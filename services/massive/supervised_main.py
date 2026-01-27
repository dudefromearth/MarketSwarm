#!/usr/bin/env python3
"""
Supervised entrypoint for Massive.

This mirrors services/massive/main.py exactly in terms of:
- sys.path rooting
- LogUtil lifecycle
- SetupBase usage
- heartbeat startup
- config loading
- shared services behavior

The ONLY difference is that the orchestrator is run
inside a supervisor loop that can restart it.
"""

import asyncio
import sys
from pathlib import Path

# -------------------------------------------------
# Ensure MarketSwarm root is on sys.path
# (MUST match main.py behavior exactly)
# -------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# -------------------------------------------------
# Shared services (identical imports)
# -------------------------------------------------
from shared.logutil import LogUtil
from shared.heartbeat import start_heartbeat
from shared.setup_base import SetupBase

# -------------------------------------------------
# Massive internals
# -------------------------------------------------
from services.massive.supervisor.supervisor import MassiveSupervisor

SERVICE_NAME = "massive"


async def main():
    # -------------------------------------------------
    # Phase 1: bootstrap logger (env-based only)
    # -------------------------------------------------
    logger = LogUtil(SERVICE_NAME)
    logger.info("starting setup() [SUPERVISED]", emoji="🧭")

    # -------------------------------------------------
    # Load configuration (identity-critical)
    # -------------------------------------------------
    setup = SetupBase(SERVICE_NAME, logger)
    config = await setup.load()

    # -------------------------------------------------
    # Phase 2: promote logger to config-driven
    # -------------------------------------------------
    logger.configure_from_config(config)
    logger.ok("configuration loaded", emoji="📄")

    # -------------------------------------------------
    # DEBUG: Print final resolved config (unchanged)
    # -------------------------------------------------
    logger.info("=== FINAL CONFIG DICT ===", emoji="🔍")
    for key in sorted(config.keys()):
        value = config[key]
        if key == "MASSIVE_API_KEY" and value:
            value = "******** (masked)"
        logger.info(f"{key}: {value}")
    logger.info("=== END CONFIG DICT ===", emoji="🔍")

    # -------------------------------------------------
    # Start background shared services (heartbeat)
    # -------------------------------------------------
    hb_task = asyncio.create_task(
        start_heartbeat(SERVICE_NAME, config, logger),
        name=f"{SERVICE_NAME}-heartbeat",
    )

    # -------------------------------------------------
    # Start supervisor (owns orchestrator lifecycle)
    # IMPORTANT:
    # - Identity already resolved via SetupBase
    # - Supervisor consumes config ONLY
    # -------------------------------------------------
    supervisor = MassiveSupervisor(
        config=config,
        logger=logger,
    )

    try:
        await supervisor.run()

        # If we ever get here, it is NOT a normal condition.
        # Supervisor exiting means Massive is no longer alive.
        logger.error(
            "supervisor exited — massive service no longer running",
            emoji="💥",
        )
        raise RuntimeError("Massive supervisor exited")

    finally:
        hb_task.cancel()
        try:
            await hb_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down supervised Massive gracefully…")