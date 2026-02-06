#!/usr/bin/env python3
"""
Dealer Gravity Incremental Worker

Handles incremental volume updates and artifact rebuilding.
Subscribes to live bar updates and maintains the Dealer Gravity
artifacts in real-time.

Architecture:
  - Listens for new bars via Redis pub/sub or polling
  - Updates raw data on disk
  - Rebuilds artifact when threshold reached
  - Pushes final artifact to Redis (delivery layer)

This worker maintains the Dealer Gravity service layer's
authoritative disk storage while keeping Redis artifacts fresh.
"""

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from redis.asyncio import Redis

from dg_artifact_builder import DGArtifactBuilder

# Paths
DATA_DIR = Path(__file__).parent.parent.parent.parent.parent / "data" / "dealer_gravity"
RAW_DIR = DATA_DIR / "raw"

# Redis
REDIS_URL = os.environ.get("MARKET_REDIS_URL", "redis://127.0.0.1:6380")

# Update thresholds
MIN_BARS_BEFORE_REBUILD = 10      # Minimum bars before triggering rebuild
MAX_SECONDS_BETWEEN_REBUILD = 60  # Force rebuild after this many seconds
TV_MICROBINS = 30


class DGIncrementalWorker:
    """
    Processes incremental volume updates and maintains artifacts.

    The worker accumulates new bars and periodically rebuilds
    the Dealer Gravity artifact, ensuring the Redis delivery
    layer stays fresh while disk remains authoritative.
    """

    def __init__(self, symbol: str = "SPX", bucket_size: int = 1):
        self.symbol = symbol.upper()
        self.bucket_size = bucket_size
        self.redis: Optional[Redis] = None
        self.builder = DGArtifactBuilder(symbol, bucket_size)

        # Incremental state
        self.pending_bars: list[dict] = []
        self.last_rebuild_time = 0

        # Ensure directories exist
        RAW_DIR.mkdir(parents=True, exist_ok=True)

    async def connect(self):
        """Connect to Redis."""
        self.redis = Redis.from_url(REDIS_URL, decode_responses=True)
        await self.builder.connect()
        print(f"[DG Worker] Connected to Redis at {REDIS_URL}")

    async def close(self):
        """Close connections."""
        if self.redis:
            await self.redis.aclose()
        await self.builder.close()

    def spy_to_bucket_index(self, spy_price: float) -> int:
        """Convert SPY price to SPX bucket index."""
        spx_price = spy_price * 10  # SPY -> SPX
        return int(spx_price // self.bucket_size)

    def accumulate_bar_tv(self, bar: dict, profile: dict[int, int]):
        """
        Accumulate bar volume using TV (microbin spreading) method.

        Distributes volume across the bar's high-low range.
        """
        low = bar.get("l")
        high = bar.get("h")
        volume = bar.get("v", 0)

        if low is None or high is None or volume <= 0:
            return

        if high <= low:
            # Point bar - all volume at midpoint
            idx = self.spy_to_bucket_index((high + low) / 2)
            profile[idx] = profile.get(idx, 0) + int(volume)
            return

        # Spread volume across microbins
        step = (high - low) / TV_MICROBINS
        vol_per_bin = volume / TV_MICROBINS

        for i in range(TV_MICROBINS):
            price = low + i * step
            idx = self.spy_to_bucket_index(price)
            profile[idx] = profile.get(idx, 0) + int(vol_per_bin)

    def load_raw_profile(self) -> dict:
        """Load current raw profile from disk."""
        raw_file = RAW_DIR / "volume_bars.json"
        if not raw_file.exists():
            return {
                "raw_profile": {},
                "tv_profile": {},
                "bucket_size": self.bucket_size,
                "days_processed": 0,
                "total_volume": 0,
                "updated_at": None
            }

        with open(raw_file, "r") as f:
            return json.load(f)

    def save_raw_profile(self, data: dict):
        """Save raw profile to disk."""
        raw_file = RAW_DIR / "volume_bars.json"
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        with open(raw_file, "w") as f:
            json.dump(data, f)

    async def apply_incremental(self, new_bars: list[dict]):
        """
        Apply new bars to the volume profile and rebuild artifact.

        1. Load current raw data from disk
        2. Append new bars to raw data
        3. Re-run transform pipeline
        4. Build final artifact
        5. Push to Redis
        """
        if not new_bars:
            return

        # 1. Load current raw data
        raw_data = self.load_raw_profile()
        tv_profile = {int(k): v for k, v in raw_data.get("tv_profile", {}).items()}
        total_volume = raw_data.get("total_volume", 0)

        # 2. Accumulate new bars
        for bar in new_bars:
            volume = bar.get("v", 0)
            if volume > 0:
                self.accumulate_bar_tv(bar, tv_profile)
                total_volume += int(volume)

        # 3. Save updated raw data to disk
        raw_data["tv_profile"] = {str(k): v for k, v in tv_profile.items()}
        raw_data["total_volume"] = total_volume
        self.save_raw_profile(raw_data)

        print(f"[DG Worker] Applied {len(new_bars)} bars, total volume: {total_volume:,.0f}")

        # 4. Rebuild and publish artifact
        await self.builder.build_and_publish()

        self.last_rebuild_time = time.time()
        self.pending_bars = []

    def should_rebuild(self) -> bool:
        """Check if we should trigger a rebuild."""
        if len(self.pending_bars) >= MIN_BARS_BEFORE_REBUILD:
            return True

        if self.last_rebuild_time > 0:
            elapsed = time.time() - self.last_rebuild_time
            if elapsed >= MAX_SECONDS_BETWEEN_REBUILD and self.pending_bars:
                return True

        return False

    async def process_bar(self, bar: dict):
        """Process a single incoming bar."""
        self.pending_bars.append(bar)

        if self.should_rebuild():
            await self.apply_incremental(self.pending_bars)

    async def subscribe_to_bars(self, stop_event: asyncio.Event):
        """
        Subscribe to live bar updates via Redis pub/sub.

        Listens for candle updates and processes them incrementally.
        """
        pubsub = self.redis.pubsub()
        await pubsub.subscribe("massive:pubsub:candles")

        print("[DG Worker] Subscribed to candle updates")

        try:
            while not stop_event.is_set():
                try:
                    message = await asyncio.wait_for(
                        pubsub.get_message(ignore_subscribe_messages=True),
                        timeout=1.0
                    )

                    if message and message["type"] == "message":
                        data = json.loads(message["data"])

                        # Extract SPY bars if present
                        spy_bars = data.get("SPY", [])
                        for bar in spy_bars:
                            await self.process_bar(bar)

                except asyncio.TimeoutError:
                    # Check if we need time-based rebuild
                    if self.should_rebuild():
                        await self.apply_incremental(self.pending_bars)

        finally:
            await pubsub.unsubscribe("massive:pubsub:candles")
            await pubsub.close()

    async def poll_for_updates(self, stop_event: asyncio.Event, interval: float = 5.0):
        """
        Alternative: Poll Redis for spot updates and trigger rebuilds.

        Use this when pub/sub isn't available or for less frequent updates.
        """
        print(f"[DG Worker] Polling for updates every {interval}s")

        while not stop_event.is_set():
            try:
                # Check if spot has changed significantly
                spot = await self.builder.fetch_spot()

                # Trigger periodic artifact refresh
                elapsed = time.time() - self.last_rebuild_time
                if elapsed >= MAX_SECONDS_BETWEEN_REBUILD:
                    await self.builder.build_and_publish(spot=spot)
                    self.last_rebuild_time = time.time()

            except Exception as e:
                print(f"[DG Worker] Poll error: {e}")

            await asyncio.sleep(interval)

    async def run(self, mode: str = "poll", stop_event: asyncio.Event = None):
        """
        Run the incremental worker.

        Args:
            mode: "subscribe" for pub/sub, "poll" for periodic polling
            stop_event: Event to signal shutdown
        """
        if stop_event is None:
            stop_event = asyncio.Event()

        print(f"[DG Worker] Starting in {mode} mode")

        if mode == "subscribe":
            await self.subscribe_to_bars(stop_event)
        else:
            await self.poll_for_updates(stop_event)


async def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Dealer Gravity Incremental Worker")
    parser.add_argument("--mode", choices=["subscribe", "poll"], default="poll",
                        help="Update mode: subscribe to pub/sub or poll periodically")
    parser.add_argument("--interval", type=float, default=60.0,
                        help="Poll interval in seconds (poll mode only)")
    args = parser.parse_args()

    worker = DGIncrementalWorker()
    await worker.connect()

    stop_event = asyncio.Event()

    # Handle signals
    import signal
    def handle_signal(sig, frame):
        print("\n[DG Worker] Shutting down...")
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        await worker.run(mode=args.mode, stop_event=stop_event)
    finally:
        await worker.close()


if __name__ == "__main__":
    asyncio.run(main())
