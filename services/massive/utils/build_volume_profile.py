#!/usr/bin/env python3
"""
build_volume_profile.py — Historical SPY→SPX volume profile collector
Stores:
    massive:volume_profile = {
        "symbol": "SPX",
        "spy_multiplier": 10,
        "bin_size_spx": 1,
        "min_price_spx": int,
        "max_price_spx": int,
        "buckets": { "price:int": volume_float },
        "last_updated": ISO timestamp
    }
"""

import os
import sys
import json
import time
import requests
import redis
from datetime import datetime, UTC, timedelta, date

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "pdjraOWSpDbg3ER_RslZYe3dmn4Y7WCC")
POLYGON_API = "https://api.polygon.io"
TICKER = "SPY"

# SPY→SPX
MULTIPLIER = 10       # SPY * 10 = SPX
BIN_SIZE_SPX = 1      # 1 SPX point resolution

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB   = int(os.getenv("REDIS_DB", "0"))

KEY = "massive:volume_profile"


# ---------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------
def rds():
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True
    )


def load_bins():
    """Load existing profile and normalize bucket keys to int."""
    raw = rds().get(KEY)
    if not raw:
        return {}

    try:
        data = json.loads(raw)
    except Exception:
        return {}

    # Normalize buckets: keys → int, values → float
    buckets = data.get("buckets", {}) or {}
    clean = {}
    for k, v in buckets.items():
        try:
            ik = int(k)
            fv = float(v)
        except Exception:
            continue
        clean[ik] = fv

    data["buckets"] = clean
    return data


def save_bins(obj):
    """Save profile, converting bucket keys back to str for JSON/Redis."""
    buckets = obj.get("buckets", {}) or {}
    out_buckets = {}
    for k, v in buckets.items():
        try:
            sk = str(int(k))
            fv = float(v)
        except Exception:
            continue
        out_buckets[sk] = fv

    obj = dict(obj)
    obj["buckets"] = out_buckets
    rds().set(KEY, json.dumps(obj))


# ---------------------------------------------------------
# Polygon fetch
# ---------------------------------------------------------
def http_get(url, params=None):
    """GET with API key applied correctly even across next_url redirects."""
    headers = {"Authorization": f"Bearer {POLYGON_API_KEY}"}
    if params is None:
        params = {}
    params["apiKey"] = POLYGON_API_KEY

    for attempt in range(5):
        r = requests.get(url, params=params, headers=headers)
        if r.status_code == 429:
            time.sleep(0.25)
            continue

        if r.status_code in (401, 403):
            print(f"❌ AUTH ERROR {r.status_code}: {r.text}")
            return None

        if not r.ok:
            print(f"❌ HTTP {r.status_code}: {r.text}")
            return None

        try:
            return r.json()
        except Exception:
            print("❌ Bad JSON response")
            return None

    return None


def get_minute_bars(start_ymd, end_ymd):
    """Pull all minute bars for SPY between two YYYY-MM-DD dates."""
    url = f"{POLYGON_API}/v2/aggs/ticker/{TICKER}/range/1/minute/{start_ymd}/{end_ymd}"
    params = {"adjusted": "true", "limit": 50000, "sort": "asc"}

    out = []
    while True:
        data = http_get(url, params=params)
        if not data:
            break

        results = data.get("results") or []
        out.extend(results)

        next_url = data.get("next_url")
        if not next_url:
            break

        # next_url already has query params; headers still carry auth
        url = next_url
        params = {}

    return out


# ---------------------------------------------------------
# Binning
# ---------------------------------------------------------
def accumulate(bins, price_spy, volume):
    """Price is SPY. Convert → SPX. Bin at 1 SPX increments."""
    if not isinstance(price_spy, (int, float)):
        return
    if not isinstance(volume, (int, float)):
        return

    spx_price = int(round(price_spy * MULTIPLIER))
    bins[spx_price] = bins.get(spx_price, 0.0) + float(volume)


# ---------------------------------------------------------
# Main backfill logic
# ---------------------------------------------------------
def backfill_range(start_ymd, end_ymd):
    print(f"Downloading SPY minute bars {start_ymd} → {end_ymd} …")
    print(f"Using Polygon Key: {POLYGON_API_KEY[:6]}••••••••••")

    bars = get_minute_bars(start_ymd, end_ymd)
    if bars is None:
        print("❌ No data returned — API auth likely failed.")
        return

    print(f"Fetched {len(bars)} minute bars.")

    # Load existing profile (already normalized to int keys)
    data = load_bins()
    bins = data.get("buckets", {}) or {}

    # Accumulate
    for b in bars:
        c = b.get("c")
        v = b.get("v")
        accumulate(bins, c, v)

    # Ensure keys are int, values float (in case any weirdness slipped in)
    clean_bins = {}
    for k, v in bins.items():
        try:
            ik = int(k)
            fv = float(v)
        except Exception:
            continue
        clean_bins[ik] = fv
    bins = clean_bins

    # Determine price range
    prices = list(bins.keys())
    price_min = min(prices) if prices else 0
    price_max = max(prices) if prices else 0


    out = {
        "symbol": "SPX",
        "spy_multiplier": MULTIPLIER,
        "bin_size_spx": BIN_SIZE_SPX,
        "min_price_spx": price_min,
        "max_price_spx": price_max,
        "buckets": bins,
        "last_updated": datetime.now(UTC).isoformat()
    }

    save_bins(out)

    print(f"Saved profile: {len(bins)} bins, range {price_min} → {price_max}")


# ---------------------------------------------------------
# CLI
# ---------------------------------------------------------
def main():
    args = sys.argv[1:]

    if not args:
        print("Usage:")
        print("  --years 5")
        print("  --years max")
        print("  --start YYYY-MM-DD --end YYYY-MM-DD")
        print("  --summary")
        print("  --wipe")
        return

    # Wipe
    if "--wipe" in args:
        print("WIPING ALL EXISTING VOLUME PROFILE DATA…")
        rds().delete(KEY)

    # Summary
    if "--summary" in args:
        data = load_bins()
        bins = data.get("buckets", {})
        print(f"Bins: {len(bins)}")
        print(f"Range: {data.get('min_price_spx')} → {data.get('max_price_spx')}")
        print(f"Last updated: {data.get('last_updated')}")
        return

    # Date range
    if "--start" in args:
        s = args[args.index("--start") + 1]
        e = args[args.index("--end") + 1]
        backfill_range(s, e)
        return

    # Years
    if "--years" in args:
        val = args[args.index("--years") + 1]

        if val == "max":
            # SPY IPO start: 1993-01-29
            start = date(1993, 1, 29)
        else:
            years = int(val)
            end = date.today()
            start = end - timedelta(days=365 * years)

        backfill_range(start.isoformat(), date.today().isoformat())
        return


if __name__ == "__main__":
    main()