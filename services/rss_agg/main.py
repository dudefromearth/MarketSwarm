#!/usr/bin/env python3
# services/rss_agg/main.py

import asyncio
import signal
import sys
import threading
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

from services.rss_agg.intel.orchestrator import run as orchestrator_run

SERVICE_NAME = "rss_agg"


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
    # Create shutdown event for graceful termination
    # -------------------------------------------------
    shutdown_event = threading.Event()

    # -------------------------------------------------
    # Set up signal handlers
    # -------------------------------------------------
    loop = asyncio.get_running_loop()

    def handle_shutdown(sig):
        sig_name = signal.Signals(sig).name
        logger.info(f"received {sig_name}, initiating graceful shutdown", emoji="🛑")
        shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_shutdown, sig)

    # -------------------------------------------------
    # Start threaded heartbeat (OUTSIDE asyncio)
    # -------------------------------------------------
    hb_stop = start_heartbeat(
        SERVICE_NAME,
        config,
        logger,
        payload_fn=lambda: {
            "service": SERVICE_NAME,
            "mode": "aggregator",
        },
    )

    # -------------------------------------------------
    # Run orchestrator with shutdown event
    # -------------------------------------------------
    logger.info("starting orchestrator", emoji="🚀")

    try:
        await orchestrator_run(config, logger, shutdown_event)
    except asyncio.CancelledError:
        logger.info("orchestrator task cancelled", emoji="⚠️")
    except Exception as e:
        logger.error(f"orchestrator error: {e}", emoji="💥")
    finally:
        # Stop heartbeat
        logger.info("stopping heartbeat", emoji="🔌")
        hb_stop.set()
        logger.ok("shutdown complete", emoji="✅")


# ------------------------------------------------------------
# Runtime wrapper
# ------------------------------------------------------------
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass  # Already handled by signal handler
