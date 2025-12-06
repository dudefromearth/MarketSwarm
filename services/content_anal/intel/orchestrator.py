import asyncio
import os
from typing import Any, Dict

import logutil  # services/content_anal/logutil.py


# Read debug flag from environment once at import time
DEBUG_ENABLED = os.getenv("DEBUG_MMAKER", "false").lower() == "true"


async def run(config: Dict[str, Any]) -> None:
    """
    Long-running orchestrator loop.

    This is the generic template:
      - Identifies the service from config["service_name"]
      - Emits INFO / ERROR logs always
      - Emits DEBUG logs only when DEBUG_MMAKER=true
      - Runs until cancelled by the main service loop
    """
    service_name = config.get("service_name", "unknown-service")
    loop_sleep = 1.0  # seconds between iterations (adjust per service)

    logutil.log(service_name, "INFO", "🚀", "orchestrator starting")

    try:
        while True:
            # Placeholder work – replace with real orchestration logic for this service
            if DEBUG_ENABLED:
                logutil.log(service_name, "DEBUG", "⏱️", "orchestrator tick")

            await asyncio.sleep(loop_sleep)

    except asyncio.CancelledError:
        # Normal shutdown path
        logutil.log(service_name, "INFO", "🛑", "orchestrator cancelled (shutdown)")
        raise

    except Exception as e:
        # Bubble up after logging – main loop will decide what to do
        logutil.log(service_name, "ERROR", "❌", f"orchestrator fatal error: {e}")
        raise

    finally:
        logutil.log(service_name, "INFO", "✅", "orchestrator exiting")