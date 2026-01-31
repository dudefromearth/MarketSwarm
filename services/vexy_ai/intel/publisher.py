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


def _get_today_key() -> str:
    """Get the Redis key for today's messages."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    return f"vexy:messages:{today}"


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

    payload_json = json.dumps(payload)

    try:
        # Publish to channel (for real-time subscribers)
        r.publish("vexy:playbyplay", payload_json)

        # Store in today's message list (for history)
        # Messages persist for the entire day + buffer
        today_key = _get_today_key()
        r.rpush(today_key, payload_json)
        r.expire(today_key, 86400 + 3600)  # 25 hours TTL (day + 1 hour buffer)

        # Also keep latest for quick polling
        r.set(
            f"vexy:model:playbyplay:{kind}:latest",
            payload_json,
            ex=86400,  # 24 hour TTL
        )

        emoji = "🎙️" if kind == "epoch" else "💥"
        _log(kind, emoji, text[:140])
    except redis.RedisError as e:
        _log("publish", "❌", f"Failed to publish to Redis: {e}")
        raise


def get_today_messages() -> list:
    """Retrieve all messages from today."""
    r = _get_redis()
    today_key = _get_today_key()
    try:
        messages = r.lrange(today_key, 0, -1)
        return [json.loads(m) for m in messages]
    except redis.RedisError as e:
        _log("fetch", "❌", f"Failed to fetch messages: {e}")
        return []
