#!/usr/bin/env python3
"""
Backfill Spot Trail Data

Fetches historical minute bars from Polygon and populates the Redis spot trail
for the Dealer Gravity chart. Fills in missing days to provide 5+ days of data.

Usage:
    python scripts/backfill_spot_trail.py --days 5
    python scripts/backfill_spot_trail.py --days 5 --symbol I:SPX
"""

import asyncio
import json
import os
import sys
import urllib.request
import urllib.error
import time
import argparse
from datetime import datetime, timedelta, date
from pathlib import Path

from redis.asyncio import Redis

# Configuration
POLYGON_BASE = "https://api.polygon.io"
REDIS_URL = "redis://127.0.0.1:6380"

# Symbol mapping: Polygon ticker -> Redis key symbol
SYMBOL_MAP = {
    "I:SPX": "SPX",
    "I:NDX": "NDX",
    "SPX": "SPX",
    "NDX": "NDX",
}


class SpotTrailBackfill:
    def __init__(self, api_key: str, redis_url: str = REDIS_URL):
        self.api_key = api_key
        self.redis_url = redis_url
        self.redis: Redis | None = None

    async def connect_redis(self):
        self.redis = Redis.from_url(self.redis_url, decode_responses=True)
        print(f"Connected to Redis at {self.redis_url}")

    async def close(self):
        if self.redis:
            await self.redis.close()

    def fetch_day_bars(self, ticker: str, date_str: str, timespan: str = "minute") -> list[dict]:
        """Fetch minute bars for a single day using urllib."""
        # For indices, use the index ticker format
        polygon_ticker = ticker
        if ticker.startswith("I:"):
            polygon_ticker = ticker  # Polygon accepts I:SPX format

        url = f"{POLYGON_BASE}/v2/aggs/ticker/{polygon_ticker}/range/1/{timespan}/{date_str}/{date_str}?apiKey={self.api_key}&limit=50000&sort=asc"

        print(f"  Fetching {ticker} for {date_str}...")

        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'MarketSwarm/1.0')

            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode('utf-8'))
                results = data.get("results", [])
                print(f"    Got {len(results)} bars")
                return results

        except urllib.error.HTTPError as e:
            if e.code == 429:
                print("  Rate limited, waiting 60s...")
                time.sleep(60)
                return self.fetch_day_bars(ticker, date_str, timespan)
            else:
                print(f"  Failed to fetch {date_str}: HTTP {e.code}")
                return []

        except Exception as e:
            print(f"  Failed to fetch {date_str}: {e}")
            return []

    async def backfill_symbol(self, symbol: str, days: int):
        """Backfill trail data for a single symbol."""
        print(f"\nBackfilling {symbol} for {days} days...")

        # Determine the Redis key
        redis_symbol = symbol
        if symbol in SYMBOL_MAP:
            redis_symbol = symbol
        trail_key = f"massive:model:spot:{symbol}:trail"

        # Get existing data range
        existing_count = await self.redis.zcard(trail_key)
        print(f"  Existing trail entries: {existing_count}")

        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        total_added = 0
        current_date = start_date

        while current_date <= end_date:
            # Skip weekends
            if current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue

            date_str = current_date.strftime("%Y-%m-%d")
            bars = self.fetch_day_bars(symbol, date_str)

            if bars:
                # Add each bar to the trail
                entries = {}
                for bar in bars:
                    # bar has: t (timestamp ms), o, h, l, c, v, vw, n
                    ts_ms = bar.get("t", 0)
                    ts_sec = ts_ms / 1000

                    # Use close price as spot value
                    value = bar.get("c", bar.get("vw", 0))
                    if not value:
                        continue

                    # Create the trail entry JSON
                    entry = {
                        "symbol": symbol,
                        "value": value,
                        "ts": datetime.utcfromtimestamp(ts_sec).isoformat() + "+00:00",
                        "source": "backfill",
                        "timeframe": "HISTORICAL"
                    }
                    entries[json.dumps(entry)] = ts_sec

                if entries:
                    # Add to Redis sorted set
                    await self.redis.zadd(trail_key, entries)
                    total_added += len(entries)
                    print(f"    Added {len(entries)} entries for {date_str}")

            # Rate limiting - be nice to Polygon
            time.sleep(0.25)
            current_date += timedelta(days=1)

        # Update final count
        final_count = await self.redis.zcard(trail_key)
        print(f"\n  Backfill complete for {symbol}:")
        print(f"    Added: {total_added} entries")
        print(f"    Total trail entries: {final_count}")

    async def run(self, symbols: list[str], days: int):
        """Run backfill for all symbols."""
        await self.connect_redis()

        try:
            for symbol in symbols:
                await self.backfill_symbol(symbol, days)
        finally:
            await self.close()


async def main():
    parser = argparse.ArgumentParser(description="Backfill spot trail data from Polygon")
    parser.add_argument("--days", type=int, default=5, help="Number of days to backfill (default: 5)")
    parser.add_argument("--symbol", type=str, help="Single symbol to backfill (default: I:SPX and I:NDX)")
    parser.add_argument("--api-key", type=str, help="Polygon API key (or set MASSIVE_API_KEY env var)")
    args = parser.parse_args()

    # Get API key
    api_key = args.api_key or os.environ.get("MASSIVE_API_KEY")
    if not api_key:
        # Try to read from truth.json
        truth_path = Path(__file__).parent / "truth.json"
        if truth_path.exists():
            with open(truth_path) as f:
                truth = json.load(f)
                api_key = truth.get("components", {}).get("massive", {}).get("env", {}).get("MASSIVE_API_KEY")

    if not api_key:
        print("Error: No API key found. Set MASSIVE_API_KEY or use --api-key")
        sys.exit(1)

    # Determine symbols
    if args.symbol:
        symbols = [args.symbol]
    else:
        symbols = ["I:SPX", "I:NDX"]

    print(f"Backfilling {args.days} days of data for: {', '.join(symbols)}")
    print(f"Using API key: {api_key[:8]}...")

    backfiller = SpotTrailBackfill(api_key)
    await backfiller.run(symbols, args.days)

    print("\nDone! Refresh the Dealer Gravity chart to see the data.")


if __name__ == "__main__":
    asyncio.run(main())
