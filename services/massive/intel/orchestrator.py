# services/massive/intel/orchestrator.py

import asyncio
import os
from typing import Any, Dict

from .spot_worker import SpotWorker
from .chain_worker import ChainWorker
from .ws_worker import WsWorker

# Robust import for logutil, regardless of how module is executed
try:
    # Preferred: package-relative when intel is a subpackage of massive
    from .. import logutil  # type: ignore[import]
except ImportError:
    # Fallback: direct import when massive/ is on sys.path (as main.py does)
    import logutil  # type: ignore[no-redef]

DEBUG_ENABLED = os.getenv("DEBUG_MASSIVE", "false").lower() == "true"


async def run(config: Dict[str, Any]) -> None:
    service_name = config.get("service_name", "massive")
    logutil.log(
        service_name,
        "INFO",
        "🚀",
        "orchestrator starting (spot + chain + ws)",
    )

    stop_event = asyncio.Event()

    spot_worker = SpotWorker(config)
    chain_worker = ChainWorker(config)
    ws_worker = WsWorker(config)

    tasks = [
        asyncio.create_task(spot_worker.run(stop_event), name="massive-spot"),
        asyncio.create_task(chain_worker.run(stop_event), name="massive-chain"),
        asyncio.create_task(ws_worker.run(stop_event), name="massive-ws"),
    ]

    try:
        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_EXCEPTION,
        )

        for t in done:
            exc = t.exception()
            if exc:
                raise exc

    except asyncio.CancelledError:
        logutil.log(service_name, "INFO", "🛑", "orchestrator cancelled (shutdown)")
        stop_event.set()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    except Exception as e:
        logutil.log(service_name, "ERROR", "❌", f"orchestrator fatal error: {e}")
        stop_event.set()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    finally:
        logutil.log(service_name, "INFO", "✅", "orchestrator exiting")