#!/usr/bin/env python3
# services/copilot/main.py
"""
Copilot Service - MEL + ADI + AI Commentary

Entry point following MarketSwarm service architecture.
Uses SetupBase for config, LogUtil for logging, heartbeat for registration.
"""

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

from services.copilot.intel.orchestrator import run as orchestrator_run

SERVICE_NAME = "copilot"


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
    # Load configuration from Truth
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
            "mel_enabled": config.get("COPILOT_MEL_ENABLED", "true") == "true",
            "adi_enabled": config.get("COPILOT_ADI_ENABLED", "true") == "true",
            "commentary_enabled": config.get("COPILOT_COMMENTARY_ENABLED", "false") == "true",
        },
    )

    # -------------------------------------------------
    # Start orchestrator (async)
    # The orchestrator handles SIGINT/SIGTERM internally
    # and performs graceful shutdown via stop_event
    # -------------------------------------------------
    try:
        await orchestrator_run(config, logger)
        # Orchestrator exited normally (via signal handler)
        logger.ok("shutdown complete", emoji="✅")
    except asyncio.CancelledError:
        logger.info("orchestrator cancelled", emoji="🛑")
    finally:
        # Always stop heartbeat thread
        hb_stop.set()
        logger.info("heartbeat stopped", emoji="💓")


# ------------------------------------------------------------
# Runtime wrapper: ensures clean Ctrl-C handling
# ------------------------------------------------------------
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown complete.")
