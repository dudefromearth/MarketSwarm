#!/usr/bin/env python3
"""
timeseries_worker.py — SPX Timeseries Feed
Fetches:
    • SPX spot (prefer synthetic → snapshot → minute bar → prev close)
    • Latest OHLCV from Polygon (1-min aggregates)

Publishes to:
    • sse:timeseries               (truth.json)
    • massive:timeseries:latest     (KV)
    • massive:timeseries:{ts}       (snapshot key)

Payload shape:
{
    "symbol": "SPX",
    "ts": "2025-01-01T12:34:56Z",
    "o": float,
    "h": float,
    "l": float,
    "c": float,
    "v": float,
    "spot": float,
    "spot_source": str
}
"""

import os
import json
import time
import redis
import requests
from datetime import datetime, timezone


# ============================================================
# CONFIG
# ============================================================
POLYGON_API = "https://api.polygon.io"
API_KEY = os.getenv("POLYGON_API_KEY", "")
SYMBOL = os.getenv("TIMESERIES_SYMBOL", "SPX")
API_SYMBOL = os.getenv("API_SYMBOL", "I:SPX")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB   = int(os.getenv("REDIS_DB", "0"))

PUB_CHANNEL = "sse:timeseries"
KEY_LATEST  = "massive:timeseries:latest"
KEY_PREFIX  = "massive:timeseries"


# ============================================================
# Redis helper
# ============================================================
def rds():
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True
    )


# ============================================================
# Polygon: HTTP wrapper
# ============================================================
def http_get(url, params=None):
    if params is None:
        params = {}

    params["apiKey"] = API_KEY

    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 429:
            time.sleep(0.25)
            return http_get(url, params)  # retry
        if not r.ok:
            return None
        return r.json()
    except Exception:
        return None


# ============================================================
# Spot resolution (synthetic → snapshot → minute → prev close)
# ============================================================
def synthetic_spot_from_ohlc(o, h, l, c):
    """Simplest synthetic midpoint."""
    nums = [x for x in (o, h, l, c) if isinstance(x, (int, float))]
    if not nums:
        return None
    return sum(nums) / len(nums)


def get_spot():
    """
    Multi-tier:
      1. Try /v3/snapshot/indices (primary)
      2. Try minute bar
      3. Try prev close
    """
    # --- (1) index snapshot ---
    url = f"{POLYGON_API}/v3/snapshot/indices"
    j = http_get(url, {"ticker": API_SYMBOL})
    if j:
        res = j.get("results")
        p = None
        if isinstance(res, list) and res:
            p = res[0].get("ticker", {}).get("lastTrade", {}).get("p")
        elif isinstance(res, dict):
            p = res.get("ticker", {}).get("lastTrade", {}).get("p")
        if isinstance(p, (int, float)):
            return float(p), "v3_snapshot"

    # --- (2) minute bar ---
    url = f"{POLYGON_API}/v2/aggs/ticker/{API_SYMBOL}/range/1/minute/2020-01-01/2100-01-01"
    j = http_get(url, {"adjusted": "true", "limit": 1, "sort": "desc"})
    if j and "results" in j and j["results"]:
        bar = j["results"][0]
        c = bar.get("c")
        if isinstance(c, (int, float)):
            return float(c), "minute_bar"

    # --- (3) prev close ---
    url = f"{POLYGON_API}/v2/aggs/ticker/{API_SYMBOL}/prev"
    j = http_get(url, {"adjusted": "true"})
    if j and "results" in j and j["results"]:
        c = j["results"][0].get("c")
        if isinstance(c, (int, float)):
            return float(c), "prev_close"

    return None, "none"


# ============================================================
# Fetch OHLCV (latest 1-min)
# ============================================================
def get_latest_ohlcv():
    url = f"{POLYGON_API}/v2/aggs/ticker/{API_SYMBOL}/range/1/minute/2020-01-01/2100-01-01"
    j = http_get(url, {"adjusted": "true", "limit": 1, "sort": "desc"})
    if not j or "results" not in j or not j["results"]:
        return None

    bar = j["results"][0]
    return {
        "o": bar.get("o"),
        "h": bar.get("h"),
        "l": bar.get("l"),
        "c": bar.get("c"),
        "v": bar.get("v"),
        "ts_ms": bar.get("t")
    }


# ============================================================
# MAIN WORKER — run_once()
# ============================================================
def run_once():
    if not API_KEY:
        print("⚠️ TIMESERIES: Missing POLYGON_API_KEY; cannot fetch.")
        return

    # Fetch OHLCV
    bar = get_latest_ohlcv()
    if not bar:
        print("⚠️ TIMESERIES: No OHLCV data returned.")
        return

    # Fetch spot
    spot, spot_src = get_spot()
    if spot is None:
        # fallback: synthetic midpoint
        spot = synthetic_spot_from_ohlc(bar["o"], bar["h"], bar["l"], bar["c"])
        spot_src = "synthetic"

    # Timestamp
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    payload = {
        "symbol": SYMBOL,
        "ts": ts,
        "o": bar["o"],
        "h": bar["h"],
        "l": bar["l"],
        "c": bar["c"],
        "v": bar["v"],
        "spot": spot,
        "spot_source": spot_src
    }

    # Redis persistence
    r = rds()
    snap_key = f"{KEY_PREFIX}:{ts}"

    pipe = r.pipeline()
    pipe.set(KEY_LATEST, json.dumps(payload))
    pipe.set(snap_key, json.dumps(payload))
    pipe.publish(PUB_CHANNEL, json.dumps(payload))
    pipe.execute()

    print(f"🕒 TIMESERIES → spot={spot:.2f} ({spot_src}) OHLC=({bar['o']},{bar['h']},{bar['l']},{bar['c']})")


# ============================================================
# CLI (debug mode)
# ============================================================
if __name__ == "__main__":
    print("Running timeseries_once()…")
    run_once()