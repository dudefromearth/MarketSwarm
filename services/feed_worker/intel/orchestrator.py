import asyncio
import os
from typing import Any, Dict
from urllib.parse import urlparse

import logutil  # services/feed_worker/logutil.py
import dte_feed_worker

DEBUG_ENABLED = os.getenv("DEBUG_FEED_WORKER", "false").lower() == "true"


def _build_worker_cfg(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Translate the service config into a flat dict for dte_feed_worker.configure_from_dict().
    Adjust the field names to match whatever your Truth/config actually emits.
    """

    worker = config.get("worker") or config.get("feed_worker") or {}
    polygon = config.get("polygon") or {}

    out: Dict[str, Any] = {}

    # --- Polygon API key ---
    if "api_key" in worker:
        out["api_key"] = worker["api_key"]
    elif "api_key" in polygon:
        out["api_key"] = polygon["api_key"]
    elif "polygon_api_key" in config:
        out["api_key"] = config["polygon_api_key"]

    # --- Symbols / DTEs ---
    out["symbol"] = worker.get("symbol") or config.get("symbol") or "SPX"
    out["api_symbol"] = worker.get("api_symbol") or config.get("api_symbol") or "I:SPX"
    out["dte_list"] = worker.get("dte_list") or config.get("dte_list") or [0, 1, 2, 3, 4, 5]

    # --- Market Redis URL → host/port/db ---
    market_url = (
        worker.get("market_redis_url")
        or config.get("market_redis_url")
        or os.getenv("MARKET_REDIS_URL")
        or "redis://127.0.0.1:6380"
    )
    parsed = urlparse(market_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 6380
    db = 0
    if parsed.path and parsed.path.strip("/"):
        try:
            db = int(parsed.path.strip("/"))
        except Exception:
            db = 0
    out["redis_host"] = host
    out["redis_port"] = port
    out["redis_db"] = db

    # --- Optional tuning block ---
    tuning = worker.get("tuning") or config.get("tuning") or {}
    for key in (
        "trail_ttl_seconds",
        "snapshot_ttl_seconds",
        "spot_publish_eps",
        "force_publish_interval_s",
        "sleep_min_s",
        "sleep_max_s",
        "quiet_delta",
        "hot_delta",
        "snapshot_mode",
        "use_pubsub",
        "use_exp_pubsub",
        "diff_for_all",
        "use_dte_aliases",
        "request_timeout",
        "page_limit",
        "include_greeks",
        "live_max_age_s",
        "delayed_max_age_s",
        "winsor_pct",
        "tag_backfill",
    ):
        if key in tuning:
            out[key] = tuning[key]

    return out


async def run(config: Dict[str, Any]) -> None:
    """
    Orchestrator for the feed_worker service.

    - Build a worker config from the service config
    - Configure dte_feed_worker
    - Run dte_feed_worker.run_loop() in a background thread
    - Cooperate with asyncio cancellation
    """

    service_name = config.get("service_name", "feed_worker")

    worker_cfg = _build_worker_cfg(config)
    dte_feed_worker.configure_from_dict(worker_cfg)

    logutil.log(service_name, "INFO", "🚀", "orchestrator starting (feed_worker)")
    if DEBUG_ENABLED:
        logutil.log(
            service_name,
            "DEBUG",
            "🔧",
            f"worker_cfg: symbol={worker_cfg.get('symbol')} api_symbol={worker_cfg.get('api_symbol')} "
            f"dte_list={worker_cfg.get('dte_list')} redis={worker_cfg.get('redis_host')}:{worker_cfg.get('redis_port')}/{worker_cfg.get('redis_db')}",
        )

    async def run_worker_in_thread() -> None:
        if DEBUG_ENABLED:
            logutil.log(service_name, "DEBUG", "🧵", "starting dte_feed_worker.run_loop() in thread")
        await asyncio.to_thread(dte_feed_worker.run_loop)

    worker_task = asyncio.create_task(run_worker_in_thread(), name=f"{service_name}-worker")

    try:
        await worker_task

    except asyncio.CancelledError:
        # Cooperative shutdown: tell worker loop to stop.
        if hasattr(dte_feed_worker, "_running"):
            dte_feed_worker._running = False  # type: ignore[attr-defined]
            if DEBUG_ENABLED:
                logutil.log(
                    service_name,
                    "DEBUG",
                    "🛑",
                    "set dte_feed_worker._running = False (shutdown signal)",
                )
        logutil.log(service_name, "INFO", "🛑", "orchestrator cancelled (shutdown)")
        raise

    except Exception as e:
        logutil.log(service_name, "ERROR", "💥", f"worker fatal error: {e}")
        raise

    finally:
        logutil.log(service_name, "INFO", "✅", "orchestrator exiting")