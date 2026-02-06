#!/usr/bin/env python3
"""
volume_profile_worker.py — Session-aware SPY→SPX Volume Profile (Real-time)

Publishes:
    market-redis → "sse:volume-profile"

Responsibilities:
    • Load historical bins (massive:volume_profile)
    • Maintain in-memory volume map (spx_price → volume)
    • When new minute data arrives: update bins
    • Apply dynamic price-span slicing (centered on spot or GEX window)
    • Publish updated ordered buckets

This worker does NOT fetch historical data — that is done by
services/massive/utils/build_volume_profile.py
"""

import os
import json
import redis
from datetime import datetime, timezone
from typing import Dict, List, Tuple

# Redis ------------------------------------------------------------
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB   = int(os.getenv("REDIS_DB", "0"))

# SPY → SPX scale (must match truth.json)
SPY_MULTIPLIER = float(os.getenv("VP_SPY_MULTIPLIER", "10"))
BIN_SIZE_SPX   = float(os.getenv("VP_BIN_SIZE_SPX", "1"))

# Volume profile storage key
KEY_PROFILE = "massive:volume_profile"        # historical + live merged
CHANNEL_PUB = "sse:volume-profile"            # publish channel (market-redis)

# Optional alignment window (e.g. ±50 strikes)
DEFAULT_WINDOW = int(os.getenv("VP_WINDOW", "50"))

# ------------------------------------------------------------------
# Redis client
# ------------------------------------------------------------------
def rds():
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True,
    )

# ------------------------------------------------------------------
# Load historical stored bins
# ------------------------------------------------------------------
def load_historical_bins() -> Dict[int, float]:
    """Returns dict {spx_price:int → volume:float}.
    If none exists, returns empty.
    """
    r = rds()
    raw = r.get(KEY_PROFILE)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return {int(k): float(v) for k, v in data.get("buckets", {}).items()}
    except Exception:
        return {}

# ------------------------------------------------------------------
# Save merged profile back to redis
# ------------------------------------------------------------------
def save_profile(bins: Dict[int, float]):
    if not bins:
        return
    r = rds()
    prices = sorted(bins.keys())
    obj = {
        "symbol": "SPX",
        "spy_multiplier": SPY_MULTIPLIER,
        "bin_size_spx": BIN_SIZE_SPX,
        "min_price_spx": min(prices),
        "max_price_spx": max(prices),
        "buckets": bins,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
    r.set(KEY_PROFILE, json.dumps(obj))

# ------------------------------------------------------------------
# Publish sliced profile
# ------------------------------------------------------------------
def publish_slice(center_price: float, bins: Dict[int, float], window: int):
    """Publishes ordered slice of the volume profile.
    center_price → usually SPX spot
    window       → number of strikes ± window

    Example: window=50 → 100-point span
    """
    if center_price is None:
        return

    lo = int(center_price) - window
    hi = int(center_price) + window

    slice_bins = [
        {"price": p, "vol": bins.get(p, 0.0)}
        for p in range(lo, hi+1)
    ]

    payload = {
        "symbol": "SPX",
        "ts": datetime.now(timezone.utc).isoformat(),
        "center": center_price,
        "window": window,
        "data": slice_bins,
    }

    rds().publish(CHANNEL_PUB, json.dumps(payload))

# ------------------------------------------------------------------
# Live update entrypoint
# ------------------------------------------------------------------
def apply_live_update(bins: Dict[int, float], price_spy: float, volume: float):
    """Convert SPY → SPX and add to bucket."""
    if price_spy is None or volume is None:
        return
    spx_price = int(round(price_spy * SPY_MULTIPLIER))
    bins[spx_price] = bins.get(spx_price, 0.0) + float(volume)

# ------------------------------------------------------------------
# Worker run_once
# ------------------------------------------------------------------
def run_once():
    """This function is called by the orchestrator at ~1-minute cadence.

    Requirements:
      • Read the latest SPY minute bar (from timeseries_worker or Polygon)
      • Update volume bins
      • Publish sliced volume profile aligned to price
    """
    r = rds()

    # --- 1) Load live minute bar data pushed by timeseries_worker
    raw = r.get("market:timeseries:SPY:latest")
    if not raw:
        return

    try:
        bar = json.loads(raw)
        c = bar.get("close")    # SPY close
        v = bar.get("volume")
    except Exception:
        return

    # --- 2) Load historical bins (cached per run)
    bins = load_historical_bins()

    # --- 3) Update bins with this minute
    apply_live_update(bins, c, v)

    # --- 4) Persist merged profile
    save_profile(bins)

    # --- 5) Determine SPX spot for slicing
    raw_spot = r.get("SPX:spot:latest")   # supplied by timeseries_worker
    if not raw_spot:
        return
    try:
        spot = float(raw_spot)
    except:
        return

    # --- 6) Publish centered slice for UI & Vexy
    publish_slice(spot, bins, DEFAULT_WINDOW)

    print(f"[VP] Updated + published slice @ SPX {spot}")