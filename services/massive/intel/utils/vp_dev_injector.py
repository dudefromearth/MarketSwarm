#!/usr/bin/env python3
"""
VP Dev Injector - Development tool for Volume Profile

Quick injection of:
- SPX spot prices
- VP buckets (nodes, wells, ranges)
- Structure presets for testing

Used by ms-vp-dev.sh menu script.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from redis.asyncio import Redis

# Redis keys (matching production)
SPOT_KEY = "massive:model:spot:SPX"
VP_KEY = "massive:volume_profile:spx"
VP_META_KEY = "massive:volume_profile:spx:meta"

REDIS_URL = os.environ.get("MARKET_REDIS_URL", "redis://127.0.0.1:6380")


class VPDevInjector:
    def __init__(self):
        self.redis: Redis | None = None

    async def connect(self):
        self.redis = Redis.from_url(REDIS_URL, decode_responses=True)

    async def close(self):
        if self.redis:
            await self.redis.aclose()

    # ========================================
    # Spot Price Operations
    # ========================================

    async def get_spot(self) -> float | None:
        """Get current SPX spot price."""
        data = await self.redis.get(SPOT_KEY)
        if data:
            payload = json.loads(data)
            return payload.get("value")
        return None

    async def inject_spot(self, price: float):
        """Inject SPX spot price."""
        payload = {
            "symbol": "SPX",
            "value": price,
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "vp-dev-injector",
            "timeframe": "MANUAL",
        }
        await self.redis.set(SPOT_KEY, json.dumps(payload))
        print(f"Injected SPX spot: ${price:.2f}")

    # ========================================
    # Volume Profile Operations
    # ========================================

    def price_to_bucket(self, price: float) -> int:
        """
        Convert price to VP bucket.

        Bucket format: price in cents, rounded to nearest 10 cents.
        This matches the VP worker and SSE API expectations.

        Example: $6895.00 -> bucket 689500
        SSE API divides by 100 to get price: 689500 / 100 = $6895.00
        """
        cents = int(round(price * 100))
        return (cents // 10) * 10

    def bucket_to_price(self, bucket: int) -> float:
        """Convert bucket to price."""
        return bucket / 100.0

    async def get_vp_summary(self) -> dict:
        """Get VP summary stats."""
        all_buckets = await self.redis.hgetall(VP_KEY)
        if not all_buckets:
            return {"count": 0, "min": 0, "max": 0, "total_volume": 0}

        buckets = {int(k): int(v) for k, v in all_buckets.items()}
        return {
            "count": len(buckets),
            "min_price": self.bucket_to_price(min(buckets.keys())),
            "max_price": self.bucket_to_price(max(buckets.keys())),
            "total_volume": sum(buckets.values()),
        }

    async def inject_vp_bucket(self, price: float, volume: int, add: bool = True):
        """Inject volume at a single price bucket."""
        bucket = self.price_to_bucket(price)
        if add:
            await self.redis.hincrby(VP_KEY, str(bucket), volume)
        else:
            await self.redis.hset(VP_KEY, str(bucket), volume)

    async def inject_vp_range(self, start: float, end: float, volume: int, step: float = 5.0):
        """
        Inject uniform volume across a price range.

        Args:
            start: Start price
            end: End price
            volume: Volume per bucket
            step: Price step in dollars (default $5)
        """
        bucket_step = int(step * 100)  # Convert dollars to bucket units

        pipe = self.redis.pipeline()
        count = 0
        price = start
        while price <= end:
            bucket = self.price_to_bucket(price)
            pipe.hset(VP_KEY, str(bucket), volume)
            count += 1
            price += step

        await pipe.execute()
        print(f"Injected {count} buckets from ${start:.2f} to ${end:.2f} (${step} step) with volume {volume:,}")

    async def inject_vp_node(self, center: float, width: float, peak_volume: int, step: float = 5.0):
        """
        Inject a high-volume node (triangular distribution).

        Args:
            center: Center price of the node
            width: Total width in dollars
            peak_volume: Volume at the center
            step: Price step in dollars (default $5)
        """
        half_width = width / 2

        pipe = self.redis.pipeline()
        count = 0
        price = center - half_width

        while price <= center + half_width:
            bucket = self.price_to_bucket(price)
            # Triangular distribution: peak at center
            distance = abs(price - center)
            factor = 1 - (distance / half_width) if half_width > 0 else 1
            volume = int(peak_volume * max(0.3, factor))  # Min 30% of peak
            pipe.hset(VP_KEY, str(bucket), volume)
            count += 1
            price += step

        await pipe.execute()
        print(f"Injected NODE at ${center:.2f} (+/- ${half_width:.2f}), peak {peak_volume:,}, {count} buckets")

    async def inject_vp_well(self, center: float, width: float, low_volume: int, step: float = 5.0):
        """
        Inject a low-volume well (antinode).

        Args:
            center: Center price of the well
            width: Total width in dollars
            low_volume: Volume for each bucket
            step: Price step in dollars (default $5)
        """
        half_width = width / 2

        pipe = self.redis.pipeline()
        count = 0
        price = center - half_width

        while price <= center + half_width:
            bucket = self.price_to_bucket(price)
            pipe.hset(VP_KEY, str(bucket), low_volume)
            count += 1
            price += step

        await pipe.execute()
        print(f"Injected WELL at ${center:.2f} (+/- ${half_width:.2f}), volume {low_volume:,}, {count} buckets")

    async def clear_vp(self):
        """Clear all VP data."""
        await self.redis.delete(VP_KEY)
        await self.redis.delete(VP_META_KEY)
        print("Cleared all VP data")

    async def update_meta(self):
        """Update VP metadata."""
        summary = await self.get_vp_summary()
        if summary["count"] > 0:
            await self.redis.hset(VP_META_KEY, mapping={
                "last_updated": datetime.now().isoformat(),
                "levels": summary["count"],
                "total_volume": summary["total_volume"],
                "min_price": summary["min_price"],
                "max_price": summary["max_price"],
            })

    # ========================================
    # Presets
    # ========================================

    async def preset_current_range(self):
        """Create VP structure for current trading range (6800-7000)."""
        print("Creating current range preset (6800-7000)...")

        # Clear existing
        await self.clear_vp()

        # Base layer: low volume across range
        await self.inject_vp_range(6800, 7000, 500000)

        # High volume nodes (where market has memory)
        await self.inject_vp_node(6850, 15, 8000000)   # Support node
        await self.inject_vp_node(6895, 10, 25000000)  # Major node (recent activity)
        await self.inject_vp_node(6920, 10, 7000000)   # Intermediate node
        await self.inject_vp_node(6950, 10, 5000000)   # Resistance node

        # Low volume wells (fast transit zones)
        await self.inject_vp_well(6870, 8, 150000)
        await self.inject_vp_well(6940, 8, 200000)

        # Set spot in middle of range
        await self.inject_spot(6892.50)
        await self.update_meta()

        print("Preset 'current range' applied.")

    async def preset_wide_range(self):
        """Create VP structure for wide range (6500-7200)."""
        print("Creating wide range preset (6500-7200)...")

        # Clear existing
        await self.clear_vp()

        # Base layer
        await self.inject_vp_range(6500, 7200, 300000)

        # Historical nodes
        await self.inject_vp_node(6600, 20, 6000000)
        await self.inject_vp_node(6700, 15, 5000000)
        await self.inject_vp_node(6800, 15, 7000000)
        await self.inject_vp_node(6895, 12, 20000000)  # Current activity
        await self.inject_vp_node(7000, 15, 8000000)
        await self.inject_vp_node(7100, 15, 4000000)

        # Wells
        await self.inject_vp_well(6650, 10, 100000)
        await self.inject_vp_well(6750, 10, 100000)
        await self.inject_vp_well(6950, 10, 150000)
        await self.inject_vp_well(7050, 10, 120000)

        await self.inject_spot(6892.50)
        await self.update_meta()

        print("Preset 'wide range' applied.")

    # ========================================
    # File Operations
    # ========================================

    async def dump_to_file(self, filepath: str):
        """Dump VP data to file."""
        all_buckets = await self.redis.hgetall(VP_KEY)
        if not all_buckets:
            print("No VP data to dump.")
            return

        buckets = sorted((int(k), int(v)) for k, v in all_buckets.items())

        with open(filepath, "w") as f:
            for bucket, volume in buckets:
                f.write(f"{bucket} {volume}\n")

        print(f"Dumped {len(buckets)} buckets to {filepath}")

    async def load_from_file(self, filepath: str, replace: bool = True):
        """Load VP data from file."""
        if replace:
            await self.clear_vp()

        with open(filepath, "r") as f:
            lines = f.readlines()

        pipe = self.redis.pipeline()
        count = 0
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                bucket = int(parts[0])
                volume = int(parts[1])
                pipe.hset(VP_KEY, str(bucket), volume)
                count += 1

        await pipe.execute()
        await self.update_meta()

        print(f"Loaded {count} buckets from {filepath}")

    # ========================================
    # Display
    # ========================================

    async def show_state(self):
        """Show current state of spot and VP."""
        spot = await self.get_spot()
        summary = await self.get_vp_summary()

        print(f"SPX Spot: ${spot:.2f}" if spot else "SPX Spot: (not set)")
        print("")
        print("Volume Profile:")
        print(f"  Buckets: {summary['count']:,}")
        if summary['count'] > 0:
            print(f"  Range: ${summary['min_price']:.2f} - ${summary['max_price']:.2f}")
            print(f"  Total Volume: {summary['total_volume']:,}")

    async def show_spot(self):
        """Show just the spot price."""
        spot = await self.get_spot()
        print(f"SPX: ${spot:.2f}" if spot else "SPX: (not set)")


async def main():
    parser = argparse.ArgumentParser(description="VP Dev Injector")
    parser.add_argument("--action", required=True,
                        choices=["show", "show-spot", "inject-spot",
                                 "inject-vp-range", "inject-vp-node", "inject-vp-well",
                                 "preset-current", "preset-wide", "clear-vp",
                                 "dump", "load"])
    parser.add_argument("--value", type=float, help="Spot price value")
    parser.add_argument("--start", type=float, help="Range start price")
    parser.add_argument("--end", type=float, help="Range end price")
    parser.add_argument("--center", type=float, help="Node/well center price")
    parser.add_argument("--width", type=float, default=10, help="Node/well width")
    parser.add_argument("--volume", type=int, default=1000000, help="Volume amount")
    parser.add_argument("--output", type=str, help="Output file path")
    parser.add_argument("--input", type=str, help="Input file path")

    args = parser.parse_args()

    injector = VPDevInjector()
    await injector.connect()

    try:
        if args.action == "show":
            await injector.show_state()

        elif args.action == "show-spot":
            await injector.show_spot()

        elif args.action == "inject-spot":
            if not args.value:
                print("Error: --value required for inject-spot")
                sys.exit(1)
            await injector.inject_spot(args.value)

        elif args.action == "inject-vp-range":
            if not args.start or not args.end:
                print("Error: --start and --end required for inject-vp-range")
                sys.exit(1)
            await injector.inject_vp_range(args.start, args.end, args.volume)
            await injector.update_meta()

        elif args.action == "inject-vp-node":
            if not args.center:
                print("Error: --center required for inject-vp-node")
                sys.exit(1)
            await injector.inject_vp_node(args.center, args.width, args.volume)
            await injector.update_meta()

        elif args.action == "inject-vp-well":
            if not args.center:
                print("Error: --center required for inject-vp-well")
                sys.exit(1)
            await injector.inject_vp_well(args.center, args.width, args.volume)
            await injector.update_meta()

        elif args.action == "preset-current":
            await injector.preset_current_range()

        elif args.action == "preset-wide":
            await injector.preset_wide_range()

        elif args.action == "clear-vp":
            await injector.clear_vp()

        elif args.action == "dump":
            path = args.output or "/tmp/vp_bins.txt"
            await injector.dump_to_file(path)

        elif args.action == "load":
            if not args.input:
                print("Error: --input required for load")
                sys.exit(1)
            await injector.load_from_file(args.input)

    finally:
        await injector.close()


if __name__ == "__main__":
    asyncio.run(main())
