"""
GEX Model Builder (Final – FIXED + INSTRUMENTED + PUBLISH LOGS)

Consumes:
  massive:chain:snapshot:{symbol}:{expiration}:*

Produces:
  massive:gex:model:{symbol}:calls
  massive:gex:model:{symbol}:puts

Instrumentation:
  massive:model:analytics (shared HASH)
  - gex:runs
  - gex:last_ts
  - gex:last_levels
  - gex:latency_last_ms
  - gex:latency_avg_ms
  - gex:latency_count
  - model:errors (on exception)
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Dict, Any, DefaultDict
from collections import defaultdict

from redis.asyncio import Redis

from ..intel.epoch_manager import EpochManager


class GexModelBuilder:
    ANALYTICS_KEY = "massive:model:analytics"
    BUILDER_NAME = "gex"

    def __init__(self, config: Dict[str, Any], logger):
        self.config = config
        self.logger = logger

        self.interval_sec = int(
            config.get("MASSIVE_GEX_INTERVAL_SEC", 1)
        )

        self.redis_url = config["buses"]["market-redis"]["url"]
        self._redis: Redis | None = None
        self.epoch_manager: EpochManager | None = None

        self.logger.info(
            "[GEX BUILDER INIT] ready",
            emoji="🧮",
        )

    async def _redis_conn(self) -> Redis:
        if not self._redis:
            self._redis = Redis.from_url(
                self.redis_url,
                decode_responses=True,
            )
            self.epoch_manager = EpochManager(
                self._redis, self.logger, self.config
            )
        return self._redis

    async def _build_once(self) -> None:
        r = await self._redis_conn()
        pipe = r.pipeline(transaction=False)

        t_start = time.monotonic()  # Start timing for latency

        symbols = [
            s.strip()
            for s in self.config.get(
                "MASSIVE_CHAIN_SYMBOLS", "SPX"
            ).split(",")
            if s.strip()
        ]

        total_levels = 0

        try:
            for symbol in symbols:
                keys = await r.keys(
                    f"massive:chain:snapshot:{symbol}:*"
                )

                calls: Dict[str, DefaultDict[str, float]] = {}
                puts: Dict[str, DefaultDict[str, float]] = {}

                if keys:
                    raw_snaps = await r.mget(keys)

                    for raw in raw_snaps:
                        if not raw:
                            continue

                        try:
                            snap = json.loads(raw)
                        except Exception:
                            continue

                        expiration = snap.get("expiration")
                        if not expiration:
                            continue

                        if expiration not in calls:
                            calls[expiration] = defaultdict(float)
                            puts[expiration] = defaultdict(float)

                        for c in snap.get("contracts", []):
                            details = c.get("details", {})
                            greeks = c.get("greeks", {})

                            strike = details.get("strike_price")
                            cp = details.get("contract_type")
                            gamma = greeks.get("gamma")
                            oi = c.get("open_interest")
                            mult = details.get("shares_per_contract", 100)

                            if (
                                strike is None
                                or gamma is None
                                or oi is None
                                or cp not in ("call", "put")
                            ):
                                continue

                            gex = gamma * oi * mult

                            if cp == "call":
                                calls[expiration][str(strike)] += gex
                            else:
                                puts[expiration][str(strike)] += gex

                ts = time.time()

                calls_model = {
                    "symbol": symbol,
                    "ts": ts,
                    "expirations": {
                        exp: dict(levels)
                        for exp, levels in calls.items()
                    },
                }

                puts_model = {
                    "symbol": symbol,
                    "ts": ts,
                    "expirations": {
                        exp: dict(levels)
                        for exp, levels in puts.items()
                    },
                }

                # Publish with explicit log
                await r.set(
                    f"massive:gex:model:{symbol}:calls",
                    json.dumps(calls_model),
                    ex=30,
                )
                self.logger.info(f"[MODEL PUBLISHED] massive:gex:model:{symbol}:calls", emoji="📦")

                await r.set(
                    f"massive:gex:model:{symbol}:puts",
                    json.dumps(puts_model),
                    ex=30,
                )
                self.logger.info(f"[MODEL PUBLISHED] massive:gex:model:{symbol}:puts", emoji="📦")

                levels = (
                    sum(len(v) for v in calls.values())
                    + sum(len(v) for v in puts.values())
                )
                total_levels += levels

                # Mark epoch clean if one exists
                epoch_id = await r.hget("epoch:active", symbol)
                if epoch_id:
                    await self.epoch_manager.mark_epoch_clean(epoch_id)

            # ------------------------------------------------
            # Instrumentation (after successful run)
            # ------------------------------------------------
            pipe.incr(f"{self.ANALYTICS_KEY}:{self.BUILDER_NAME}:runs")
            pipe.set(f"{self.ANALYTICS_KEY}:{self.BUILDER_NAME}:last_ts", time.time())
            pipe.hincrby(f"{self.ANALYTICS_KEY}", f"{self.BUILDER_NAME}:levels_total", total_levels)

        except Exception as e:
            pipe.incr(f"{self.ANALYTICS_KEY}:model:errors")
            self.logger.error(f"[GEX BUILDER ERROR] {e}", emoji="💥")
            raise

        finally:
            # Latency calculation
            dt = time.monotonic() - t_start
            latency_ms = int(dt * 1000)

            count = await r.hincrby(f"{self.ANALYTICS_KEY}", f"{self.BUILDER_NAME}:latency_count", 1)
            prev_avg = float(await r.get(f"{self.ANALYTICS_KEY}:{self.BUILDER_NAME}:latency_avg_ms") or 0)
            new_avg = (prev_avg * (count - 1) + latency_ms) / count if count > 1 else latency_ms

            pipe.set(f"{self.ANALYTICS_KEY}:{self.BUILDER_NAME}:latency_last_ms", latency_ms)
            pipe.set(f"{self.ANALYTICS_KEY}:{self.BUILDER_NAME}:latency_avg_ms", int(new_avg))

            await pipe.execute()

        self.logger.info(
            f"[GEX MODEL] total_levels={total_levels} latency={latency_ms}ms",
            emoji="📊",
        )

    async def run(self, stop_event: asyncio.Event) -> None:
        self.logger.info(
            "[GEX BUILDER START] running",
            emoji="🔥",
        )

        try:
            while not stop_event.is_set():
                t0 = time.monotonic()
                await self._build_once()
                dt = time.monotonic() - t0
                await asyncio.sleep(
                    max(0.0, self.interval_sec - dt)
                )
        finally:
            self.logger.info(
                "GexModelBuilder stopped",
                emoji="🛑",
            )