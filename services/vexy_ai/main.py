#!/usr/bin/env python3
"""
Vexy AI - Central Nervous System of MarketSwarm.

This is the bootstrap entry point. All business logic lives in
capability modules. This file only:
1. Sets up the Python path
2. Creates the logger
3. Loads configuration
4. Wires the dependency container
5. Starts Vexy (which runs the HTTP server and background tasks)
6. Handles clean shutdown
"""

import asyncio
import os
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

SERVICE_NAME = "vexy_ai"


# ------------------------------------------------------------
# Main lifecycle
# ------------------------------------------------------------
async def main():
    """Bootstrap and run Vexy."""
    # -------------------------------------------------
    # Phase 1: Bootstrap logger
    # -------------------------------------------------
    logger = LogUtil(SERVICE_NAME)
    logger.info("Starting Vexy AI...", emoji="🦋")

    # -------------------------------------------------
    # Phase 2: Load configuration
    # -------------------------------------------------
    setup = SetupBase(SERVICE_NAME, logger)
    config = await setup.load()
    logger.configure_from_config(config)
    logger.ok("Configuration loaded", emoji="📄")

    # -------------------------------------------------
    # Phase 3: Start heartbeat (threaded, outside asyncio)
    # -------------------------------------------------
    http_port = int(os.getenv("VEXY_HTTP_PORT", "3005"))
    config["VEXY_HTTP_PORT"] = http_port

    hb_stop = start_heartbeat(
        SERVICE_NAME,
        config,
        logger,
        payload_fn=lambda: {
            "service": SERVICE_NAME,
            "mode": "assistant",
            "http_port": http_port,
        },
    )

    # -------------------------------------------------
    # Phase 4: Wire dependency container
    # -------------------------------------------------
    from services.vexy_ai.core.container import Container

    container = Container(config, logger)
    vexy = await container.wire()

    # -------------------------------------------------
    # Phase 5: Start Vexy (runs HTTP server and background tasks)
    # -------------------------------------------------
    try:
        await vexy.start()
    except asyncio.CancelledError:
        logger.info("Received shutdown signal", emoji="🛑")
    except Exception as e:
        logger.error(f"Vexy failed: {e}", emoji="❌")
        raise
    finally:
        # -------------------------------------------------
        # Phase 6: Clean shutdown
        # -------------------------------------------------
        hb_stop.set()
        await container.shutdown()
        logger.info("Vexy AI shutdown complete", emoji="✓")


# ------------------------------------------------------------
# Runtime wrapper: ensures clean Ctrl-C handling
# ------------------------------------------------------------
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down gracefully...")
