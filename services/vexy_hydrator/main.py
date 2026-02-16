#!/usr/bin/env python3
"""
Vexy Hydrator — Cognition Snapshot Builder.

Builds and refreshes low-latency cognition snapshots in Echo Redis
by hydrating from canonical user + system sources.

Bootstrap pattern: LogUtil → SetupBase → heartbeat → run
"""

import asyncio
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure MarketSwarm root is on sys.path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import redis as sync_redis
import uvicorn
from fastapi import FastAPI

from shared.logutil import LogUtil
from shared.heartbeat import start_heartbeat
from shared.setup_base import SetupBase

SERVICE_NAME = "vexy_hydrator"


async def main():
    """Bootstrap and run the hydrator."""

    # Phase 1: Logger
    logger = LogUtil(SERVICE_NAME)
    logger.info("Starting Vexy Hydrator...", emoji="🌿")

    # Phase 2: Configuration
    setup = SetupBase(SERVICE_NAME, logger)
    config = await setup.load()
    logger.configure_from_config(config)
    logger.ok("Configuration loaded", emoji="📄")

    # Phase 3: Heartbeat
    http_port = int(os.getenv("HYDRATOR_PORT", "3007"))

    hb_stop = start_heartbeat(
        SERVICE_NAME,
        config,
        logger,
        payload_fn=lambda: {
            "service": SERVICE_NAME,
            "mode": "hydrator",
            "http_port": http_port,
        },
    )

    # Phase 4: Connect to Redis buses
    buses = config.get("buses", {}) or {}
    echo_url = buses.get("echo-redis", {}).get("url", "redis://127.0.0.1:6382")
    market_url = buses.get("market-redis", {}).get("url", "redis://127.0.0.1:6380")

    echo_redis = sync_redis.from_url(echo_url, decode_responses=True)
    market_redis = sync_redis.from_url(market_url, decode_responses=True)

    # Verify echo-redis
    try:
        echo_redis.ping()
        logger.info(f"Connected to echo-redis: {echo_url}", emoji="🧠")
    except Exception as e:
        logger.error(f"Cannot connect to echo-redis: {e}", emoji="❌")
        hb_stop.set()
        return

    # Verify market-redis
    try:
        market_redis.ping()
        logger.info(f"Connected to market-redis: {market_url}", emoji="🔴")
    except Exception as e:
        logger.error(f"Cannot connect to market-redis: {e}", emoji="❌")
        hb_stop.set()
        return

    # Phase 5: Create sources + hydration engine
    from services.vexy_hydrator.sources.market_source import MarketSource
    from services.vexy_hydrator.sources.warm_source import WarmSource
    from services.vexy_hydrator.sources.risk_source import RiskSource
    from services.vexy_hydrator.sources.system_source import SystemSource
    from services.vexy_hydrator.hydrator import HydrationEngine

    market_source = MarketSource(market_redis, logger)
    warm_source = WarmSource(config, logger)
    risk_source = RiskSource(config, logger)
    system_source = SystemSource(config, logger)

    engine = HydrationEngine(
        echo_redis=echo_redis,
        market_source=market_source,
        warm_source=warm_source,
        risk_source=risk_source,
        system_source=system_source,
        logger=logger,
    )

    # Phase 6: Create FastAPI app + routes
    app = FastAPI(title="Vexy Hydrator", version="1.0")

    from services.vexy_hydrator.routes import create_router
    api_router = create_router(engine, logger)
    app.include_router(api_router)

    # Phase 7: Start presence listener
    from services.vexy_hydrator.triggers import PresenceListener

    async def on_presence(user_id: int, tier: str):
        """Callback: hydrate snapshot when user detected."""
        await engine.hydrate(user_id=user_id, tier=tier)

    presence = PresenceListener(market_redis, on_presence, logger)
    await presence.start()

    # Phase 8: Start routine data cache refresh loop
    async def routine_data_loop():
        """Refresh system-level routine data from market-redis to echo-redis."""
        await asyncio.sleep(5)  # Let services settle
        while True:
            try:
                await _refresh_routine_data(market_redis, echo_redis, logger)
            except Exception as e:
                logger.warning(f"Routine data refresh error: {e}")
            await asyncio.sleep(300)  # 5 minutes

    routine_task = asyncio.create_task(routine_data_loop())

    # Phase 8b: Start daily echo consolidation loop (17:30 ET)
    async def consolidation_loop():
        """Run echo consolidation daily at 17:30 ET (post market close + buffer)."""
        import pytz
        ET_TZ = pytz.timezone("America/New_York")
        ran_today = None  # Track which date we last ran

        await asyncio.sleep(30)  # Let services settle
        while True:
            try:
                now = datetime.now(ET_TZ)
                today = now.strftime("%Y-%m-%d")

                if now.hour == 17 and now.minute >= 30 and ran_today != today:
                    logger.info("Starting daily echo consolidation...", emoji="🔄")
                    from services.vexy_ai.intel.scheduled_jobs import run_echo_consolidation
                    result = await run_echo_consolidation(logger=logger)
                    logger.info(
                        f"Consolidation complete: {result.get('users_consolidated')}/{result.get('users_processed')} users, "
                        f"{result.get('total_conversations')} convs, {result.get('total_activities')} acts, "
                        f"{result.get('duration_ms')}ms",
                        emoji="✅",
                    )
                    ran_today = today
            except Exception as e:
                logger.warning(f"Consolidation loop error: {e}")
            await asyncio.sleep(60)  # Check every minute

    consolidation_task = asyncio.create_task(consolidation_loop())

    # Phase 9: Run HTTP server
    logger.ok(f"Hydrator ready on port {http_port}", emoji="🌿")

    server_config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=http_port,
        log_level="warning",
    )
    server = uvicorn.Server(server_config)

    try:
        await server.serve()
    except asyncio.CancelledError:
        logger.info("Shutdown signal received", emoji="🛑")
    finally:
        await presence.stop()
        routine_task.cancel()
        consolidation_task.cancel()
        hb_stop.set()
        logger.info("Vexy Hydrator shutdown complete", emoji="✓")


async def _refresh_routine_data(market_redis, echo_redis, logger):
    """
    Read system-level market data from market-redis, write summaries to echo-redis.

    Categories and sources:
    - econ_calendar: massive:econ:schedule:rolling:v1 (TTL 1h)
    - vix: massive:vix_regime:model:SPX (TTL 5min)
    - market_conditions: massive:model:spot:SPX + massive:market_mode:model:SPX (TTL 15min)
    - gex: massive:gex:model:SPX:calls/puts (TTL 2h)
    - regime: massive:bias_lfi:model:SPX (TTL 1h)
    """
    import json

    CATEGORIES = {
        "econ_calendar": {
            "keys": ["massive:econ:schedule:rolling:v1"],
            "ttl": 3600,
        },
        "vix": {
            "keys": ["massive:vix_regime:model:SPX"],
            "ttl": 300,
        },
        "market_conditions": {
            "keys": ["massive:model:spot:SPX", "massive:market_mode:model:SPX"],
            "ttl": 900,
        },
        "gex": {
            "keys": ["massive:gex:model:SPX:calls", "massive:gex:model:SPX:puts"],
            "ttl": 7200,
        },
        "regime": {
            "keys": ["massive:bias_lfi:model:SPX"],
            "ttl": 3600,
        },
    }

    for category, spec in CATEGORIES.items():
        try:
            data = {}
            for key in spec["keys"]:
                raw = market_redis.get(key)
                if raw:
                    try:
                        data[key.split(":")[-1]] = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        data[key.split(":")[-1]] = raw

            if data:
                echo_key = f"echo:system:routine_data:{category}"
                echo_redis.set(echo_key, json.dumps(data), ex=spec["ttl"])
        except Exception as e:
            logger.warning(f"Routine data refresh failed for {category}: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down gracefully...")
