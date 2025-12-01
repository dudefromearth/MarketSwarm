#!/usr/bin/env python3
import json
import os
from urllib.parse import urlparse

import redis


def _redis_from_url(url: str) -> redis.Redis:
    parsed = urlparse(url or "redis://127.0.0.1:6379")
    return redis.Redis(
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 6379,
        decode_responses=True,
    )


def _load_truth(r: redis.Redis) -> dict:
    """
    Support both truth:doc (new) and truth (legacy) for compatibility.
    """
    for key in (os.getenv("TRUTH_KEY") or "truth:doc", "truth"):
        raw = r.get(key)
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                continue
    return {}


def setup_service_environment(svc: str):
    system_url = os.getenv("SYSTEM_REDIS_URL", "redis://127.0.0.1:6379")
    r = _redis_from_url(system_url)

    truth = _load_truth(r)
    if not truth:
        raise RuntimeError("truth not found in system-redis")

    comp = truth.get("components", {}).get(svc)
    if not comp:
        raise RuntimeError(f"No component block for {svc}")

    print(f"[{svc}] Setup complete — truth loaded")
    return {
        "truth": truth,
        "component": comp,
        "redis": r,
    }
