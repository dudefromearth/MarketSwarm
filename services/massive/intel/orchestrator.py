# services/massive/intel/orchestrator.py

import asyncio
import os
from datetime import datetime, timezone
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


def _today_yyyymmdd() -> str:
    """
    Default WS expiry when none is provided:
      - Use current UTC date
      - Format: YYYYMMDD
    """
    return datetime.now(timezone.utc).strftime("%Y%m%d")


async def run(config: Dict[str, Any]) -> None:
    service_name = config.get("service_name", "massive")

    # ------------------------------------------------------------
    # WS-specific config bridge (env → WsWorker config)
    # ------------------------------------------------------------

    # 1) WS enabled: default ON unless explicitly disabled
    ws_enabled_env = config.get(
        "ws_enabled",
        os.getenv("MASSIVE_WS_ENABLED", "true").lower() == "true",
    )

    # 2) Expiry: accept config/env, normalize, or default to today (0DTE)
    raw_expiry = (
        config.get("ws_expiry_yyyymmdd")
        or os.getenv("MASSIVE_WS_EXPIRY_YYYYMMDD", "")
    )

    if raw_expiry:
        expiry_clean = raw_expiry.replace("-", "")
    else:
        expiry_clean = _today_yyyymmdd()

    # Keep an ISO version around for clarity / downstream consumers
    expiry_iso = (
        f"{expiry_clean[0:4]}-{expiry_clean[4:6]}-{expiry_clean[6:8]}"
        if len(expiry_clean) == 8
        else expiry_clean
    )

    # 3) URL + reconnect
    ws_url_env = config.get(
        "ws_url",
        os.getenv("MASSIVE_WS_URL", "wss://socket.massive.com/options"),
    )
    ws_reconnect_env = config.get(
        "ws_reconnect_delay_sec",
        float(os.getenv("MASSIVE_WS_RECONNECT_DELAY_SEC", "5.0")),
    )

    # Make a shallow copy so we can tweak WS-related fields only
    ws_config: Dict[str, Any] = dict(config)
    ws_config.setdefault("ws_enabled", ws_enabled_env)
    ws_config["ws_url"] = ws_url_env
    ws_config["ws_reconnect_delay_sec"] = ws_reconnect_env
    ws_config["ws_expiry_yyyymmdd"] = expiry_clean  # WsWorker accepts YYYYMMDD / YYYY-MM-DD

    # ------------------------------------------------------------
    # Logging startup
    # ------------------------------------------------------------
    extras = []
    if ws_enabled_env:
        extras.append(f"ws(exp={expiry_iso})")

    logutil.log(
        service_name,
        "INFO",
        "🚀",
        f"orchestrator starting (spot + chain + {', '.join(extras) or 'no ws'})",
    )

    stop_event = asyncio.Event()

    # ------------------------------------------------------------
    # Initialize workers with config (they pull shared from config)
    # ------------------------------------------------------------
    spot_worker = SpotWorker(config)
    chain_worker = ChainWorker(config)

    ws_worker = None
    if ws_enabled_env:
        try:
            ws_worker = WsWorker(ws_config)
        except Exception as e:
            # If WS is misconfigured, spot/chain still run.
            logutil.log(
                service_name,
                "ERROR",
                "💥",
                f"Failed to init WsWorker (WS disabled for this run): {e}",
            )

    # ------------------------------------------------------------
    # Task creation
    # ------------------------------------------------------------
    tasks = [
        asyncio.create_task(spot_worker.run(stop_event), name="massive-spot"),
        asyncio.create_task(chain_worker.run(stop_event), name="massive-chain"),
    ]

    if ws_worker is not None:
        tasks.append(
            asyncio.create_task(ws_worker.run(stop_event), name="massive-ws")
        )

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
        # Close shared primary Redis if present
        shared_resources = config.get("shared_resources", {})
        if "primary_redis" in shared_resources:
            await shared_resources["primary_redis"].close()
        logutil.log(service_name, "INFO", "✅", "orchestrator exiting")