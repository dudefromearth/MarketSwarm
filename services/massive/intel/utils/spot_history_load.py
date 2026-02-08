#!/usr/bin/env python3
"""
Spot History Load - Load historical spot data into trail

Downloads SPX/NDX minute bars from Polygon and populates the spot trail in Redis.
Use this to backfill historical data for the Dealer Gravity chart.

Usage:
    python spot_history_load.py --days 14      # Last 14 days (default)
    python spot_history_load.py --days 30      # Last 30 days
    python spot_history_load.py --symbol SPX   # SPX only (default)
    python spot_history_load.py --symbol NDX   # NDX only
    python spot_history_load.py --symbol all   # Both SPX and NDX
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

# Symbol mapping: Polygon ticker -> Redis key
SYMBOLS = {
    "SPX": {"polygon": "I:SPX", "redis_key": "massive:model:spot:I:SPX:trail"},
    "NDX": {"polygon": "I:NDX", "redis_key": "massive:model:spot:I:NDX:trail"},
}


class SpotHistoryLoader:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.redis: Redis | None = None
        self.points_loaded = 0

    async def connect(self):
        self.redis = Redis.from_url(REDIS_URL, decode_responses=True)
        print(f"Connected to Redis at {REDIS_URL}")

    async def close(self):
        if self.redis:
            await self.redis.aclose()

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
            elif e.code == 404:
                return []  # No data for this day (holiday, etc.)
            print(f"  HTTP error {e.code} for {date_str}")
            return []
        except Exception as e:
            print(f"  Error fetching {date_str}: {e}")
            return []

    async def load_symbol(self, symbol: str, days: int, clear: bool = False):
        """Load historical data for a symbol."""
        config = SYMBOLS.get(symbol.upper())
        if not config:
            print(f"Unknown symbol: {symbol}")
            return

        polygon_ticker = config["polygon"]
        redis_key = config["redis_key"]

        print(f"\nLoading {symbol} ({polygon_ticker}) -> {redis_key}")

        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        print(f"Date range: {start_date} to {end_date}")

        if clear:
            await self.redis.delete(redis_key)
            print("Cleared existing trail data")

        current = start_date
        days_processed = 0
        points_added = 0
        batch = []
        batch_size = 1000

        while current <= end_date:
            # Skip weekends
            if current.weekday() >= 5:
                current += timedelta(days=1)
                continue

            date_str = current.strftime("%Y-%m-%d")
            bars = self.fetch_day(polygon_ticker, date_str)

            if bars:
                for bar in bars:
                    # bar: { t: timestamp_ms, o, h, l, c, v, vw, n }
                    ts_ms = bar.get("t", 0)
                    ts_sec = ts_ms / 1000

                    # Use VWAP if available, else close price
                    value = bar.get("vw") or bar.get("c")
                    if not value:
                        continue

                    # Create spot snapshot
                    snapshot = json.dumps({
                        "symbol": polygon_ticker,
                        "value": round(value, 2),
                        "ts": datetime.utcfromtimestamp(ts_sec).isoformat() + "+00:00",
                        "source": "polygon/historical",
                        "timeframe": "1m",
                    })

                    batch.append((ts_sec, snapshot))
                    points_added += 1

                    # Flush batch periodically
                    if len(batch) >= batch_size:
                        pipe = self.redis.pipeline()
                        for score, member in batch:
                            pipe.zadd(redis_key, {member: score})
                        await pipe.execute()
                        batch.clear()

                days_processed += 1
                if days_processed % 5 == 0:
                    print(f"  {days_processed} days processed, {points_added:,} points")

            # Rate limit: ~4 requests/second
            time.sleep(0.25)
            current += timedelta(days=1)

        # Final flush
        if batch:
            pipe = self.redis.pipeline()
            for score, member in batch:
                pipe.zadd(redis_key, {member: score})
            await pipe.execute()

        # Set TTL (15 days)
        await self.redis.expire(redis_key, 1296000)

        self.points_loaded += points_added
        print(f"  Loaded {points_added:,} points for {symbol} ({days_processed} trading days)")

    async def load(self, symbols: list[str], days: int, clear: bool = True):
        """Load historical data for specified symbols."""
        for symbol in symbols:
            await self.load_symbol(symbol, days, clear)

        print(f"\nTotal: {self.points_loaded:,} points loaded")


async def main():
    parser = argparse.ArgumentParser(description="Load historical spot data")
    parser.add_argument("--days", type=int, default=14, help="Number of days to load (default: 14)")
    parser.add_argument("--symbol", type=str, default="SPX", help="Symbol to load: SPX, NDX, or 'all' (default: SPX)")
    parser.add_argument("--no-clear", action="store_true", help="Don't clear existing data")
    args = parser.parse_args()

    api_key = os.environ.get("POLYGON_API_KEY") or os.environ.get("MASSIVE_API_KEY")
    if not api_key:
        print("Error: POLYGON_API_KEY or MASSIVE_API_KEY required")
        sys.exit(1)

    # Determine symbols to load
    if args.symbol.lower() == "all":
        symbols = list(SYMBOLS.keys())
    else:
        symbols = [args.symbol.upper()]

    loader = SpotHistoryLoader(api_key)
    await loader.connect()

    try:
        await loader.load(
            symbols=symbols,
            days=args.days,
            clear=not args.no_clear
        )
    finally:
        await loader.close()


if __name__ == "__main__":
    asyncio.run(main())
