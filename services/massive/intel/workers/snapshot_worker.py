# services/massive/intel/workers/snapshot_worker.py

from __future__ import annotations

import asyncio
import json
import time
import re
from typing import Dict, Any

from redis.asyncio import Redis


# ============================================================
# Ticker helpers (authoritative)
# ============================================================

_TICKER_RE = re.compile(r"^O:(?P<root>[A-Z]+)\d{6,8}[CP]\d+")


def symbol_from_ticker(ticker: str) -> str | None:
    """
    Derive canonical symbol (I:SPX / I:NDX) from option ticker.
    Sole source of truth: ticker string.

    Handles root variants:
    - SPX, SPXW, SPXM → I:SPX
    - NDX, NDXP → I:NDX
    """
    m = _TICKER_RE.match(ticker)
    if not m:
        return None

    root = m.group("root")

    # SPX variants (standard, weekly, monthly)
    if root in ("SPX", "SPXW", "SPXM"):
        return "I:SPX"

    # NDX variants
    if root in ("NDX", "NDXP"):
        return "I:NDX"

    return None


# ============================================================
# SnapshotWorker — Geometry-driven (CHAIN ONLY)
# ============================================================

class SnapshotWorker:
    """
    SnapshotWorker — Geometry-driven snapshot stage (CHAIN-ONLY MODE)

    - Listens for geometry events
    - Reads massive:chain:latest
    - Buckets contracts strictly by ticker
    - Hands snapshots directly to Builder

    Ticker is the truth. Payload is opaque.
    """

    def __init__(self, config: Dict[str, Any], logger):
        self.config = config
        self.logger = logger

        self.symbols = [
            s.strip()
            for s in config.get("MASSIVE_CHAIN_SYMBOLS", "I:SPX,I:NDX").split(",")
            if s.strip()
        ]

        self.market_redis_url = config["buses"]["market-redis"]["url"]
        self._redis: Redis | None = None

        self.geometry_channel = "massive:chain:geometry_updated"
        self.geometry_key = "massive:chain:latest"

        self.builder = None
        self.stop_event: asyncio.Event | None = None

        self.logger.info(
            f"[SNAPSHOT INIT] symbols={self.symbols} (ticker-authoritative)",
            emoji="📸",
        )

    async def _redis_conn(self) -> Redis:
        if not self._redis:
            self._redis = Redis.from_url(self.market_redis_url, decode_responses=True)
        return self._redis

    # ============================================================
    # Event loop
    # ============================================================

    async def _run_geometry_listener(self) -> None:
        r = await self._redis_conn()
        pubsub = r.pubsub()
        await pubsub.subscribe(self.geometry_channel)

        self.logger.info(
            f"[SNAPSHOT] Listening for geometry events on {self.geometry_channel}",
            emoji="📡",
        )

        async for msg in pubsub.listen():
            if self.stop_event.is_set():
                break

            if msg["type"] != "message":
                continue

            try:
                payload = json.loads(msg["data"])
                version = payload.get("version")
                self.logger.info(
                    f"[SNAPSHOT] Geometry event received v={version}",
                    emoji="🔔",
                )
                await self._produce_snapshot(version)

            except Exception as e:
                self.logger.error(f"[SNAPSHOT EVENT ERROR] {e}", emoji="💥")

        await pubsub.unsubscribe(self.geometry_channel)

    # ============================================================
    # Snapshot production
    # ============================================================

    async def _produce_snapshot(self, geometry_version: int) -> None:
        r = await self._redis_conn()

        raw = await r.get(self.geometry_key)
        if not raw:
            self.logger.warning("[SNAPSHOT] No geometry found", emoji="⚠️")
            return

        geometry = json.loads(raw)
        contracts: Dict[str, Any] = geometry.get("contracts", {})
        if not contracts:
            self.logger.warning("[SNAPSHOT] Geometry empty", emoji="⚠️")
            return

        heatmap_id = f"heatmap_{int(time.time() * 1000)}"
        substrate_id = f"chain_v{geometry_version}:{heatmap_id}"

        snapshots: Dict[str, Dict[str, Any]] = {s: {} for s in self.symbols}

        rejected = 0

        for ticker, payload in contracts.items():
            symbol = symbol_from_ticker(ticker)
            if symbol is None or symbol not in snapshots:
                rejected += 1
                continue

            c = dict(payload)
            c["substrate_id"] = substrate_id
            snapshots[symbol][ticker] = c

        total = sum(len(v) for v in snapshots.values())

        self.logger.info(
            f"[SNAPSHOT] Produced v={geometry_version} "
            f"contracts={total} rejected={rejected}",
            emoji="📦",
        )

        if not self.builder:
            self.logger.warning("[SNAPSHOT] Builder not injected", emoji="⚠️")
            return

        try:
            await self.builder.receive_snapshot(snapshots)
            self.logger.info("[SNAPSHOT] Snapshot pushed to builder", emoji="➡️")
        except Exception as e:
            self.logger.error(f"[SNAPSHOT → BUILDER ERROR] {e}", emoji="💥")

    # ============================================================
    # Wiring
    # ============================================================

    def set_builder(self, builder) -> None:
        self.builder = builder
        self.logger.info("[SNAPSHOT] Builder injected", emoji="🔗")

    async def run(self, stop_event: asyncio.Event) -> None:
        self.stop_event = stop_event
        self.logger.info("[SNAPSHOT START] running", emoji="📸")

        try:
            await self._run_geometry_listener()
        except asyncio.CancelledError:
            self.logger.info("[SNAPSHOT] cancelled", emoji="🛑")
        finally:
            self.logger.info("[SNAPSHOT STOP] halted", emoji="🛑")