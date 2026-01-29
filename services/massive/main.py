#!/usr/bin/env python3
# services/massive/main.py

import asyncio
import sys
import os
from pathlib import Path

# ------------------------------------------------------------
# Ensure MarketSwarm root is on sys.path
# ------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ------------------------------------------------------------
# Imports
# ------------------------------------------------------------
from shared.logutil import LogUtil
from shared.heartbeat import start_heartbeat
from shared.setup_base import SetupBase

from services.massive.intel.orchestrator import run as orchestrator_run

SERVICE_NAME = "massive"


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

    # Promote logger to config-driven
    logger.configure_from_config(config)
    logger.ok("configuration loaded", emoji="📄")

    # -------------------------------------------------
    # DEBUG: Print resolved config
    # -------------------------------------------------
    logger.info("=== FINAL CONFIG DICT ===", emoji="🔍")
    for key in sorted(config.keys()):
        value = config[key]
        if key == "MASSIVE_API_KEY" and value:
            value = "******** (masked)"
        logger.info(f"{key}: {value}")
    logger.info("=== END CONFIG DICT ===", emoji="🔍")

    # -------------------------------------------------
    # Start HEARTBEAT (THREAD — NOT ASYNC)
    # -------------------------------------------------
    # Start HEARTBEAT (THREAD — NOT ASYNC)
    hb_stop = start_heartbeat(
        SERVICE_NAME,
        config,
        logger,
        payload_fn=lambda: {
            "service": SERVICE_NAME,
            "pid": os.getpid(),
            "status": "running",
        },
    )

    # -------------------------------------------------
    # Start orchestrator (async)
    # -------------------------------------------------
    orch_task = asyncio.create_task(
        orchestrator_run(config, logger),
        name=f"{SERVICE_NAME}-orchestrator",
    )

    # -------------------------------------------------
    # Supervisor loop
    # -------------------------------------------------
    try:
        await orch_task
        logger.warn("orchestrator exited unexpectedly", emoji="⚠️")
    finally:
        # Signal heartbeat thread to stop
        hb_stop.set()
        logger.info("heartbeat stop signaled", emoji="🛑")


# ------------------------------------------------------------
# Runtime wrapper
# ------------------------------------------------------------
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down gracefully…")