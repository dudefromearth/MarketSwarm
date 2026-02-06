#!/usr/bin/env python3
"""
vp_live_worker.py — FINAL optimized incremental VP updater.
Called once per orchestrator cycle.

Responsibilities:
  • Fetch the latest minute bar (SPY or QQQ)
  • Convert to synthetic SPX/NDX price space
  • Incrementally update RAW and TV bins ONLY
  • Recompute lightweight VP metrics (VPOC, HVN, LVN)
  • Save updated model to system-redis
  • Publish unified model snapshot to market-redis (sse:volume-profile)
"""

import os, json, redis, requests
from datetime import datetime, UTC

# ---------------------------------------------------------------------
# ENV + CONFIG
# ---------------------------------------------------------------------
SYSTEM_KEY       = "massive:volume_profile"
MARKET_CHANNEL   = "sse:volume-profile"

SYSTEM_REDIS_URL = os.getenv("SYSTEM_REDIS_URL", "redis://127.0.0.1:6379")
MARKET_REDIS_URL = os.getenv("MARKET_REDIS_URL", "redis://127.0.0.1:6380")

POLYGON_API_KEY  = os.getenv("POLYGON_API_KEY")

SPY_SYMBOL       = os.getenv("VP_SPY_SYMBOL", "SPY")
SYN_SYMBOL       = os.getenv("VP_SYN", "SPX")
SCALE            = float(os.getenv("VP_SCALE", "10"))
MICROBINS        = int(os.getenv("VP_MICROBINS", "30"))

# RAW bins use bin-size 1 SPX point (implicit in SCALE)
# TV bins distribute volume across microbins between low→high.

r_system = redis.Redis.from_url(SYSTEM_REDIS_URL, decode_responses=True)
r_market = redis.Redis.from_url(MARKET_REDIS_URL, decode_responses=True)


# ---------------------------------------------------------------------
# Fetch latest minute bar
# ---------------------------------------------------------------------
def fetch_latest_minute():
    url = f"https://api.polygon.io/v2/aggs/ticker/{SPY_SYMBOL}/range/1/minute/latest"
    params = {"apiKey": POLYGON_API_KEY, "adjusted": "true", "limit": 1}

    r = requests.get(url, params=params)
    if not r.ok:
        print("[vp_live_worker] Polygon error:", r.text)
        return None

    data = r.json()
    if "results" not in data or not data["results"]:
        return None

    return data["results"][0]


# ---------------------------------------------------------------------
# Compute VPOC + HVN/LVN from bins
# Very cheap: N ≈ 4000–6000
# ---------------------------------------------------------------------
def compute_vp_metrics(bins_raw: dict):
    if not bins_raw:
        return None, [], []

    kv = {int(k): float(v) for k, v in bins_raw.items()}
    vpoc = max(kv.keys(), key=lambda k: kv[k])

    vols = list(kv.values())
    avg = sum(vols) / len(vols)

    hvn = [p for p, v in kv.items() if v >= avg * 1.5]
    lvn = [p for p, v in kv.items() if v <= avg * 0.5]

    return vpoc, hvn, lvn


# ---------------------------------------------------------------------
# MAIN ONE-SHOT UPDATE
# ---------------------------------------------------------------------
def run_once(config=None, log=lambda *_: None):
    try:
        base = r_system.get(SYSTEM_KEY)
        if not base:
            log("volume", "⚠️", "No base VP model found in system redis")
            return

        model = json.loads(base)
        bins_raw = model.get("buckets_raw", {})
        bins_tv  = model.get("buckets_tv", {})

        bar = fetch_latest_minute()
        if not bar:
            log("volume", "⚠️", "No latest bar from Polygon")
            return

        c = bar["c"]   # close
        h = bar["h"]
        l = bar["l"]
        v = bar["v"]

        # -------------------------------------------------------------
        # Update RAW bin
        # -------------------------------------------------------------
        spx_bin = int(round(c * SCALE))
        bins_raw[str(spx_bin)] = bins_raw.get(str(spx_bin), 0.0) + v

        # -------------------------------------------------------------
        # Update TV bins (distributed)
        # -------------------------------------------------------------
        if h > l:
            step = (h - l) / MICROBINS
            vol_per = v / MICROBINS
            for i in range(MICROBINS):
                price_micro = l + i * step
                spx_micro   = int(round(price_micro * SCALE))
                bins_tv[str(spx_micro)] = bins_tv.get(str(spx_micro), 0.0) + vol_per

        # -------------------------------------------------------------
        # Recompute structural metrics (cheap)
        # -------------------------------------------------------------
        vpoc, hvn, lvn = compute_vp_metrics(bins_raw)

        # -------------------------------------------------------------
        # Update model
        # -------------------------------------------------------------
        model["buckets_raw"]  = bins_raw
        model["buckets_tv"]   = bins_tv
        model["vpoc"]         = vpoc
        model["hvn"]          = hvn
        model["lvn"]          = lvn
        model["last_updated"] = datetime.now(UTC).isoformat()

        # Save full model to system redis
        r_system.set(SYSTEM_KEY, json.dumps(model))

        # Publish unified snapshot to market redis
        snapshot = {
            "symbol": SYN_SYMBOL,
            "volume_profile": model,
        }
        r_market.publish(MARKET_CHANNEL, json.dumps(snapshot))

        log("volume", "🟢", f"VP updated + published (bin={spx_bin}, vol={v})")

    except Exception as e:
        log("volume", "❌", f"VP worker error: {e}")