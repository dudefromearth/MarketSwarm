import asyncio
import os
from typing import Any, Dict

from shared.logutil import LogUtil


# Read debug flag from environment once at import time
DEBUG_ENABLED = os.getenv("DEBUG_CONTENT_ANAL", "false").lower() == "true"


async def run(config: Dict[str, Any], logger: LogUtil) -> None:
    """
    Long-running orchestrator loop.

    This is the generic template:
      - Identifies the service from config["service_name"]
      - Emits INFO / ERROR logs always
      - Emits DEBUG logs only when DEBUG_CONTENT_ANAL=true
      - Runs until cancelled by the main service loop
    """
    service_name = config.get("service_name", "content_anal")
    loop_sleep = 1.0  # seconds between iterations (adjust per service)

    logger.info("orchestrator starting", emoji="🚀")

    try:
        while True:
            # Placeholder work – replace with real orchestration logic for this service
            if DEBUG_ENABLED:
                logger.debug("orchestrator tick", emoji="⏱️")

            await asyncio.sleep(loop_sleep)

    except asyncio.CancelledError:
        # Normal shutdown path
        logger.info("orchestrator cancelled (shutdown)", emoji="🛑")
        raise

    except Exception as e:
        # Bubble up after logging – main loop will decide what to do
        logger.error(f"orchestrator fatal error: {e}", emoji="❌")
        raise

    finally:
        logger.info("orchestrator exiting", emoji="✅")
