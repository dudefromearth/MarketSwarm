# services/vigil/heartbeat.py

import asyncio
import json
import os
import time
from datetime import datetime, UTC
from typing import Any, Dict

from redis.asyncio import Redis


SERVICE_NAME_DEFAULT = "feed_worker"


def log(status: str, message: str, emoji: str = "", component: str = "heartbeat") -> None:
    """
    Standard log line:
      [timestamp][component][STATUS] emoji message
    """
    ts = datetime.now(UTC).isoformat(timespec="seconds")
    emoji_part = f" {emoji}" if emoji else ""
    print(f"[{ts}][{component}][{status}]{emoji_part} {message}")


async def start_heartbeat(service_name: str = SERVICE_NAME_DEFAULT,
                          config: Dict[str, Any] | None = None) -> None:
    """
    Async heartbeat loop.

    Uses the service config produced by setup.setup(), in particular:
      - config["heartbeat"]["interval_sec"]
      - config["outputs"] (to find the heartbeat publish endpoint)

    Contract:
      - Runs forever until cancelled (e.g. Ctrl+C in main).
      - Publishes a simple JSON payload to the configured heartbeat key.
    """
    if config is None:
        log("ERROR", "no config provided to start_heartbeat()", "💥")
        return

    hb_cfg = config.get("heartbeat", {}) or {}
    outputs = config.get("outputs", []) or []

    # 1) Resolve interval
    interval = hb_cfg.get("interval_sec", 10)

    # 2) Resolve Redis target from outputs:
    #    Prefer any publish_to with a key containing "heartbeat".
    hb_out: Dict[str, Any] | None = None
    for out in outputs:
        if "heartbeat" in (out.get("key") or ""):
            hb_out = out
            break

    if hb_out:
        redis_url = hb_out.get("redis_url") or os.getenv(
            "SYSTEM_REDIS_URL", "redis://127.0.0.1:6379"
        )
        heartbeat_key = hb_out.get("key") or hb_cfg.get(
            "channel", f"{service_name}:heartbeat"
        )
    else:
        # Fallback: no explicit heartbeat output; use system redis + channel
        redis_url = os.getenv("SYSTEM_REDIS_URL", "redis://127.0.0.1:6379")
        heartbeat_key = hb_cfg.get("channel", f"{service_name}:heartbeat")
        log(
            "WARN",
            f"no explicit heartbeat output in config.outputs; "
            f"falling back to {redis_url} key={heartbeat_key}",
            "⚠️",
        )

    r = Redis.from_url(redis_url, decode_responses=True)
    log(
        "INFO",
        f"connected to Redis for heartbeat (url={redis_url}, key={heartbeat_key}, interval={interval}s)",
        "🔌",
    )

    # 3) Pulse loop
    try:
        while True:
            payload = {
                "service": service_name,
                "ts": time.time(),
                "status": "alive",
            }
            try:
                await r.publish(heartbeat_key, json.dumps(payload))
                log(
                    "INFO",
                    f"heartbeat sent (key={heartbeat_key})",
                    "💓",
                )
            except Exception as e:
                log(
                    "ERROR",
                    f"failed to publish heartbeat: {e}",
                    "💥",
                )

            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        log("INFO", "heartbeat task cancelled, shutting down", "🛑")
        # Let main handle process-level shutdown
        raise