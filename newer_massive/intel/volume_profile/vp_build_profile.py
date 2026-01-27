#!/usr/bin/env python3
"""
vp_build_profile.py

Build a synthetic SPX/NDX volume profile from 1-min ETF bars and
store it in Redis.

Input JSON (from vp_download_history.py):

{
  "ticker": "SPY",
  "start": "YYYY-MM-DD",
  "end": "YYYY-MM-DD",
  "bars": [ { "o":..., "h":..., "l":..., "c":..., "v":..., "t":... }, ... ]
}

Output keys:

  SYSTEM_REDIS:
    massive:volume_profile          → full schema (same shape as original script)

  MARKET_REDIS (optional):
    sse:volume-profile              → published light payload:
      { "symbol": "SPX", "mode": "raw|tv", "buckets": { price: vol, ... } }

Usage:

  python vp_build_profile.py \
    --ticker SPY \
    --file ./data/vp/SPY_1min_YYYY-MM-DD_to_YYYY-MM-DD.json \
    --publish raw
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, UTC
from typing import Any, Dict, List

import redis


INSTRUMENTS: Dict[str, Dict[str, Any]] = {
    "SPY": {"synthetic": "SPX", "multiplier": 10},
    "QQQ": {"synthetic": "NDX", "multiplier": 4},
}

BIN_SIZE = 1

SYSTEM_REDIS_URL = os.getenv("SYSTEM_REDIS_URL", "redis://127.0.0.1:6379")
MARKET_REDIS_URL = os.getenv("MARKET_REDIS_URL", "redis://127.0.0.1:6380")
SYSTEM_KEY = "massive:volume_profile"
MARKET_CHANNEL = "sse:volume-profile"


def log(stage: str, emoji: str, msg: str) -> None:
    print(f"[vp_build|{stage}]{emoji} {msg}")


def rds_system() -> redis.Redis:
    return redis.Redis.from_url(SYSTEM_REDIS_URL, decode_responses=True)


def rds_market() -> redis.Redis:
    return redis.Redis.from_url(MARKET_REDIS_URL, decode_responses=True)


def accumulate_raw(
    bins_raw: Dict[int, float],
    price: float | None,
    vol: float | None,
    multiplier: int,
) -> None:
    if price is None or vol is None:
        return
    spx = int(round(price * multiplier))
    bins_raw[spx] = bins_raw.get(spx, 0.0) + float(vol)


def accumulate_tv(
    bins_tv: Dict[int, float],
    low: float | None,
    high: float | None,
    vol: float | None,
    multiplier: int,
    microbins: int = 30,
) -> None:
    if low is None or high is None or vol is None:
        return
    if high <= low:
        return

    step = (high - low) / microbins
    vol_per = vol / microbins

    for i in range(microbins):
        spy_price = low + i * step
        spx = int(round(spy_price * multiplier))
        bins_tv[spx] = bins_tv.get(spx, 0.0) + vol_per


def save_to_system_redis(obj: Dict[str, Any]) -> None:
    out = dict(obj)
    # Ensure keys in buckets are strings for JSON
    for key in ("buckets_raw", "buckets_tv"):
        out[key] = {str(int(k)): float(v) for k, v in out.get(key, {}).items()}
    rds_system().set(SYSTEM_KEY, json.dumps(out))
    log("redis", "💾", f"Wrote base profile to SYSTEM_REDIS ({SYSTEM_KEY})")


def publish_to_market(obj: Dict[str, Any]) -> None:
    rds_market().publish(MARKET_CHANNEL, json.dumps(obj))
    log("redis", "📡", f"Published profile to MARKET_REDIS ({MARKET_CHANNEL})")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()

    ap.add_argument(
        "--ticker",
        type=str,
        required=True,
        help="Underlying ETF used for profile (SPY, QQQ)",
    )
    ap.add_argument(
        "--file",
        type=str,
        required=True,
        help="JSON file produced by vp_download_history.py",
    )
    ap.add_argument(
        "--publish",
        type=str,
        default="raw",
        choices=["raw", "tv", "both", "none"],
        help="How to publish to MARKET_REDIS",
    )

    return ap.parse_args()


def main() -> None:
    args = parse_args()
    ticker = args.ticker.upper()

    if ticker not in INSTRUMENTS:
        raise SystemExit(f"Unsupported ticker: {ticker}. Supported: {list(INSTRUMENTS)}")

    synthetic = INSTRUMENTS[ticker]["synthetic"]
    multiplier = INSTRUMENTS[ticker]["multiplier"]

    path = args.file
    if not os.path.isfile(path):
        raise SystemExit(f"Input file not found: {path}")

    log("config", "🔧", f"ticker={ticker}, synthetic={synthetic}, multiplier={multiplier}")
    log("config", "🔧", f"file={path}, publish={args.publish}")

    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    bars: List[Dict[str, Any]] = payload.get("bars") or []
    log("input", "ℹ️", f"Loaded {len(bars)} bars from file.")

    ohlc: List[Dict[str, Any]] = []
    bins_raw: Dict[int, float] = {}
    bins_tv: Dict[int, float] = {}

    for b in bars:
        t = b.get("t")
        o = b.get("o")
        h = b.get("h")
        l = b.get("l")
        c = b.get("c")
        v = b.get("v")

        ohlc.append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": v})
        accumulate_raw(bins_raw, c, v, multiplier)
        accumulate_tv(bins_tv, l, h, v, multiplier)

    if bins_raw:
        price_min = min(bins_raw.keys())
        price_max = max(bins_raw.keys())
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

    mode = args.publish
    if mode in ("raw", "both"):
        publish_to_market({"symbol": synthetic, "mode": "raw", "buckets": out["buckets_raw"]})
    if mode in ("tv", "both"):
        publish_to_market({"symbol": synthetic, "mode": "tv", "buckets": out["buckets_tv"]})

    log("done", "✅", f"Volume profile built for {synthetic}")


if __name__ == "__main__":
    main()