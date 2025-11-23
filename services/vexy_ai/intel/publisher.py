#!/usr/bin/env python3
"""
publisher.py — Real-Time Commentary Publisher for Vexy AI

Part of MarketSwarm — the real-time options + intel play-by-play engine
Built by Ernie & Conor — 2025

Purpose:
    Publish epoch and event commentary to the market-redis bus with perfect provenance.

Key Responsibilities:
    • Serialize and publish commentary to vexy:playbyplay channel
    • Enforce MarketSwarm logging standard with timestamp + component + step
    • Guarantee delivery of structured payload to FrontEndNode
    • Be the single source of truth for what Vexy says

First Principles:
    • One channel: vexy:playbyplay on market-redis (6380)
    • One format: JSON with kind, text, meta, ts, voice
    • One voice per payload — "anchor" today, Ice/Fire tomorrow
    • Never drop a message — if Redis is down, we die loudly
    • Logging is sacred — every publish must be visible

Future Developer Notes:
    • This file will never change structure — only voice and channel
    • FrontEndNode depends on this exact schema — break it and the world ends
    • Add new voices by extending meta["voice"] — never touch the channel
    • This is the mouth of the swarm. Keep it clean, loud, and honest.

You are holding the voice of the market.
Make it speak truth.
"""

import redis
import json
from datetime import datetime
from typing import Dict, Any

# Market-redis — where FrontEndNode listens
r = redis.Redis(host="127.0.0.1", port=6380, decode_responses=True)


def _log(step: str, emoji: str, msg: str):
    """
    Internal logging — follows MarketSwarm canonical format.

    Format: [YYYY-MM-DD HH:MM:SS] [vexy_ai|step] message
    """
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [vexy_ai|{step}] {emoji} {msg}")


def publish(kind: str, text: str, meta: Dict[str, Any]) -> None:
    """
    Publish commentary to the market bus.

    This is the single point where Vexy speaks to the world.

    Args:
        kind (str): "epoch" or "event" — determines icon and routing
        text (str): The exact words Vexy says
        meta (dict): Structured context — epoch name, event type, symbol, etc.

    Returns:
        None — fire and forget (Redis pub/sub)

    Notes:
        • Channel: vexy:playbyplay on market-redis (6380)
        • Payload includes UTC timestamp with Z suffix
        • Voice field allows future multi-personality support
        • Logs using MarketSwarm standard with appropriate emoji
    """
    payload = {
        "kind": kind,
        "text": text.strip(),
        "meta": meta,
        "ts": datetime.utcnow().isoformat() + "Z",
        "voice": "anchor"  # future: "ice", "fire", "whisper"
    }

    try:
        r.publish("vexy:playbyplay", json.dumps(payload))
        emoji = "Speaking" if kind == "epoch" else "Event"
        _log(kind, emoji, text[:140])
    except redis.RedisError as e:
        _log("publish", "ERROR", f"Failed to publish to Redis: {e}")
        raise  # Die loudly — if we can't speak, the swarm is broken