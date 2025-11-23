#!/usr/bin/env python3
"""
Refactored build_volume_profile.py — WITH FIXED PAGINATION API KEY
Fully corrected version.
"""

import os
import sys
import json
import time
import requests
import redis
from datetime import datetime, UTC, timedelta, date

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "YOUR_KEY_HERE")
POLYGON_API = "https://api.polygon.io"

INSTRUMENTS = {
    "SPY": {"synthetic": "SPX", "multiplier": 10},
    "QQQ": {"synthetic": "NDX", "multiplier": 4},
}

BIN_SIZE = 1
SYSTEM_REDIS_URL = os.getenv("SYSTEM_REDIS_URL", "redis://127.0.0.1:6379")
MARKET_REDIS_URL = os.getenv("MARKET_REDIS_URL", "redis://127.0.0.1:6380")
SYSTEM_KEY = "massive:volume_profile"
MARKET_CHANNEL = "sse:volume-profile"

def rds_system(): return redis.Redis.from_url(SYSTEM_REDIS_URL, decode_responses=True)
def rds_market(): return redis.Redis.from_url(MARKET_REDIS_URL, decode_responses=True)

def save_to_system_redis(obj):
    out = dict(obj)
    for key in ("buckets_raw", "buckets_tv"):
        out[key] = {str(int(k)): float(v) for k, v in out.get(key, {}).items()}
    rds_system().set(SYSTEM_KEY, json.dumps(out))

def publish_to_market(obj): rds_market().publish(MARKET_CHANNEL, json.dumps(obj))

def http_get(url, params=None):
    headers = {"Authorization": f"Bearer {POLYGON_API_KEY}"}
    if params is None:
        params = {}
    params["apiKey"] = POLYGON_API_KEY

    for attempt in range(5):
        r = requests.get(url, params=params, headers=headers)
        if r.status_code == 429:
            time.sleep(0.25); continue
        if r.status_code in (401,403): print(f"AUTH ERROR {r.status_code}: {r.text}"); return None
        if not r.ok: print(f"HTTP {r.status_code}: {r.text}"); return None
        try: return r.json()
        except: print("Bad JSON response"); return None
    return None

def get_minute_bars(ticker, start_ymd, end_ymd):
    url = f"{POLYGON_API}/v2/aggs/ticker/{ticker}/range/1/minute/{start_ymd}/{end_ymd}"
    params = {"adjusted": "true", "limit": 50000, "sort": "asc"}

    out = []
    while True:
        data = http_get(url, params=params)
        if not data: break

        results = data.get("results") or []
        out.extend(results)

        next_url = data.get("next_url")
        if not next_url: break

        # FIXED: Ensure API KEY persists across paginated requests
        url = next_url
        params = {"apiKey": POLYGON_API_KEY}

    return out

def accumulate_raw(bins_raw, price, vol, multiplier):
    if price is None or vol is None: return
    spx = int(round(price * multiplier))
    bins_raw[spx] = bins_raw.get(spx, 0.0) + float(vol)

def accumulate_tv(bins_tv, low, high, vol, multiplier, microbins=30):
    if low is None or high is None or vol is None: return
    if high <= low: return
    step = (high - low) / microbins
    vol_per = vol / microbins
    for i in range(microbins):
        spy_price = low + i * step
        spx = int(round(spy_price * multiplier))
        bins_tv[spx] = bins_tv.get(spx, 0.0) + vol_per

def backfill(ticker, years=None, start=None, end=None, publish_mode="raw"):
    inst = INSTRUMENTS[ticker]
    synthetic = inst["synthetic"]
    multiplier = inst["multiplier"]

    if start and end:
        start_ymd, end_ymd = start, end
    else:
        if years == "max":
            start_ymd = "1993-01-29" if ticker=="SPY" else "1999-03-10"
            end_ymd = date.today().isoformat()
        else:
            yrs = int(years)
            end_dt = date.today(); start_dt = end_dt - timedelta(days=yrs*365)
            start_ymd = start_dt.isoformat(); end_ymd = end_dt.isoformat()

    print(f"Downloading {ticker} {start_ymd} → {end_ymd}")
    bars = get_minute_bars(ticker, start_ymd, end_ymd)
    print(f"Fetched {len(bars)} bars.")

    ohlc = []; bins_raw = {}; bins_tv = {}
    for b in bars:
        t,o,h,l,c,v = b.get("t"),b.get("o"),b.get("h"),b.get("l"),b.get("c"),b.get("v")
        ohlc.append({"t":t,"o":o,"h":h,"l":l,"c":c,"v":v})
        accumulate_raw(bins_raw, c, v, multiplier)
        accumulate_tv(bins_tv, l, h, v, multiplier)

    if bins_raw:
        price_min, price_max = min(bins_raw.keys()), max(bins_raw.keys())
    else:
        price_min = price_max = 0

    out = {
        "symbol": ticker,
        "synthetic_symbol": synthetic,
        "spy_multiplier": multiplier,
        "bin_size": BIN_SIZE,
        "min_price": price_min,
        "max_price": price_max,
        "last_updated": datetime.now(UTC).isoformat(),
        "ohlc": ohlc,
        "buckets_raw": bins_raw,
        "buckets_tv": bins_tv,
    }

    save_to_system_redis(out)
    print("Saved full schema to system-redis → massive:volume_profile")

    if publish_mode in ("raw","both"):
        publish_to_market({"symbol": synthetic, "mode": "raw", "buckets": bins_raw})
        print("Published RAW to market-redis → sse:volume-profile")
    if publish_mode in ("tv","both"):
        publish_to_market({"symbol": synthetic, "mode": "tv", "buckets": bins_tv})
        print("Published TV to market-redis → sse:volume-profile")

def main():
    args = sys.argv[1:]
    if not args:
        print("Usage:\n  --ticker SPY|QQQ\n  --years N|max\n  --start YYYY-MM-DD --end YYYY-MM-DD\n  --publish raw|tv|both|none")
        return
    ticker = "SPY"
    if "--ticker" in args: ticker = args[args.index("--ticker")+1].upper()
    publish_mode = "raw"
    if "--publish" in args: publish_mode = args[args.index("--publish")+1]
    if "--start" in args and "--end" in args:
        s,e = args[args.index("--start")+1], args[args.index("--end")+1]
        backfill(ticker, start=s, end=e, publish_mode=publish_mode); return
    if "--years" in args:
        yrs = args[args.index("--years")+1]
        backfill(ticker, years=yrs, publish_mode=publish_mode); return

if __name__ == "__main__": main()