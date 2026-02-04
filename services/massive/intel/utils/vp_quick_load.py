#!/usr/bin/env python3
"""
VP Quick Load - Fast Volume Profile Builder

Downloads SPY minute bars from Polygon and streams to Redis progressively.
Use this for quick VP population during development.

Usage:
    python vp_quick_load.py --days 30      # Last 30 days
    python vp_quick_load.py --years 1      # Last year
    python vp_quick_load.py --years 15     # Full history (slow)
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
from pathlib import Path

from redis.asyncio import Redis

POLYGON_BASE = "https://api.polygon.io"
REDIS_KEY = "massive:volume_profile:spx"
REDIS_META_KEY = "massive:volume_profile:spx:meta"
REDIS_URL = os.environ.get("MARKET_REDIS_URL", "redis://127.0.0.1:6380")


class VPQuickLoader:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.redis: Redis | None = None
        self.profile: dict[int, int] = {}  # bucket -> volume
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
        except Exception as e:
            return []

    def process_bars(self, bars: list[dict]):
        """Process bars and accumulate volume."""
        for bar in bars:
            price = bar.get("vw") or ((bar.get("h", 0) + bar.get("l", 0)) / 2)
            volume = bar.get("v", 0)
            if volume <= 0:
                continue

            bucket = self.spy_to_spx_bucket(price)
            if bucket not in self.profile:
                self.profile[bucket] = 0
            self.profile[bucket] += int(volume)
            self.total_volume += int(volume)

    async def flush_to_redis(self, clear_first: bool = False):
        """Save accumulated profile to Redis."""
        if not self.profile:
            return

        pipe = self.redis.pipeline()

        if clear_first:
            pipe.delete(REDIS_KEY)

        for bucket, volume in self.profile.items():
            pipe.hincrby(REDIS_KEY, str(bucket), volume)

        # Update metadata
        all_buckets = list(self.profile.keys())
        pipe.hset(REDIS_META_KEY, mapping={
            "last_updated": datetime.now().isoformat(),
            "levels": len(all_buckets),
            "total_volume": self.total_volume,
            "min_price": min(all_buckets) / 100 if all_buckets else 0,
            "max_price": max(all_buckets) / 100 if all_buckets else 0,
            "days_processed": self.days_processed,
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

        if clear:
            await self.redis.delete(REDIS_KEY)
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
                    print(f"  {self.days_processed} days ({current}): {len(self.profile):,} levels, {self.total_volume:,.0f} volume")

                # Periodic flush to Redis
                if self.days_processed % flush_interval == 0:
                    await self.flush_to_redis(clear_first=False)
                    print(f"  -> Flushed to Redis")
                    self.profile.clear()

            # Rate limit: ~4 requests/second
            time.sleep(0.25)
            current += timedelta(days=1)

        # Final flush
        await self.flush_to_redis(clear_first=False)
        print(f"\nDone: {self.days_processed} days, {self.total_volume:,.0f} total volume")


async def main():
    parser = argparse.ArgumentParser(description="VP Quick Load")
    parser.add_argument("--days", type=int, help="Number of days to load")
    parser.add_argument("--years", type=int, help="Number of years to load")
    parser.add_argument("--no-clear", action="store_true", help="Don't clear existing data")
    args = parser.parse_args()

    api_key = os.environ.get("POLYGON_API_KEY") or os.environ.get("MASSIVE_API_KEY")
    if not api_key:
        print("Error: POLYGON_API_KEY or MASSIVE_API_KEY required")
        sys.exit(1)

    loader = VPQuickLoader(api_key)
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
