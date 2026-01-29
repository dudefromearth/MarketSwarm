#!/usr/bin/env python3
# services/journal/main.py

import asyncio
import sys
from pathlib import Path

# ------------------------------------------------------------
# 1) Ensure MarketSwarm root is on sys.path
# ------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ------------------------------------------------------------
# 2) Imports
# ------------------------------------------------------------
from shared.logutil import LogUtil
from shared.heartbeat import start_heartbeat
from shared.setup_base import SetupBase

from services.journal.intel.orchestrator import run as orchestrator_run

SERVICE_NAME = "journal"


# ------------------------------------------------------------
# Main lifecycle
# ------------------------------------------------------------
async def main():
    # -------------------------------------------------
    # Phase 1: bootstrap logger
    # -------------------------------------------------
    logger = LogUtil(SERVICE_NAME)
    logger.info("starting setup()", emoji="⚙️")

    # -------------------------------------------------
    # Load configuration
    # -------------------------------------------------
    setup = SetupBase(SERVICE_NAME, logger)
    config = await setup.load()

    # Promote logger (config-driven)
    logger.configure_from_config(config)
    logger.ok("configuration loaded", emoji="📄")

    # -------------------------------------------------
    # Start threaded heartbeat (OUTSIDE asyncio)
    # -------------------------------------------------
    hb_stop = start_heartbeat(
        SERVICE_NAME,
        config,
        logger,
        payload_fn=lambda: {
            "service": SERVICE_NAME,
            "mode": "api",
        },
    )

    # -------------------------------------------------
    # Start orchestrator (async)
    # -------------------------------------------------
    orch_task = asyncio.create_task(
        orchestrator_run(config, logger),
        name=f"{SERVICE_NAME}-orchestrator",
    )

    try:
        await orch_task
        logger.warn("orchestrator exited unexpectedly", emoji="⚠️")
    finally:
        # Always stop heartbeat thread
        hb_stop.set()


# ------------------------------------------------------------
# Runtime wrapper: ensures clean Ctrl-C handling
# ------------------------------------------------------------
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down gracefully…")
