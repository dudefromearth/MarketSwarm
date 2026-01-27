#!/usr/bin/env python3
# services/massive/intel/chain_worker.py

from __future__ import annotations

import asyncio
import json
import math
import os
import time
from datetime import datetime
from typing import Any, Dict, List

from redis.asyncio import Redis
from massive import RESTClient

from ..normalizers.registry import NORMALIZERS


# ============================================================
# Helpers
# ============================================================

def _round_to_nearest_5(x: float) -> int:
    return int(round(x / 5.0)) * 5


# ============================================================
# Chain Snapshot Capture (optional, passive)
# ============================================================

class ChainSnapshotCapture:
    def __init__(self, capture_dir: str, logger):
        os.makedirs(capture_dir, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        self.path = os.path.join(capture_dir, f"chain_{ts}.jsonl")
        self.fh = open(self.path, "a", buffering=1)
        logger.info(f"[CHAIN CAPTURE] enabled → {self.path}", emoji="📸")

    def write(self, record: Dict[str, Any]) -> None:
        self.fh.write(json.dumps(record) + "\n")


# ============================================================
# ChainWorker — NO EPOCHS, SURFACE HASH PER SNAPSHOT
# ============================================================

class ChainWorker:
    """
    ChainWorker — publishes unified surface hash per snapshot
    No epochs, no per-contract keys, no bloat
    """

    def __init__(self, config: Dict[str, Any], logger) -> None:
        self.config = config
        self.logger = logger

        self.chain_symbols = [
            s.strip()
            for s in config.get("MASSIVE_CHAIN_SYMBOLS", "SPX").split(",")
            if s.strip()
        ]

        self.interval_sec = int(config.get("MASSIVE_CHAIN_INTERVAL_SEC", "10"))
        self.num_expirations = int(config.get("MASSIVE_CHAIN_NUM_EXPIRATIONS", "10"))
        self.surface_ttl_sec = int(config.get("MASSIVE_SURFACE_TTL_MINUTES", 390)) * 60

        self.em_days = int(config.get("MASSIVE_CHAIN_EM_DAYS", "1"))
        self.em_mult = float(config.get("MASSIVE_CHAIN_EM_MULT", "2.25"))

        self.client = RESTClient(config["MASSIVE_API_KEY"])

        self.market_redis_url = config["buses"]["market-redis"]["url"]
        self._redis: Optional[Redis] = None

        self.capture_enabled = str(config.get("MASSIVE_WS_CAPTURE", "false")).lower() == "true"
        self.chain_capture: Optional[ChainSnapshotCapture] = None
        if self.capture_enabled:
            cap_dir = config.get("MASSIVE_WS_CAPTURE_CHAIN_DIR")
            if cap_dir:
                self.chain_capture = ChainSnapshotCapture(cap_dir, logger)

        self.logger.info(
            f"[CHAIN INIT] symbols={self.chain_symbols} "
            f"interval={self.interval_sec}s expirations={self.num_expirations} "
            f"surface_ttl={self.surface_ttl_sec}s",
            emoji="🧱",
        )

    async def _redis_conn(self) -> Redis:
        if not self._redis:
            self._redis = Redis.from_url(
                self.market_redis_url,
                decode_responses=True,
            )
        return self._redis

    async def _load_spot(self, sym: str) -> Optional[float]:
        r = await self._redis_conn()
        raw = await r.get(f"massive:model:spot:{sym}")
        if not raw:
            return None
        return float(json.loads(raw).get("value"))

    def _compute_range(self, spot: float, vix: Optional[float]) -> int:
        if not vix or vix <= 0:
            return 150
        em = spot * (vix / 100.0) * math.sqrt(self.em_days / 252.0)
        return int(round(self.em_mult * em)) or 50

    def _list_expirations(self, underlying: str) -> List[str]:
        exps = set()
        for opt in self.client.list_snapshot_options_chain(
            underlying,
            params={"limit": 250},
        ):
            exp = getattr(opt.details, "expiration_date", None)
            if exp:
                exps.add(exp)
        return sorted(exps)[:self.num_expirations]

    async def _publish_surface(self, r: Redis, underlying: str, surface: Dict[str, str], ts: int) -> None:
        latest_key = f"massive:surface:{underlying}:latest"
        ts_key = f"massive:surface:{underlying}:{ts}"

        pipe = r.pipeline(transaction=False)
        pipe.hset(latest_key, mapping=surface)
        pipe.expire(latest_key, self.surface_ttl_sec)

        pipe.hset(ts_key, mapping=surface)
        pipe.expire(ts_key, self.surface_ttl_sec)

        # Notify builders
        pipe.publish("massive:surface:updated", underlying)

        await pipe.execute()

        self.logger.ok(f"[SURFACE PUBLISHED] {underlying} {len(surface)} strikes", emoji="📦")

    async def _run_once(self) -> None:
        r = await self._redis_conn()
        vix = await self._load_spot("VIX")
        now_epoch = time.time()
        ts = int(now_epoch)

        for underlying in self.chain_symbols:
            spot = await self._load_spot(underlying)
            if spot is None:
                self.logger.warning(f"[CHAIN SKIP] no spot for {underlying}")
                continue

            atm = _round_to_nearest_5(spot)
            rng = self._compute_range(spot, vix)
            expirations = self._list_expirations(underlying)

            surface: Dict[str, str] = {}

            for exp in expirations:
                self.logger.info(f"[CHAIN FETCH] {underlying} {exp}", emoji="📡")
                t0 = time.monotonic()

                params = {
                    "expiration_date": exp,
                    "strike_price.gte": atm - rng,
                    "strike_price.lte": atm + rng,
                    "limit": 250,
                }

                contracts = []
                for opt in self.client.list_snapshot_options_chain(underlying, params=params):
                    raw = json.loads(json.dumps(opt, default=lambda o: o.__dict__))
                    contracts.append(raw)

                    strike = raw.get("details", {}).get("strike_price")
                    if strike is not None:
                        surface[str(strike)] = json.dumps(raw)

                latency_ms = (time.monotonic() - t0) * 1000
                self.logger.info(
                    f"[CHAIN OK] {underlying} {exp} contracts={len(contracts)} latency={latency_ms:.1f}ms",
                    emoji="✅",
                )

            if surface:
                await self._publish_surface(r, underlying, surface, ts)

            cycle_duration = time.monotonic() - time.monotonic()
            self.logger.info(
                f"[CHAIN CYCLE COMPLETE] {underlying} duration={cycle_duration:.2f}s strikes={len(surface)}",
                emoji="🔁",
            )

    async def run(self, stop_event: asyncio.Event) -> None:
        self.logger.info("[CHAIN START] running", emoji="🚀")

        try:
            while not stop_event.is_set():
                cycle_start = time.monotonic()
                await self._run_once()
                cycle_duration = time.monotonic() - cycle_start

                # Immediate next request — no fixed sleep
                backoff = max(0.5, 10.0 - cycle_duration)  # target ~10s cycle
                await asyncio.sleep(backoff)
        finally:
            self.logger.info("ChainWorker stopped", emoji="🛑")