# services/copilot/intel/orchestrator.py
"""
Copilot Orchestrator - MEL + ADI + Commentary API Server

Receives config from SetupBase, manages service lifecycle.
"""

import asyncio
import signal
import os
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
from .ai_providers import AIProviderConfig


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
        self.host = "127.0.0.1"
        self.port = int(config.get("COPILOT_PORT", "8095"))
        self.mel_enabled = config.get("COPILOT_MEL_ENABLED", "true") == "true"
        self.adi_enabled = config.get("COPILOT_ADI_ENABLED", "true") == "true"
        self.commentary_enabled = config.get("COPILOT_COMMENTARY_ENABLED", "false") == "true"

        # MEL thresholds from config
        self.mel_threshold_valid = int(config.get("COPILOT_MEL_THRESHOLD_VALID", "70"))
        self.mel_threshold_degraded = int(config.get("COPILOT_MEL_THRESHOLD_DEGRADED", "50"))
        self.mel_interval_ms = int(config.get("COPILOT_MEL_INTERVAL_MS", "5000"))

        # Redis connections (from buses in config)
        self.buses = config.get("buses", {})
        self.market_redis: Redis | None = None
        self.system_redis: Redis | None = None

        # Market data cache (populated from Redis subscriptions)
        self._market_data = {
            "spot_price": None,
            "gamma_levels": None,
            "volume_profile": None,
            "heatmap": None,
            "timestamp": None,
        }

        # Subsystems
        self.mel: MELOrchestrator | None = None
        self.mel_api: MELAPIHandler | None = None
        self.adi: ADIOrchestrator | None = None
        self.adi_api: ADIAPIHandler | None = None
        self.commentary: CommentaryService | None = None
        self.commentary_api: CommentaryAPIHandler | None = None

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

    def get_market_data(self) -> dict:
        """
        Get current market data for MEL calculation.
        Returns cached data from Redis subscriptions.
        """
        return self._market_data

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

        self.mel_api = MELAPIHandler(orchestrator=self.mel, logger=self.logger)
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
            provider=commentary_settings.get("provider", "anthropic"),
            api_key=os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"),
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

    async def health_check(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({
            "status": "ok",
            "service": "copilot",
            "timestamp": datetime.utcnow().isoformat(),
            "mel_enabled": self.mel_enabled,
            "adi_enabled": self.adi_enabled,
            "commentary_enabled": self.commentary_enabled,
        })

    async def setup_web_app(self):
        """Setup aiohttp web application."""
        self.app = web.Application()
        self.app.router.add_get("/health", self.health_check)

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

        # Setup web app
        await self.setup_web_app()

        # Start MEL
        if self.mel:
            if self.mel_api:
                self.mel_api.setup_broadcast()
            await self.mel.start()

        # Start Commentary
        if self.commentary:
            await self.commentary.start()

        # Start web server
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()

        self.logger.ok(f"Copilot ready at http://{self.host}:{self.port}", emoji="🚀")

    async def stop(self):
        """Stop all subsystems."""
        self.logger.info("shutting down...", emoji="🛑")

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

    # Setup signal handlers
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def handle_signal():
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    # Start orchestrator
    await orchestrator.start()

    # Wait for stop signal
    await stop_event.wait()

    # Cleanup
    await orchestrator.stop()
