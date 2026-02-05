#!/usr/bin/env python3
"""
VP Quick Load - Fast Volume Profile Builder

Downloads SPY minute bars from Polygon and streams to Redis progressively.
Supports two accumulation modes:

  RAW: Volume placed at VWAP price (single point per bar)
  TV:  Volume distributed across bar's high-low range (TradingView style)

Usage:
    python vp_quick_load.py --days 30              # Last 30 days, both modes
    python vp_quick_load.py --days 30 --mode raw   # RAW only
    python vp_quick_load.py --days 30 --mode tv    # TV only
    python vp_quick_load.py --years 1              # Last year
"""

import argparse
import asyncio
import json
import os
import sys
import urllib.request
import urllib.error
import time
from datetime import datetime, timedelta, date

from redis.asyncio import Redis

POLYGON_BASE = "https://api.polygon.io"
REDIS_URL = os.environ.get("MARKET_REDIS_URL", "redis://127.0.0.1:6380")

# Redis keys for each mode
REDIS_KEYS = {
    "raw": "massive:volume_profile:spx",
    "tv": "massive:volume_profile:spx:tv",
}
REDIS_META_KEY = "massive:volume_profile:spx:meta"

# TV smoothing: number of microbins to distribute volume across bar range
TV_MICROBINS = 30


class VPQuickLoader:
    def __init__(self, api_key: str, mode: str = "both"):
        self.api_key = api_key
        self.mode = mode  # "raw", "tv", or "both"
        self.redis: Redis | None = None

        # Separate profiles for each mode
        self.profile_raw: dict[int, int] = {}
        self.profile_tv: dict[int, int] = {}

        self.days_processed = 0
        self.total_volume = 0

    async def connect(self):
        self.redis = Redis.from_url(REDIS_URL, decode_responses=True)
        print(f"Connected to Redis at {REDIS_URL}")

    async def close(self):
        if self.redis:
            await self.redis.aclose()

    def spy_to_spx_bucket(self, spy_price: float) -> int:
        """Convert SPY price to SPX bucket (price in cents, rounded to $0.10)."""
        spy_cents = int(round(spy_price * 100))
        spx_cents = spy_cents * 10  # SPY -> SPX scaling
        return (spx_cents // 10) * 10  # Round to nearest 10 cents

    def fetch_day(self, ticker: str, date_str: str) -> list[dict]:
        """Fetch minute bars for a single day."""
        url = f"{POLYGON_BASE}/v2/aggs/ticker/{ticker}/range/1/minute/{date_str}/{date_str}?apiKey={self.api_key}&limit=50000&sort=asc"

        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'MarketSwarm/1.0')

            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode('utf-8'))
                return data.get("results", [])

        except urllib.error.HTTPError as e:
            if e.code == 429:
                print("  Rate limited, waiting 60s...")
                time.sleep(60)
                return self.fetch_day(ticker, date_str)
            return []
        except Exception:
            return []

    def accumulate_raw(self, bar: dict):
        """RAW mode: Volume at VWAP price (or mid if no VWAP)."""
        price = bar.get("vw") or ((bar.get("h", 0) + bar.get("l", 0)) / 2)
        volume = bar.get("v", 0)
        if volume <= 0 or price <= 0:
            return

        bucket = self.spy_to_spx_bucket(price)
        self.profile_raw[bucket] = self.profile_raw.get(bucket, 0) + int(volume)

    def accumulate_tv(self, bar: dict):
        """TV mode: Volume distributed across bar's high-low range."""
        low = bar.get("l")
        high = bar.get("h")
        volume = bar.get("v", 0)

        if low is None or high is None or volume <= 0:
            return
        if high <= low:
            # Single price bar - treat like raw
            bucket = self.spy_to_spx_bucket((high + low) / 2)
            self.profile_tv[bucket] = self.profile_tv.get(bucket, 0) + int(volume)
            return

        # Distribute volume across microbins within the bar's range
        step = (high - low) / TV_MICROBINS
        vol_per_bin = volume / TV_MICROBINS

        for i in range(TV_MICROBINS):
            price = low + i * step
            bucket = self.spy_to_spx_bucket(price)
            self.profile_tv[bucket] = self.profile_tv.get(bucket, 0) + int(vol_per_bin)

    def process_bars(self, bars: list[dict]):
        """Process bars and accumulate volume based on mode."""
        for bar in bars:
            volume = bar.get("v", 0)
            if volume <= 0:
                continue

            if self.mode in ("raw", "both"):
                self.accumulate_raw(bar)

            if self.mode in ("tv", "both"):
                self.accumulate_tv(bar)

            self.total_volume += int(volume)

    async def flush_to_redis(self, clear_first: bool = False):
        """Save accumulated profiles to Redis."""
        pipe = self.redis.pipeline()

        # Flush RAW profile
        if self.mode in ("raw", "both") and self.profile_raw:
            if clear_first:
                pipe.delete(REDIS_KEYS["raw"])
            for bucket, volume in self.profile_raw.items():
                pipe.hincrby(REDIS_KEYS["raw"], str(bucket), volume)

        # Flush TV profile
        if self.mode in ("tv", "both") and self.profile_tv:
            if clear_first:
                pipe.delete(REDIS_KEYS["tv"])
            for bucket, volume in self.profile_tv.items():
                pipe.hincrby(REDIS_KEYS["tv"], str(bucket), volume)

        # Update metadata
        all_buckets = list(self.profile_raw.keys()) or list(self.profile_tv.keys())
        if all_buckets:
            pipe.hset(REDIS_META_KEY, mapping={
                "last_updated": datetime.now().isoformat(),
                "mode": self.mode,
                "levels_raw": len(self.profile_raw),
                "levels_tv": len(self.profile_tv),
                "total_volume": self.total_volume,
                "min_price": min(all_buckets) / 100 if all_buckets else 0,
                "max_price": max(all_buckets) / 100 if all_buckets else 0,
                "days_processed": self.days_processed,
                "tv_microbins": TV_MICROBINS,
            })

        await pipe.execute()

    async def load(self, days: int = None, years: int = None, clear: bool = True):
        """Load VP data from Polygon."""
        end_date = date.today()

        if years:
            start_date = end_date - timedelta(days=years * 365)
        elif days:
            start_date = end_date - timedelta(days=days)
        else:
            start_date = end_date - timedelta(days=30)

        print(f"Loading SPY data from {start_date} to {end_date}")
        print(f"Mode: {self.mode.upper()}")

        if clear:
            if self.mode in ("raw", "both"):
                await self.redis.delete(REDIS_KEYS["raw"])
            if self.mode in ("tv", "both"):
                await self.redis.delete(REDIS_KEYS["tv"])
            await self.redis.delete(REDIS_META_KEY)
            print("Cleared existing VP data")

        current = start_date
        flush_interval = 50  # Flush to Redis every 50 days

        while current <= end_date:
            # Skip weekends
            if current.weekday() >= 5:
                current += timedelta(days=1)
                continue

            date_str = current.strftime("%Y-%m-%d")
            bars = self.fetch_day("SPY", date_str)

            if bars:
                self.process_bars(bars)
                self.days_processed += 1

                if self.days_processed % 10 == 0:
                    levels = len(self.profile_raw) if self.mode in ("raw", "both") else len(self.profile_tv)
                    print(f"  {self.days_processed} days ({current}): {levels:,} levels, {self.total_volume:,.0f} volume")

                # Periodic flush to Redis
                if self.days_processed % flush_interval == 0:
                    await self.flush_to_redis(clear_first=False)
                    print(f"  -> Flushed to Redis")
                    self.profile_raw.clear()
                    self.profile_tv.clear()

            # Rate limit: ~4 requests/second
            time.sleep(0.25)
            current += timedelta(days=1)

        # Final flush
        await self.flush_to_redis(clear_first=False)

        print(f"\nDone: {self.days_processed} days, {self.total_volume:,.0f} total volume")
        if self.mode in ("raw", "both"):
            count = await self.redis.hlen(REDIS_KEYS["raw"])
            print(f"  RAW levels: {count:,}")
        if self.mode in ("tv", "both"):
            count = await self.redis.hlen(REDIS_KEYS["tv"])
            print(f"  TV levels: {count:,}")


async def main():
    parser = argparse.ArgumentParser(description="VP Quick Load")
    parser.add_argument("--days", type=int, help="Number of days to load")
    parser.add_argument("--years", type=int, help="Number of years to load")
    parser.add_argument("--no-clear", action="store_true", help="Don't clear existing data")
    parser.add_argument(
        "--mode",
        choices=["raw", "tv", "both"],
        default="both",
        help="Accumulation mode: raw (VWAP), tv (distributed), or both (default)"
    )
    args = parser.parse_args()

    api_key = os.environ.get("POLYGON_API_KEY") or os.environ.get("MASSIVE_API_KEY")
    if not api_key:
        print("Error: POLYGON_API_KEY or MASSIVE_API_KEY required")
        sys.exit(1)

    loader = VPQuickLoader(api_key, mode=args.mode)
    await loader.connect()

    try:
        await loader.load(
            days=args.days,
            years=args.years,
            clear=not args.no_clear
        )
    finally:
        await loader.close()


if __name__ == "__main__":
    asyncio.run(main())
