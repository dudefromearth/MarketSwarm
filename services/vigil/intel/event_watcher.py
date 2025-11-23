#!/usr/bin/env python3
"""
Vigil — MarketSwarm Event Watcher
Single-cycle watcher: fetch → filter → publish
"""

import json
import time
from datetime import datetime, timezone
import redis

# Redis
r_market = redis.Redis(host="127.0.0.1", port=6380, decode_responses=True)

# Publisher
def publish_event(event: dict):
    payload = {"event": json.dumps(event)}
    r_market.xadd("vigil:events", payload)
    print(f"[vigil] 🔔 event published: {event['type']}")

# Normalizer
def normalize(kind: str, data: dict) -> dict:
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": kind,
        "severity": data.get("severity", "info"),
        "evidence": data,
    }

# Filters
def detect_sharp_move(chain):
    mv = chain.get("px_move_pct", 0)
    if abs(mv) >= 0.5:
        return normalize("sharp_move", {"move": mv, "severity": "medium"})
    return None

def detect_volume_surge(chain):
    vol = chain.get("volume_ratio", 1)
    if vol >= 3.0:
        return normalize("volume_surge", {"ratio": vol, "severity": "high"})
    return None

FILTERS = [detect_sharp_move, detect_volume_surge]

# Listener
def fetch_latest_chain():
    msg = r_market.xrevrange("sse:chain-feed", "+", "-", count=1)
    if not msg:
        return None
    _, fields = msg[0]
    try:
        return json.loads(fields.get("delta", "{}"))
    except Exception:
        return None

# IMPORTANT:
# This now runs **one cycle** only.
def run_once():
    chain = fetch_latest_chain()
    if not chain:
        return

    for f in FILTERS:
        evt = f(chain)
        if evt:
            publish_event(evt)