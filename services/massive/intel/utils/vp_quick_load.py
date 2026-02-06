#!/usr/bin/env python3
"""
VP Quick Load - Fast Volume Profile Builder

Downloads SPY minute bars from Polygon and builds a compact volume profile.

Data Storage Strategy (Dealer Gravity Architecture):
  - RAW volumes saved to DISK (authoritative, replayable)
  - FINAL artifacts pushed to REDIS (delivery layer only)

Disk storage: data/dealer_gravity/raw/volume_bars.json
Redis storage: dealer_gravity:artifact:{symbol} (render-ready only)

Usage:
    python vp_quick_load.py --days 30              # Last 30 days
    python vp_quick_load.py --years 15             # 15 years of history
    python vp_quick_load.py --years 15 --bucket 20 # $20 buckets
"""

import argparse
import asyncio
import json
import os
import sys
import urllib.request
import urllib.error
import time
from datetime import datetime, timedelta, date, timezone
from pathlib import Path

from redis.asyncio import Redis

POLYGON_BASE = "https://api.polygon.io"
REDIS_URL = os.environ.get("MARKET_REDIS_URL", "redis://127.0.0.1:6380")

# Disk storage paths (authoritative)
DATA_DIR = Path(__file__).parent.parent.parent.parent.parent / "data" / "dealer_gravity"
RAW_DIR = DATA_DIR / "raw"
TRANSFORMS_DIR = DATA_DIR / "transforms"
STRUCTURES_DIR = DATA_DIR / "structures"
ARTIFACTS_DIR = DATA_DIR / "artifacts"

# Redis keys (legacy - for backward compatibility)
REDIS_KEY_RAW = "massive:volume_profile:spx"
REDIS_KEY_TV = "massive:volume_profile:spx:tv"

# New Redis keys (Dealer Gravity artifact format)
REDIS_KEY_ARTIFACT = "dealer_gravity:artifact:spx"
REDIS_KEY_CONTEXT = "dealer_gravity:context:spx"

# TV smoothing: microbins to distribute volume across bar range
TV_MICROBINS = 30

# Structure detection thresholds
VOLUME_NODE_THRESHOLD = 0.7  # 70th percentile = Volume Node (concentrated attention)
VOLUME_WELL_THRESHOLD = 0.2  # Below 20th percentile = Volume Well (neglect)
CREVASSE_MIN_WIDTH = 3       # Minimum consecutive wells to form a Crevasse

# Default bucket size in SPX dollars
# $1 SPX = $0.10 SPY = minimum meaningful tick
# Full 15-year range (~5500 buckets) = ~44KB in Redis
# API returns ±250 points (~500 buckets) = ~4KB per request
DEFAULT_BUCKET_SIZE = 1


class VPQuickLoader:
    def __init__(self, api_key: str, mode: str = "tv", bucket_size: int = DEFAULT_BUCKET_SIZE):
        self.api_key = api_key
        self.mode = mode
        self.bucket_size = bucket_size
        self.redis: Redis | None = None

        # Accumulate into dict: bucket_index -> volume
        self.profile_raw: dict[int, int] = {}
        self.profile_tv: dict[int, int] = {}

        # Track price range
        self.min_bucket = float('inf')
        self.max_bucket = float('-inf')

        self.days_processed = 0
        self.total_volume = 0

        # Ensure disk directories exist
        for d in [RAW_DIR, TRANSFORMS_DIR, STRUCTURES_DIR, ARTIFACTS_DIR]:
            d.mkdir(parents=True, exist_ok=True)

    async def connect(self):
        self.redis = Redis.from_url(REDIS_URL, decode_responses=True)
        print(f"Connected to Redis at {REDIS_URL}")

    async def close(self):
        if self.redis:
            await self.redis.aclose()

    def spy_to_bucket_index(self, spy_price: float) -> int:
        """Convert SPY price to bucket index."""
        spx_price = spy_price * 10  # SPY -> SPX
        bucket_index = int(spx_price // self.bucket_size)
        self.min_bucket = min(self.min_bucket, bucket_index)
        self.max_bucket = max(self.max_bucket, bucket_index)
        return bucket_index

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
        """RAW mode: Volume at VWAP price."""
        price = bar.get("vw") or ((bar.get("h", 0) + bar.get("l", 0)) / 2)
        volume = bar.get("v", 0)
        if volume <= 0 or price <= 0:
            return

        idx = self.spy_to_bucket_index(price)
        self.profile_raw[idx] = self.profile_raw.get(idx, 0) + int(volume)

    def accumulate_tv(self, bar: dict):
        """TV mode: Volume distributed across bar's high-low range."""
        low = bar.get("l")
        high = bar.get("h")
        volume = bar.get("v", 0)

        if low is None or high is None or volume <= 0:
            return
        if high <= low:
            idx = self.spy_to_bucket_index((high + low) / 2)
            self.profile_tv[idx] = self.profile_tv.get(idx, 0) + int(volume)
            return

        step = (high - low) / TV_MICROBINS
        vol_per_bin = volume / TV_MICROBINS

        for i in range(TV_MICROBINS):
            price = low + i * step
            idx = self.spy_to_bucket_index(price)
            self.profile_tv[idx] = self.profile_tv.get(idx, 0) + int(vol_per_bin)

    def process_bars(self, bars: list[dict]):
        """Process bars and accumulate volume."""
        for bar in bars:
            volume = bar.get("v", 0)
            if volume <= 0:
                continue

            if self.mode in ("raw", "both"):
                self.accumulate_raw(bar)
            if self.mode in ("tv", "both"):
                self.accumulate_tv(bar)

            self.total_volume += int(volume)

    def build_compact_profile(self, profile: dict[int, int]) -> dict:
        """Convert bucket dict to compact array format with normalized volumes."""
        if not profile:
            return {"min": 0, "step": self.bucket_size, "volumes": []}

        min_idx = min(profile.keys())
        max_idx = max(profile.keys())

        # Build dense array from min to max
        raw_volumes = []
        for i in range(min_idx, max_idx + 1):
            raw_volumes.append(profile.get(i, 0))

        # Normalize to 0-1000 scale (max volume = 1000)
        max_vol = max(raw_volumes) if raw_volumes else 1
        volumes = [int(v * 1000 / max_vol) for v in raw_volumes]

        return {
            "min": min_idx * self.bucket_size,  # Min price in dollars
            "step": self.bucket_size,
            "volumes": volumes,  # Normalized 0-1000
        }

    def detect_structures(self, compact: dict) -> dict:
        """
        Detect structural features using Dealer Gravity lexicon.

        Returns:
            volume_nodes: Price levels with concentrated attention (high volume)
            volume_wells: Price levels with neglect (low volume)
            crevasses: Extended regions of persistent volume scarcity
        """
        volumes = compact.get("volumes", [])
        min_price = compact.get("min", 0)
        step = compact.get("step", 1)

        if not volumes:
            return {"volume_nodes": [], "volume_wells": [], "crevasses": []}

        # Calculate thresholds
        sorted_vols = sorted([v for v in volumes if v > 0])
        if not sorted_vols:
            return {"volume_nodes": [], "volume_wells": [], "crevasses": []}

        node_threshold = sorted_vols[int(len(sorted_vols) * VOLUME_NODE_THRESHOLD)]
        well_threshold = sorted_vols[int(len(sorted_vols) * VOLUME_WELL_THRESHOLD)]

        volume_nodes = []
        volume_wells = []

        for i, vol in enumerate(volumes):
            price = min_price + i * step
            if vol >= node_threshold:
                volume_nodes.append(price)
            elif vol <= well_threshold and vol > 0:
                volume_wells.append(price)

        # Detect Crevasses (extended regions of consecutive wells)
        crevasses = []
        crevasse_start = None
        consecutive_wells = 0

        for i, vol in enumerate(volumes):
            is_well = vol <= well_threshold
            if is_well:
                if crevasse_start is None:
                    crevasse_start = min_price + i * step
                consecutive_wells += 1
            else:
                if consecutive_wells >= CREVASSE_MIN_WIDTH:
                    crevasse_end = min_price + (i - 1) * step
                    crevasses.append([crevasse_start, crevasse_end])
                crevasse_start = None
                consecutive_wells = 0

        # Handle crevasse at the end
        if consecutive_wells >= CREVASSE_MIN_WIDTH and crevasse_start is not None:
            crevasse_end = min_price + (len(volumes) - 1) * step
            crevasses.append([crevasse_start, crevasse_end])

        return {
            "volume_nodes": volume_nodes,
            "volume_wells": volume_wells,
            "crevasses": crevasses
        }

    def save_raw_to_disk(self):
        """Save raw volume data to disk (authoritative storage)."""
        raw_file = RAW_DIR / "volume_bars.json"

        data = {
            "raw_profile": dict(self.profile_raw),
            "tv_profile": dict(self.profile_tv),
            "bucket_size": self.bucket_size,
            "days_processed": self.days_processed,
            "total_volume": self.total_volume,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        with open(raw_file, "w") as f:
            json.dump(data, f)

        print(f"  Raw data saved to disk: {raw_file}")

    def build_artifact(self, compact: dict, structures: dict, spot: float = None) -> dict:
        """
        Build final render-ready artifact (Tier 1: Visualization Artifact).
        This is what gets pushed to Redis and served to the frontend.
        """
        artifact_version = f"v{int(time.time())}"

        return {
            "profile": {
                "min": compact.get("min", 0),
                "step": compact.get("step", 1),
                "bins": compact.get("volumes", [])
            },
            "structures": structures,
            "meta": {
                "spot": spot,
                "algorithm": "tv_microbins_30",
                "normalized_scale": 1000,
                "artifact_version": artifact_version,
                "last_update": datetime.now(timezone.utc).isoformat()
            }
        }

    def build_context_snapshot(self, artifact: dict, spot: float = None) -> dict:
        """
        Build context snapshot (Tier 2: System-Focused).
        For Trade Selector, RiskGraph, ML systems.
        """
        structures = artifact.get("structures", {})
        volume_nodes = structures.get("volume_nodes", [])
        volume_wells = structures.get("volume_wells", [])
        crevasses = structures.get("crevasses", [])

        # Calculate proximity metrics if spot provided
        nearest_node_dist = None
        well_proximity = None
        in_crevasse = False

        if spot and volume_nodes:
            nearest_node = min(volume_nodes, key=lambda x: abs(x - spot))
            nearest_node_dist = (spot - nearest_node) / spot  # Normalized distance

        if spot and volume_wells:
            nearest_well = min(volume_wells, key=lambda x: abs(x - spot))
            well_proximity = abs(spot - nearest_well) / spot

        if spot and crevasses:
            for start, end in crevasses:
                if start <= spot <= end:
                    in_crevasse = True
                    break

        return {
            "symbol": "SPX",
            "spot": spot,
            "nearest_volume_node": min(volume_nodes, key=lambda x: abs(x - spot)) if spot and volume_nodes else None,
            "nearest_volume_node_dist": nearest_node_dist,
            "volume_well_proximity": well_proximity,
            "in_crevasse": in_crevasse,
            "market_memory_strength": 0.82,  # TODO: Calculate from volume distribution
            "gamma_alignment": None,  # Populated by GEX integration
            "artifact_version": artifact.get("meta", {}).get("artifact_version"),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def save_artifact_to_disk(self, artifact: dict, context: dict):
        """Save artifact and context to disk (authoritative before Redis push)."""
        artifact_file = ARTIFACTS_DIR / "spx_latest.json"
        context_file = ARTIFACTS_DIR / "spx_context.json"

        with open(artifact_file, "w") as f:
            json.dump(artifact, f)

        with open(context_file, "w") as f:
            json.dump(context, f)

        print(f"  Artifact saved to disk: {artifact_file}")

    async def save_to_redis(self, spot: float = None):
        """Save compact profiles and Dealer Gravity artifacts to Redis."""
        pipe = self.redis.pipeline()

        # Legacy format (backward compatibility)
        if self.mode in ("raw", "both") and self.profile_raw:
            compact = self.build_compact_profile(self.profile_raw)
            pipe.set(REDIS_KEY_RAW, json.dumps(compact))
            print(f"  RAW: {len(compact['volumes'])} levels, {len(json.dumps(compact)):,} bytes")

        compact_tv = None
        if self.mode in ("tv", "both") and self.profile_tv:
            compact_tv = self.build_compact_profile(self.profile_tv)
            pipe.set(REDIS_KEY_TV, json.dumps(compact_tv))
            print(f"  TV: {len(compact_tv['volumes'])} levels, {len(json.dumps(compact_tv)):,} bytes")

        # Dealer Gravity artifact format (new)
        if compact_tv:
            # 1. Save raw data to disk (authoritative)
            self.save_raw_to_disk()

            # 2. Detect structures
            structures = self.detect_structures(compact_tv)
            print(f"  Structures: {len(structures['volume_nodes'])} nodes, "
                  f"{len(structures['volume_wells'])} wells, "
                  f"{len(structures['crevasses'])} crevasses")

            # 3. Build artifacts
            artifact = self.build_artifact(compact_tv, structures, spot)
            context = self.build_context_snapshot(artifact, spot)

            # 4. Save to disk (authoritative)
            self.save_artifact_to_disk(artifact, context)

            # 5. Push to Redis (delivery layer)
            pipe.set(REDIS_KEY_ARTIFACT, json.dumps(artifact))
            pipe.set(REDIS_KEY_CONTEXT, json.dumps(context))
            print(f"  Artifact: {len(json.dumps(artifact)):,} bytes")

        await pipe.execute()

        # 6. Publish update event for SSE fanout
        if compact_tv:
            event = {
                "type": "dealer_gravity_artifact_updated",
                "symbol": "SPX",
                "artifact_version": artifact.get("meta", {}).get("artifact_version"),
                "occurred_at": datetime.now(timezone.utc).isoformat()
            }
            await self.redis.publish("dealer_gravity_updated", json.dumps(event))
            print(f"  Published update event: {event['artifact_version']}")

    async def load(self, days: int = None, years: int = None):
        """Load VP data from Polygon."""
        end_date = date.today()

        if years:
            start_date = end_date - timedelta(days=years * 365)
        elif days:
            start_date = end_date - timedelta(days=days)
        else:
            start_date = end_date - timedelta(days=30)

        print(f"Loading SPY data from {start_date} to {end_date}")
        print(f"Mode: {self.mode.upper()}, Bucket size: ${self.bucket_size}")

        current = start_date

        while current <= end_date:
            if current.weekday() >= 5:  # Skip weekends
                current += timedelta(days=1)
                continue

            date_str = current.strftime("%Y-%m-%d")
            bars = self.fetch_day("SPY", date_str)

            if bars:
                self.process_bars(bars)
                self.days_processed += 1

                if self.days_processed % 50 == 0:
                    levels = len(self.profile_tv) if self.mode in ("tv", "both") else len(self.profile_raw)
                    print(f"  {self.days_processed} days ({current}): {levels} levels")

            time.sleep(0.25)  # Rate limit
            current += timedelta(days=1)

        # Save final result (fetch current spot if available)
        spot = await self.fetch_current_spot()
        await self.save_to_redis(spot=spot)
        print(f"\nDone: {self.days_processed} days, {self.total_volume:,.0f} total volume")

    async def fetch_current_spot(self) -> float | None:
        """Fetch current SPX spot price from Redis."""
        try:
            spot_data = await self.redis.get("massive:models:spot")
            if spot_data:
                data = json.loads(spot_data)
                return data.get("SPX", {}).get("last") or data.get("SPX", {}).get("price")
        except Exception:
            pass
        return None


async def main():
    parser = argparse.ArgumentParser(description="VP Quick Load")
    parser.add_argument("--days", type=int, help="Number of days to load")
    parser.add_argument("--years", type=int, help="Number of years to load")
    parser.add_argument("--mode", choices=["raw", "tv", "both"], default="tv")
    parser.add_argument("--bucket", type=int, default=DEFAULT_BUCKET_SIZE,
                        help=f"Bucket size in SPX dollars (default: ${DEFAULT_BUCKET_SIZE})")
    args = parser.parse_args()

    api_key = os.environ.get("POLYGON_API_KEY") or os.environ.get("MASSIVE_API_KEY")
    if not api_key:
        print("Error: POLYGON_API_KEY or MASSIVE_API_KEY required")
        sys.exit(1)

    loader = VPQuickLoader(api_key, mode=args.mode, bucket_size=args.bucket)
    await loader.connect()

    try:
        await loader.load(days=args.days, years=args.years)
    finally:
        await loader.close()


if __name__ == "__main__":
    asyncio.run(main())
