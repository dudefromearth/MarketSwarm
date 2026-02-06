#!/usr/bin/env python3
"""
Dealer Gravity Artifact Builder

Transforms raw volume data from disk into render-ready visualization artifacts.
This module implements the disk-based compute pipeline:

  Raw Data (disk)
    ↓
  Transform (micro-bins, TV, etc.)
    ↓
  Structural Analysis (Volume Nodes, Volume Wells, Crevasses)
    ↓
  Renderable Artifact Builder
    ↓
  Push FINAL artifact to Redis (delivery layer)

Each stage is versioned, replayable, testable, and auditable.

Dealer Gravity Lexicon (REQUIRED):
  - Volume Node: Price level with concentrated market attention (NOT HVN)
  - Volume Well: Price level with neglect (NOT LVN)
  - Crevasse: Extended regions of persistent volume scarcity
  - Market Memory: Persistent topology across long horizons

BANNED TERMS (never use):
  - POC, VAH, VAL, Value Area, HVN, LVN, or any AMT terminology
"""

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from redis.asyncio import Redis

# Paths
DATA_DIR = Path(__file__).parent.parent.parent.parent.parent / "data" / "dealer_gravity"
RAW_DIR = DATA_DIR / "raw"
TRANSFORMS_DIR = DATA_DIR / "transforms"
STRUCTURES_DIR = DATA_DIR / "structures"
ARTIFACTS_DIR = DATA_DIR / "artifacts"

# Redis
REDIS_URL = os.environ.get("MARKET_REDIS_URL", "redis://127.0.0.1:6380")
REDIS_KEY_ARTIFACT = "dealer_gravity:artifact:spx"
REDIS_KEY_CONTEXT = "dealer_gravity:context:spx"

# Structure detection thresholds
VOLUME_NODE_THRESHOLD = 0.7   # Top 30% = Volume Nodes
VOLUME_WELL_THRESHOLD = 0.2   # Bottom 20% = Volume Wells
CREVASSE_MIN_WIDTH = 3        # Minimum consecutive wells for Crevasse

# TV transform settings
TV_MICROBINS = 30
NORMALIZED_SCALE = 1000


class DGArtifactBuilder:
    """
    Builds Dealer Gravity artifacts from raw volume data.

    This class implements the core pipeline:
    1. Load raw data from disk
    2. Apply transforms (TV microbin spreading)
    3. Detect structural features (Volume Nodes, Wells, Crevasses)
    4. Build render-ready artifact
    5. Push to Redis for delivery
    """

    def __init__(self, symbol: str = "SPX", bucket_size: int = 1):
        self.symbol = symbol.upper()
        self.bucket_size = bucket_size
        self.redis: Optional[Redis] = None

        # Ensure directories exist
        for d in [RAW_DIR, TRANSFORMS_DIR, STRUCTURES_DIR, ARTIFACTS_DIR]:
            d.mkdir(parents=True, exist_ok=True)

    async def connect(self):
        """Connect to Redis."""
        self.redis = Redis.from_url(REDIS_URL, decode_responses=True)

    async def close(self):
        """Close Redis connection."""
        if self.redis:
            await self.redis.aclose()

    def load_raw_from_disk(self) -> dict:
        """Load raw volume data from disk."""
        raw_file = RAW_DIR / "volume_bars.json"
        if not raw_file.exists():
            return {}

        with open(raw_file, "r") as f:
            return json.load(f)

    def transform_tv(self, raw_profile: dict[str, int]) -> dict[int, int]:
        """
        Apply TV transform to raw volume data.

        The TV transform spreads volume across the bar's high-low range
        using microbins, creating a smoother volume profile.
        """
        # Raw profile is already transformed in vp_quick_load.py
        # This method exists for future re-processing needs
        return {int(k): v for k, v in raw_profile.items()}

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

        # Normalize to 0-1000 scale
        max_vol = max(raw_volumes) if raw_volumes else 1
        volumes = [int(v * NORMALIZED_SCALE / max_vol) for v in raw_volumes]

        return {
            "min": min_idx * self.bucket_size,
            "step": self.bucket_size,
            "volumes": volumes,
        }

    def detect_structures(self, compact: dict) -> dict:
        """
        Detect structural features using Dealer Gravity lexicon.

        Volume Node: Zone of concentrated market attention (friction, memory)
        Volume Well: Zone of market neglect (low resistance, acceleration)
        Crevasse: Extended region of persistent volume scarcity (convex outcomes)
        """
        volumes = compact.get("volumes", [])
        min_price = compact.get("min", 0)
        step = compact.get("step", 1)

        if not volumes:
            return {"volume_nodes": [], "volume_wells": [], "crevasses": []}

        # Calculate thresholds from non-zero volumes
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

        # Detect Crevasses (extended consecutive wells)
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

    def calculate_market_memory_strength(self, compact: dict, structures: dict) -> float:
        """
        Calculate Market Memory strength (0-1).

        Higher values indicate stronger persistent topology.
        Based on volume distribution stability and structural feature density.
        """
        volumes = compact.get("volumes", [])
        if not volumes:
            return 0.0

        # Factors contributing to market memory:
        # 1. Volume distribution concentration (Gini coefficient proxy)
        total_vol = sum(volumes)
        if total_vol == 0:
            return 0.0

        sorted_vols = sorted(volumes, reverse=True)
        top_20_pct = sorted_vols[:int(len(sorted_vols) * 0.2)]
        concentration = sum(top_20_pct) / total_vol  # How much volume is in top 20%

        # 2. Structural feature density
        num_nodes = len(structures.get("volume_nodes", []))
        num_wells = len(structures.get("volume_wells", []))
        num_crevasses = len(structures.get("crevasses", []))
        price_range = len(volumes)

        node_density = min(num_nodes / max(price_range, 1) * 10, 1.0)
        structure_factor = (node_density + (num_crevasses > 0) * 0.2) / 1.2

        # Combine factors
        memory_strength = (concentration * 0.6 + structure_factor * 0.4)
        return round(min(memory_strength, 1.0), 2)

    def build_artifact(self, compact: dict, structures: dict, spot: float = None) -> dict:
        """
        Build final render-ready artifact (Tier 1: Visualization Artifact).

        This is the contract between server and frontend:
        - Frontend maps bins → pixels
        - Frontend draws structural overlays
        - Frontend does NO inference, NO recomputation
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
                "algorithm": f"tv_microbins_{TV_MICROBINS}",
                "normalized_scale": NORMALIZED_SCALE,
                "artifact_version": artifact_version,
                "last_update": datetime.now(timezone.utc).isoformat()
            }
        }

    def build_context_snapshot(self, artifact: dict, compact: dict,
                               structures: dict, spot: float = None) -> dict:
        """
        Build context snapshot (Tier 2: System-Focused).

        For Trade Selector, RiskGraph, ML feature extraction.
        Extremely small (~200 bytes), deterministic, ML-ready.
        """
        volume_nodes = structures.get("volume_nodes", [])
        volume_wells = structures.get("volume_wells", [])
        crevasses = structures.get("crevasses", [])

        # Calculate proximity metrics
        nearest_node = None
        nearest_node_dist = None
        well_proximity = None
        in_crevasse = False

        if spot and volume_nodes:
            nearest_node = min(volume_nodes, key=lambda x: abs(x - spot))
            nearest_node_dist = round((spot - nearest_node) / spot, 6)

        if spot and volume_wells:
            nearest_well = min(volume_wells, key=lambda x: abs(x - spot))
            well_proximity = round(abs(spot - nearest_well) / spot, 6)

        if spot and crevasses:
            for start, end in crevasses:
                if start <= spot <= end:
                    in_crevasse = True
                    break

        # Calculate market memory strength
        memory_strength = self.calculate_market_memory_strength(compact, structures)

        return {
            "symbol": self.symbol,
            "spot": spot,
            "nearest_volume_node": nearest_node,
            "nearest_volume_node_dist": nearest_node_dist,
            "volume_well_proximity": well_proximity,
            "in_crevasse": in_crevasse,
            "market_memory_strength": memory_strength,
            "gamma_alignment": None,  # Populated by GEX integration
            "artifact_version": artifact.get("meta", {}).get("artifact_version"),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def save_structures_to_disk(self, structures: dict):
        """Save structural analysis to disk."""
        struct_file = STRUCTURES_DIR / f"{self.symbol.lower()}_structures.json"
        with open(struct_file, "w") as f:
            json.dump({
                "structures": structures,
                "analyzed_at": datetime.now(timezone.utc).isoformat()
            }, f)

    def save_artifact_to_disk(self, artifact: dict, context: dict):
        """Save artifact and context to disk (authoritative)."""
        artifact_file = ARTIFACTS_DIR / f"{self.symbol.lower()}_latest.json"
        context_file = ARTIFACTS_DIR / f"{self.symbol.lower()}_context.json"

        with open(artifact_file, "w") as f:
            json.dump(artifact, f)

        with open(context_file, "w") as f:
            json.dump(context, f)

    async def fetch_spot(self) -> float | None:
        """Fetch current spot price from Redis."""
        try:
            spot_data = await self.redis.get("massive:models:spot")
            if spot_data:
                data = json.loads(spot_data)
                symbol_data = data.get(self.symbol, {})
                return symbol_data.get("last") or symbol_data.get("price")
        except Exception:
            pass
        return None

    async def build_and_publish(self, spot: float = None) -> dict:
        """
        Run full pipeline: disk → transform → structure → artifact → Redis.

        Returns the built artifact.
        """
        # 1. Load raw data from disk
        raw_data = self.load_raw_from_disk()
        if not raw_data:
            raise ValueError("No raw data found on disk")

        tv_profile = raw_data.get("tv_profile", {})
        if not tv_profile:
            raise ValueError("No TV profile data found")

        # 2. Build compact profile
        profile_dict = {int(k): v for k, v in tv_profile.items()}
        compact = self.build_compact_profile(profile_dict)

        # 3. Detect structures
        structures = self.detect_structures(compact)
        self.save_structures_to_disk(structures)

        # 4. Get spot price if not provided
        if spot is None:
            spot = await self.fetch_spot()

        # 5. Build artifacts
        artifact = self.build_artifact(compact, structures, spot)
        context = self.build_context_snapshot(artifact, compact, structures, spot)

        # 6. Save to disk (authoritative)
        self.save_artifact_to_disk(artifact, context)

        # 7. Push to Redis (delivery layer)
        pipe = self.redis.pipeline()
        pipe.set(REDIS_KEY_ARTIFACT, json.dumps(artifact))
        pipe.set(REDIS_KEY_CONTEXT, json.dumps(context))
        await pipe.execute()

        # 8. Publish update event
        event = {
            "type": "dealer_gravity_artifact_updated",
            "symbol": self.symbol,
            "artifact_version": artifact["meta"]["artifact_version"],
            "occurred_at": datetime.now(timezone.utc).isoformat()
        }
        await self.redis.publish("dealer_gravity_updated", json.dumps(event))

        print(f"[DG] Artifact built and published: {artifact['meta']['artifact_version']}")
        print(f"     Structures: {len(structures['volume_nodes'])} nodes, "
              f"{len(structures['volume_wells'])} wells, "
              f"{len(structures['crevasses'])} crevasses")
        print(f"     Market Memory: {context['market_memory_strength']}")

        return artifact


async def main():
    """CLI entry point for manual artifact rebuilding."""
    import argparse

    parser = argparse.ArgumentParser(description="Dealer Gravity Artifact Builder")
    parser.add_argument("--spot", type=float, help="Manual spot price override")
    args = parser.parse_args()

    builder = DGArtifactBuilder()
    await builder.connect()

    try:
        artifact = await builder.build_and_publish(spot=args.spot)
        print(f"\nArtifact: {json.dumps(artifact['meta'], indent=2)}")
    finally:
        await builder.close()


if __name__ == "__main__":
    asyncio.run(main())
