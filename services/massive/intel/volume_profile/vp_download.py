#!/usr/bin/env python3
"""
Volume Profile - Historical Data Download

Downloads 15 years of SPY minute bars from Polygon.
Buckets volume by 1-cent price levels.
Stores cumulative profile in Redis, scaled to SPX.

SPY $0.01 → SPX $0.10 (approximate 10x scaling)
"""

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

# Add project root to path
ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.logutil import LogUtil

# Configuration
POLYGON_BASE = "https://api.polygon.io"
YEARS_OF_HISTORY = 15
REDIS_KEY = "massive:volume_profile:spx"
REDIS_URL = "redis://127.0.0.1:6380"


class VolumeProfileDownloader:
    def __init__(self, api_key: str, logger):
        self.api_key = api_key
        self.logger = logger
        self.redis: Redis | None = None

        # Volume profile: price_cents -> volume
        # Price is SPY price in cents (e.g., 69750 = $697.50)
        self.profile: dict[int, int] = {}

    async def connect_redis(self):
        self.redis = Redis.from_url(REDIS_URL, decode_responses=True)
        self.logger.info(f"Connected to Redis at {REDIS_URL}", emoji="🔗")

    async def close(self):
        if self.redis:
            await self.redis.close()

    def spy_to_spx_cents(self, spy_cents: int) -> int:
        """Convert SPY price in cents to SPX price in cents (10x scale)."""
        return spy_cents * 10

    def fetch_day_bars(self, ticker: str, date_str: str) -> list[dict]:
        """Fetch minute bars for a single day using urllib."""
        url = f"{POLYGON_BASE}/v2/aggs/ticker/{ticker}/range/1/minute/{date_str}/{date_str}?apiKey={self.api_key}&limit=50000&sort=asc"

        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'MarketSwarm/1.0')

            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode('utf-8'))
                return data.get("results", [])

        except urllib.error.HTTPError as e:
            if e.code == 429:
                self.logger.warning("Rate limited, waiting 60s...", emoji="⏳")
                time.sleep(60)
                return self.fetch_day_bars(ticker, date_str)
            else:
                self.logger.warning(f"Failed to fetch {date_str}: HTTP {e.code}", emoji="⚠️")
                return []

        except Exception as e:
            self.logger.warning(f"Failed to fetch {date_str}: {e}", emoji="⚠️")
            return []

    def process_bars(self, bars: list[dict]):
        """Process minute bars and add volume to profile buckets."""
        for bar in bars:
            # Use VWAP if available, otherwise average of high/low
            if "vw" in bar and bar["vw"]:
                price = bar["vw"]
            else:
                price = (bar["h"] + bar["l"]) / 2

            volume = bar.get("v", 0)
            if volume <= 0:
                continue

            # Convert to cents and bucket
            spy_cents = int(round(price * 100))

            if spy_cents not in self.profile:
                self.profile[spy_cents] = 0
            self.profile[spy_cents] += int(volume)

    async def download_historical(self):
        """Download 15 years of SPY data."""
        end_date = date.today()
        start_date = end_date - timedelta(days=YEARS_OF_HISTORY * 365)

        self.logger.info(f"Downloading SPY data from {start_date} to {end_date}", emoji="📥")
        self.logger.info(f"This will take a while...", emoji="⏳")

        current = start_date
        days_processed = 0
        total_volume = 0

        while current <= end_date:
            # Skip weekends
            if current.weekday() >= 5:
                current += timedelta(days=1)
                continue

            date_str = current.strftime("%Y-%m-%d")
            bars = self.fetch_day_bars("SPY", date_str)

            if bars:
                self.process_bars(bars)
                days_processed += 1
                day_volume = sum(b.get("v", 0) for b in bars)
                total_volume += day_volume

                if days_processed % 50 == 0:
                    self.logger.info(
                        f"Processed {days_processed} days ({current}), {len(self.profile):,} price levels, "
                        f"{total_volume:,.0f} total volume",
                        emoji="📊"
                    )

            # Rate limit: 5 requests per second for free tier
            time.sleep(0.25)
            current += timedelta(days=1)

        self.logger.ok(
            f"Download complete: {days_processed} days, {len(self.profile):,} price levels",
            emoji="✅"
        )

    async def save_to_redis(self):
        """Save profile to Redis, scaled to SPX."""
        if not self.redis:
            await self.connect_redis()

        # Convert SPY cents to SPX cents (10x)
        spx_profile = {}
        for spy_cents, volume in self.profile.items():
            spx_cents = self.spy_to_spx_cents(spy_cents)
            # Bucket to nearest 10 cents (SPX $0.10 levels)
            bucket = (spx_cents // 10) * 10
            if bucket not in spx_profile:
                spx_profile[bucket] = 0
            spx_profile[bucket] += volume

        # Store as hash: price_cents -> volume
        pipe = self.redis.pipeline()
        pipe.delete(REDIS_KEY)

        for price_cents, volume in spx_profile.items():
            pipe.hset(REDIS_KEY, str(price_cents), volume)

        # Store metadata
        pipe.hset(f"{REDIS_KEY}:meta", mapping={
            "last_updated": datetime.now().isoformat(),
            "levels": len(spx_profile),
            "total_volume": sum(spx_profile.values()),
            "min_price": min(spx_profile.keys()),
            "max_price": max(spx_profile.keys()),
        })

        await pipe.execute()

        self.logger.ok(
            f"Saved {len(spx_profile):,} SPX price levels to Redis",
            emoji="💾"
        )

    async def run(self):
        """Main entry point."""
        try:
            await self.connect_redis()
            await self.download_historical()
            await self.save_to_redis()
        finally:
            await self.close()


async def main():
    logger = LogUtil("vp-download")

    api_key = os.environ.get("POLYGON_API_KEY") or os.environ.get("MASSIVE_API_KEY")
    if not api_key:
        logger.error("POLYGON_API_KEY or MASSIVE_API_KEY required", emoji="❌")
        sys.exit(1)

    downloader = VolumeProfileDownloader(api_key, logger)
    await downloader.run()


if __name__ == "__main__":
    asyncio.run(main())
