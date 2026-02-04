# services/copilot/intel/orchestrator.py
"""
Copilot Orchestrator - MEL + ADI + Commentary API Server

Receives config from SetupBase, manages service lifecycle.
"""

import asyncio
from typing import Dict, Any
from datetime import datetime

from aiohttp import web
import aiohttp_cors
from redis.asyncio import Redis

from .mel import MELOrchestrator
from .mel_models import MELConfig
from .mel_api import MELAPIHandler
from .adi import ADIOrchestrator
from .adi_api import ADIAPIHandler
from .commentary import CommentaryService
from .commentary_models import CommentaryConfig
from .commentary_api import CommentaryAPIHandler
from .ai_providers import AIProviderConfig, AIProviderManager, create_provider
from .alert_engine import AlertEngine, AlertEngineConfig
from .alert_evaluators import create_all_evaluators


class CopilotOrchestrator:
    """
    Main orchestrator for Copilot service.

    Manages MEL, ADI, and Commentary subsystems.
    Connects to MarketSwarm Redis buses for market data.
    """

    def __init__(self, config: Dict[str, Any], logger):
        self.config = config
        self.logger = logger

        # Extract config values
        self.host = "0.0.0.0"
        self.port = int(config.get("COPILOT_PORT", "8095"))
        self.mel_enabled = config.get("COPILOT_MEL_ENABLED", "true") == "true"
        self.adi_enabled = config.get("COPILOT_ADI_ENABLED", "true") == "true"
        self.commentary_enabled = config.get("COPILOT_COMMENTARY_ENABLED", "false") == "true"
        self.alerts_enabled = config.get("COPILOT_ALERTS_ENABLED", "true") == "true"

        # MEL thresholds from config
        self.mel_threshold_valid = int(config.get("COPILOT_MEL_THRESHOLD_VALID", "70"))
        self.mel_threshold_degraded = int(config.get("COPILOT_MEL_THRESHOLD_DEGRADED", "50"))
        self.mel_interval_ms = int(config.get("COPILOT_MEL_INTERVAL_MS", "5000"))

        # Redis connections (from buses in config)
        self.buses = config.get("buses", {})
        self.market_redis: Redis | None = None
        self.system_redis: Redis | None = None
        self.intel_redis: Redis | None = None

        # Market data cache per DTE (populated from Redis subscriptions)
        # Key is DTE (0, 1, 2, etc.), value is market data dict
        self._market_data_by_dte: Dict[int, dict] = {}
        self._available_dtes: list = []
        self._active_dte: int = 0  # Currently selected DTE for MEL calculation

        # Subsystems
        self.mel: MELOrchestrator | None = None
        self.mel_api: MELAPIHandler | None = None
        self.adi: ADIOrchestrator | None = None
        self.adi_api: ADIAPIHandler | None = None
        self.commentary: CommentaryService | None = None
        self.commentary_api: CommentaryAPIHandler | None = None
        self.alert_engine: AlertEngine | None = None
        self.ai_manager: AIProviderManager | None = None

        # Web app
        self.app: web.Application | None = None
        self.runner: web.AppRunner | None = None

    async def connect_redis(self):
        """Connect to Redis buses."""
        market_bus = self.buses.get("market-redis", {})
        system_bus = self.buses.get("system-redis", {})

        if market_bus.get("url"):
            self.market_redis = Redis.from_url(
                market_bus["url"],
                decode_responses=True
            )
            self.logger.info(f"connected to market-redis", emoji="🔗")

        if system_bus.get("url"):
            self.system_redis = Redis.from_url(
                system_bus["url"],
                decode_responses=True
            )
            self.logger.info(f"connected to system-redis", emoji="🔗")

        intel_bus = self.buses.get("intel-redis", {})
        if intel_bus.get("url"):
            self.intel_redis = Redis.from_url(
                intel_bus["url"],
                decode_responses=True
            )
            self.logger.info(f"connected to intel-redis", emoji="🔗")

    def get_market_data(self, dte: int | None = None) -> dict:
        """
        Get current market data for MEL calculation.
        Returns cached data for the specified DTE (or active DTE).
        """
        target_dte = dte if dte is not None else self._active_dte
        return self._market_data_by_dte.get(target_dte, {})

    def set_active_dte(self, dte: int) -> None:
        """Set the active DTE for MEL calculation."""
        if dte != self._active_dte:
            self._active_dte = dte
            self.logger.info(f"MEL active DTE changed to {dte}", emoji="📅")

    def get_available_dtes(self) -> list:
        """Get list of available DTEs from GEX data."""
        return self._available_dtes

    def get_event_flags(self, now: datetime) -> list:
        """
        Get event flags for the current time.
        TODO: Integrate with economic calendar from market-redis.
        """
        return []

    def get_user_context(self) -> dict:
        """
        Get user context for ADI snapshot.
        TODO: Integrate with UI state via WebSocket.
        """
        return {
            "selected_tile": None,
            "risk_graph_strategies": [],
            "active_alerts": [],
            "open_trades": [],
            "active_log_id": None,
        }

    async def poll_market_data(self):
        """
        Poll Redis for market data and update _market_data_by_dte cache.
        Transforms massive data format into MEL-compatible format for each DTE.
        Runs every 5 seconds.
        """
        import json
        from datetime import datetime as dt
        poll_interval = 5  # seconds

        while True:
            try:
                if self.market_redis:
                    # Fetch spot price (shared across all DTEs)
                    spot_raw = await self.market_redis.get("massive:model:spot:I:SPX")
                    spot_price = None
                    if spot_raw:
                        try:
                            spot_data = json.loads(spot_raw)
                            spot_price = spot_data.get("value")
                        except Exception:
                            pass

                    # Fetch price history from trail (shared across all DTEs)
                    price_history = []
                    try:
                        trail_raw = await self.market_redis.zrange(
                            "massive:model:spot:I:SPX:trail", -100, -1, withscores=True
                        )
                        for member, score in trail_raw:
                            try:
                                data = json.loads(member)
                                price_history.append({
                                    "price": data.get("value"),
                                    "ts": score,
                                })
                            except Exception:
                                pass
                    except Exception:
                        pass

                    # Fetch heatmap (shared)
                    heatmap_raw = await self.market_redis.get("massive:heatmap:model:I:SPX:latest")
                    heatmap_data = None
                    if heatmap_raw:
                        try:
                            heatmap_data = json.loads(heatmap_raw)
                        except Exception:
                            pass

                    # Fetch volume profile (shared)
                    vp_raw = await self.market_redis.hgetall("massive:volume_profile:spx")
                    volume_profile = None
                    if vp_raw:
                        try:
                            volume_profile = {
                                int(k): int(v) for k, v in vp_raw.items()
                            }
                        except Exception:
                            pass

                    # Fetch GEX data - process ALL expirations
                    gex_calls_raw = await self.market_redis.get("massive:gex:model:I:SPX:calls")
                    gex_puts_raw = await self.market_redis.get("massive:gex:model:I:SPX:puts")

                    if gex_calls_raw and gex_puts_raw:
                        try:
                            calls_data = json.loads(gex_calls_raw)
                            puts_data = json.loads(gex_puts_raw)

                            calls_exp = calls_data.get("expirations", {})
                            puts_exp = puts_data.get("expirations", {})

                            if calls_exp and puts_exp:
                                # Get sorted expiration dates
                                all_exps = sorted(set(calls_exp.keys()) & set(puts_exp.keys()))
                                self._available_dtes = list(range(len(all_exps)))

                                # Process each expiration as a DTE index
                                for dte_index, exp_date in enumerate(all_exps):
                                    calls = calls_exp.get(exp_date, {})
                                    puts = puts_exp.get(exp_date, {})

                                    # Calculate net gamma at each strike
                                    all_strikes = set(calls.keys()) | set(puts.keys())
                                    net_gamma = {}
                                    max_abs_gamma = 0
                                    max_gamma_strike = None

                                    for strike in all_strikes:
                                        call_g = float(calls.get(strike, 0))
                                        put_g = float(puts.get(strike, 0))
                                        net = call_g - put_g
                                        net_gamma[int(float(strike))] = net

                                        # Track max gamma for magnet
                                        total = call_g + put_g
                                        if total > max_abs_gamma:
                                            max_abs_gamma = total
                                            max_gamma_strike = int(float(strike))

                                    # Sort strikes and build gamma level dicts
                                    sorted_strikes = sorted(net_gamma.keys())
                                    gamma_levels = [
                                        {"strike": s, "net_gamma": net_gamma[s]}
                                        for s in sorted_strikes
                                    ]
                                    gamma_magnet = max_gamma_strike

                                    # Find zero gamma (where net gamma crosses zero)
                                    zero_gamma = None
                                    prev_strike = None
                                    prev_net = None
                                    for strike in sorted_strikes:
                                        net = net_gamma[strike]
                                        if prev_net is not None:
                                            if (prev_net < 0 and net > 0) or (prev_net > 0 and net < 0):
                                                zero_gamma = (prev_strike + strike) / 2
                                                break
                                        prev_strike = strike
                                        prev_net = net

                                    # Store market data for this DTE
                                    self._market_data_by_dte[dte_index] = {
                                        "dte": dte_index,
                                        "expiration": exp_date,
                                        "spot_price": spot_price,
                                        "gamma_levels": gamma_levels,
                                        "zero_gamma": zero_gamma,
                                        "gamma_magnet": gamma_magnet,
                                        "price_history": price_history,
                                        "volume_profile": volume_profile,
                                        "heatmap": heatmap_data,
                                        "timestamp": datetime.utcnow(),
                                    }

                        except Exception as e:
                            self.logger.warn(f"GEX transform error: {e}", emoji="⚠️")

                    # Notify alert engine of market data update
                    self._on_market_data_update()

            except Exception as e:
                self.logger.warn(f"market data poll error: {e}", emoji="⚠️")

            await asyncio.sleep(poll_interval)

    async def setup_mel(self):
        """Initialize MEL subsystem."""
        if not self.mel_enabled:
            self.logger.info("MEL disabled by config", emoji="⏸️")
            return

        # Build MEL config from Truth settings
        mel_settings = self.config.get("mel", {})
        config_kwargs = {
            "snapshot_interval_ms": self.mel_interval_ms,
            "valid_threshold": float(self.mel_threshold_valid),
            "degraded_threshold": float(self.mel_threshold_degraded),
        }
        if mel_settings.get("weights"):
            config_kwargs["weights"] = mel_settings["weights"]
        if mel_settings.get("coherenceMultipliers"):
            config_kwargs["coherence_multipliers"] = mel_settings["coherenceMultipliers"]
        mel_config = MELConfig(**config_kwargs)

        self.mel = MELOrchestrator(
            config=mel_config,
            logger=self.logger,
            market_data_provider=self.get_market_data,
            event_calendar=self.get_event_flags,
        )

        self.mel_api = MELAPIHandler(
            orchestrator=self.mel,
            logger=self.logger,
            copilot_orchestrator=self,
        )
        self.logger.ok("MEL orchestrator initialized", emoji="📊")

    async def setup_adi(self):
        """Initialize ADI subsystem."""
        if not self.adi_enabled:
            self.logger.info("ADI disabled by config", emoji="⏸️")
            return

        if not self.mel:
            self.logger.warn("ADI requires MEL - skipping", emoji="⚠️")
            return

        self.adi = ADIOrchestrator(
            mel_orchestrator=self.mel,
            market_data_provider=self.get_market_data,
            user_context_provider=self.get_user_context,
            logger=self.logger,
            symbol="SPX",
        )

        self.adi_api = ADIAPIHandler(orchestrator=self.adi, logger=self.logger)
        self.logger.ok("ADI orchestrator initialized", emoji="🤖")

    async def setup_commentary(self):
        """Initialize Commentary subsystem."""
        if not self.commentary_enabled:
            self.logger.info("Commentary disabled by config", emoji="⏸️")
            return

        commentary_settings = self.config.get("commentary", {})

        ai_config = AIProviderConfig(
            provider=commentary_settings.get("provider", "openai"),
            api_key=self.config.get("OPENAI_API_KEY") or self.config.get("ANTHROPIC_API_KEY"),
            model=None,  # Use provider default
        )

        commentary_config = CommentaryConfig(
            enabled=True,
            rate_limit_per_minute=commentary_settings.get("rateLimitPerMinute", 10),
        )

        self.commentary = CommentaryService(
            config=commentary_config,
            ai_config=ai_config,
            logger=self.logger,
        )

        self.commentary_api = CommentaryAPIHandler(
            service=self.commentary,
            logger=self.logger
        )

        # Connect MEL updates to Commentary triggers
        if self.mel:
            self.mel.subscribe(self.commentary.update_mel)

        self.logger.ok("Commentary service initialized", emoji="💬")

    async def setup_alerts(self):
        """Initialize Alert Engine subsystem."""
        if not self.alerts_enabled:
            self.logger.info("Alerts disabled by config", emoji="⏸️")
            return

        alerts_settings = self.config.get("alerts", {})
        keys_config = alerts_settings.get("keys", {})

        # Setup AI provider manager for AI-powered alerts
        ai_config = AIProviderConfig(
            provider=alerts_settings.get("provider", "openai"),
            api_key=self.config.get("OPENAI_API_KEY") or self.config.get("ANTHROPIC_API_KEY"),
            model=alerts_settings.get("model"),
        )

        try:
            primary_provider = create_provider(ai_config, self.logger)
            self.ai_manager = AIProviderManager(
                primary=primary_provider,
                fallback=None,
                logger=self.logger,
            )
            self.logger.info(f"AI provider configured: {alerts_settings.get('provider', 'anthropic')}", emoji="🤖")
        except Exception as e:
            self.logger.warn(f"AI provider setup failed: {e}, AI alerts will be disabled", emoji="⚠️")
            self.ai_manager = None

        # Create alert engine config from Truth settings
        alert_config = AlertEngineConfig(
            enabled=True,
            fast_loop_interval_ms=int(self.config.get(
                "COPILOT_ALERTS_FAST_LOOP_MS",
                alerts_settings.get("fastLoopIntervalMs", 1000)
            )),
            slow_loop_interval_ms=int(self.config.get(
                "COPILOT_ALERTS_SLOW_LOOP_MS",
                alerts_settings.get("slowLoopIntervalMs", 5000)
            )),
            # Redis keys from Truth config
            redis_key_prefix=keys_config.get("alertPrefix", "copilot:alerts"),
            publish_channel=keys_config.get("events", "copilot:alerts:events"),
            latest_key=keys_config.get("latest", "copilot:alerts:latest"),
            analytics_key=keys_config.get("analytics", "copilot:alerts:analytics"),
            # Role gating from Truth config
            role_gating=alerts_settings.get("roleGating"),
            limits=alerts_settings.get("limits"),
            max_alerts_per_user=alerts_settings.get("maxAlertsPerUser", 50),
        )

        self.logger.info(
            f"Alert config: fast={alert_config.fast_loop_interval_ms}ms, "
            f"slow={alert_config.slow_loop_interval_ms}ms, "
            f"channel={alert_config.publish_channel}",
            emoji="⚙️"
        )

        # Initialize alert engine
        self.alert_engine = AlertEngine(
            config=alert_config,
            redis=self.market_redis,
            intel_redis=self.intel_redis,
            logger=self.logger,
        )

        # Register all evaluators
        evaluators = create_all_evaluators(self.ai_manager)
        for evaluator in evaluators:
            self.alert_engine.register_evaluator(evaluator)

        # Log role gating config
        if alert_config.role_gating:
            ai_types = [t for t in alert_config.role_gating.keys() if t.startswith("ai_")]
            self.logger.info(f"Role gating enabled for {len(ai_types)} AI alert types", emoji="🔐")

        self.logger.ok("Alert engine initialized", emoji="🔔")

    def _on_market_data_update(self) -> None:
        """Called after market data is updated - notifies alert engine."""
        if self.alert_engine:
            market_data = self.get_market_data()
            # Use asyncio.create_task to avoid blocking the poll loop
            asyncio.create_task(
                self.alert_engine.update_market_data(market_data),
                name="alert-market-update"
            )

    async def health_check(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({
            "status": "ok",
            "service": "copilot",
            "timestamp": datetime.utcnow().isoformat(),
            "mel_enabled": self.mel_enabled,
            "adi_enabled": self.adi_enabled,
            "commentary_enabled": self.commentary_enabled,
            "alerts_enabled": self.alerts_enabled,
            "alerts_count": len(self.alert_engine.get_alerts()) if self.alert_engine else 0,
        })

    async def debug_market_data(self, request: web.Request) -> web.Response:
        """Debug endpoint to check market data per DTE."""
        dte = int(request.query.get("dte", "0"))
        data = self._market_data_by_dte.get(dte, {})

        # Summarize gamma levels
        gamma_levels = data.get("gamma_levels", [])
        gamma_summary = {
            "count": len(gamma_levels),
            "first_5": gamma_levels[:5] if gamma_levels else [],
            "last_5": gamma_levels[-5:] if gamma_levels else [],
        }

        return web.json_response({
            "dte": dte,
            "active_dte": self._active_dte,
            "available_dtes": self._available_dtes,
            "data_present": bool(data),
            "spot_price": data.get("spot_price"),
            "zero_gamma": data.get("zero_gamma"),
            "gamma_magnet": data.get("gamma_magnet"),
            "gamma_levels_summary": gamma_summary,
            "price_history_count": len(data.get("price_history", [])),
            "expiration": data.get("expiration"),
        })

    async def get_analytics(self, request: web.Request) -> web.Response:
        """GET /analytics - Get all Copilot analytics."""
        analytics = {
            "service": "copilot",
            "timestamp": datetime.utcnow().isoformat(),
            "mel": {
                "enabled": self.mel_enabled,
                "running": getattr(self, 'mel', None) is not None,
            },
            "adi": {
                "enabled": self.adi_enabled,
                "running": getattr(self, 'adi', None) is not None,
            },
            "commentary": {
                "enabled": self.commentary_enabled,
                "running": getattr(self, 'commentary', None) is not None,
            },
            "alerts": await self._get_alert_analytics() if getattr(self, 'alert_engine', None) else {},
        }
        return web.json_response(analytics)

    async def get_alert_analytics(self, request: web.Request) -> web.Response:
        """GET /analytics/alerts - Get alert-specific analytics."""
        if not self.alert_engine:
            return web.json_response({"error": "Alert engine not initialized"}, status=503)

        analytics = await self._get_alert_analytics()
        return web.json_response(analytics)

    async def _get_alert_analytics(self) -> dict:
        """Get alert analytics from the alert engine."""
        if not self.alert_engine:
            return {}

        try:
            analytics = await self.alert_engine.get_analytics_from_redis()
            return {
                "enabled": self.alerts_enabled,
                "running": self.alert_engine._running,
                **analytics,
            }
        except Exception as e:
            self.logger.warn(f"Error getting alert analytics: {e}")
            return self.alert_engine.get_analytics()

    async def setup_web_app(self):
        """Setup aiohttp web application."""
        self.app = web.Application()
        self.app.router.add_get("/health", self.health_check)
        self.app.router.add_get("/debug/market-data", self.debug_market_data)
        self.app.router.add_get("/analytics", self.get_analytics)
        self.app.router.add_get("/analytics/alerts", self.get_alert_analytics)

        # Register API routes
        if self.mel_api:
            self.mel_api.register_routes(self.app)
        if self.adi_api:
            self.adi_api.register_routes(self.app)
        if self.commentary_api:
            self.commentary_api.register_routes(self.app)

        # Setup CORS
        cors = aiohttp_cors.setup(self.app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
            )
        })
        for route in list(self.app.router.routes()):
            if not route.resource.canonical.startswith("/ws"):
                cors.add(route)

        self.logger.ok("web application configured", emoji="🌐")

    async def start(self):
        """Start all subsystems and web server."""
        # Connect to Redis
        await self.connect_redis()

        # Initialize subsystems
        await self.setup_mel()
        await self.setup_adi()
        await self.setup_commentary()
        await self.setup_alerts()

        # Setup web app
        await self.setup_web_app()

        # Start market data polling
        asyncio.create_task(self.poll_market_data(), name="market-data-poll")
        self.logger.info("market data polling started", emoji="📊")

        # Start MEL
        if self.mel:
            if self.mel_api:
                self.mel_api.setup_broadcast()
            await self.mel.start()

        # Start Commentary
        if self.commentary:
            await self.commentary.start()

        # Start Alert Engine
        if self.alert_engine:
            await self.alert_engine.start()

        # Start web server
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()

        self.logger.ok(f"Copilot ready at http://{self.host}:{self.port}", emoji="🚀")

    async def stop(self):
        """Stop all subsystems."""
        self.logger.info("shutting down...", emoji="🛑")

        if self.alert_engine:
            await self.alert_engine.stop()
        if self.commentary:
            await self.commentary.stop()
        if self.mel:
            await self.mel.stop()
        if self.mel_api:
            await self.mel_api.close_all()
        if self.runner:
            await self.runner.cleanup()
        if self.market_redis:
            await self.market_redis.close()
        if self.system_redis:
            await self.system_redis.close()

    async def run_forever(self):
        """Run until interrupted."""
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()


async def run(config: Dict[str, Any], logger):
    """
    Entry point called by main.py.

    Args:
        config: Configuration dict from SetupBase
        logger: LogUtil instance
    """
    orchestrator = CopilotOrchestrator(config, logger)
    await orchestrator.start()

    try:
        # Run forever until cancelled
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info("orchestrator cancelled", emoji="🛑")
    finally:
        await orchestrator.stop()
