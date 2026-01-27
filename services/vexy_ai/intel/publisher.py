#!/usr/bin/env python3
"""
publisher.py — Real-Time Commentary Publisher for Vexy AI

Publishes epoch and event commentary to the market-redis bus.
"""

import json
import os
from datetime import datetime, UTC
from typing import Any, Dict, Optional

import redis

# Lazy connection — initialized on first publish
_r_market: Optional[redis.Redis] = None


def _get_redis() -> redis.Redis:
    global _r_market
    if _r_market is None:
        url = os.getenv("MARKET_REDIS_URL", "redis://127.0.0.1:6380")
        _r_market = redis.Redis.from_url(url, decode_responses=True)
    return _r_market


def _log(step: str, emoji: str, msg: str):
    """Internal logging — follows MarketSwarm canonical format."""
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [vexy_ai|{step}] {emoji} {msg}")


def publish(kind: str, text: str, meta: Dict[str, Any]) -> None:
    """
    Publish commentary to the market bus.

    Args:
        kind (str): "epoch" or "event" — determines icon and routing
        text (str): The exact words Vexy says
        meta (dict): Structured context — epoch name, event type, symbol, etc.
    """
    r = _get_redis()

    payload = {
        "kind": kind,
        "text": text.strip(),
        "meta": meta,
        "ts": datetime.now(UTC).isoformat() + "Z",
        "voice": "anchor",
    }

    try:
        # Publish to channel (for real-time subscribers)
        r.publish("vexy:playbyplay", json.dumps(payload))

        # Also store as latest model (for polling clients)
        r.set(
            f"vexy:model:playbyplay:{kind}:latest",
            json.dumps(payload),
            ex=3600,  # 1 hour TTL
        )

        emoji = "🎙️" if kind == "epoch" else "💥"
        _log(kind, emoji, text[:140])
    except redis.RedisError as e:
        _log("publish", "❌", f"Failed to publish to Redis: {e}")
        raise
