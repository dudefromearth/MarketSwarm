from __future__ import annotations

import time
import uuid
from typing import Dict, Any, Optional, List

from redis.asyncio import Redis


class EpochManager:
    """
    EpochManager

    Owns the lifecycle of epochs:
      - creation
      - dirty / clean state
      - WS activity awareness
      - dormancy detection
      - forced recompute when WS is silent

    HARD INVARIANT:
      A full epoch MUST be recalculated if WS is dormant.
    """

    def __init__(self, redis: Redis, logger, config: Dict[str, Any]):
        self.redis = redis
        self.logger = logger
        self.config = config

        # ------------------------------------------------------------
        # Epoch policy
        # ------------------------------------------------------------
        # Configurable TTL in minutes (default one trading session ≈ 390 min)
        self.epoch_ttl_minutes = int(config.get("MASSIVE_EPOCH_TTL_MINUTES", 390))
        self.epoch_ttl_sec = self.epoch_ttl_minutes * 60

        self.dormant_threshold = int(
            config.get("MASSIVE_EPOCH_DORMANT_THRESHOLD", 5)
        )

        # ------------------------------------------------------------
        # Redis keys
        # ------------------------------------------------------------
        self.active_epoch_key = "epoch:active"           # hash: symbol → epoch_id
        self.epoch_meta_prefix = "epoch:meta:"           # epoch:meta:{epoch_id}
        self.epoch_dirty_set = "epoch:dirty"
        self.epoch_clean_set = "epoch:clean"
        self.epoch_timeline_prefix = "epoch:timeline:"   # epoch:timeline:{symbol}

        self.logger.info(
            f"[EPOCH INIT] ttl={self.epoch_ttl_minutes}min ({self.epoch_ttl_sec}s) "
            f"dormant_threshold={self.dormant_threshold}",
            emoji="🧬",
        )

    # ------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------

    async def ensure_epoch(
        self,
        symbol: str,
        snapshot: Dict[str, Any],
    ) -> str:
        # Always create a new epoch — one per chain snapshot
        new_epoch = await self._create_epoch(symbol, snapshot)

        # Switch active — old epoch will be cleaned by TTL
        prev_epoch = await self.redis.hget(self.active_epoch_key, symbol)
        if prev_epoch:
            await self._expire_old_epoch(prev_epoch)

        await self.redis.hset(self.active_epoch_key, symbol, new_epoch)

        self.logger.info(
            f"[EPOCH SWITCH] {symbol} active epoch → {new_epoch}",
            emoji="🔄",
        )

        return new_epoch

    async def _expire_old_epoch(self, old_epoch_id: str) -> None:
        """Apply TTL to old epoch keys"""
        pipe = self.redis.pipeline(transaction=False)
        pipe.expire(f"{self.epoch_meta_prefix}{old_epoch_id}", self.epoch_ttl_sec)
        pipe.expire(f"epoch:{old_epoch_id}:had_ws_updates", self.epoch_ttl_sec)
        await pipe.execute()

    # ------------------------------------------------------------
    # WS activity marking
    # ------------------------------------------------------------

    async def mark_ws_update(self, epoch_id: str) -> None:
        await self.redis.set(
            f"epoch:{epoch_id}:had_ws_updates",
            1,
            ex=self.epoch_ttl_sec,
        )

    # ------------------------------------------------------------
    # Epoch creation
    # ------------------------------------------------------------

    async def _create_epoch(
        self,
        symbol: str,
        snapshot: Dict[str, Any],
    ) -> str:
        epoch_id = self._generate_epoch_id(symbol)
        meta_key = f"{self.epoch_meta_prefix}{epoch_id}"

        dormant_count_key = f"epoch:{symbol}:dormant_count"
        dormant_count = int(await self.redis.get(dormant_count_key) or 0)

        prev_epoch = await self.redis.hget(self.active_epoch_key, symbol)
        prev_had_updates = False
        if prev_epoch:
            prev_had_updates = (
                await self.redis.get(f"epoch:{prev_epoch}:had_ws_updates") == "1"
            )

        if prev_epoch and not prev_had_updates:
            dormant_count += 1
        else:
            dormant_count = 0

        await self.redis.set(dormant_count_key, dormant_count, ex=self.epoch_ttl_sec)

        force_dirty = prev_epoch is None or dormant_count >= self.dormant_threshold

        created_ts = time.time()

        # Store geometry for debugging / future use
        max_strike = snapshot.get("max_strike", 0)
        min_strike = snapshot.get("min_strike", 0)
        strike_range = max_strike - min_strike

        meta = {
            "epoch_id": epoch_id,
            "symbol": symbol,
            "created_ts": str(created_ts),
            "strike_count": str(snapshot.get("strike_count")),
            "dte_count": str(snapshot.get("dte_count")),
            "strike_range": str(strike_range),
            "hash": snapshot.get("structure_hash"),
            "forced_dirty": str(int(force_dirty)),
            "dormant_count": str(dormant_count),
        }

        pipe = self.redis.pipeline(transaction=False)

        pipe.hset(meta_key, mapping=meta)
        pipe.expire(meta_key, self.epoch_ttl_sec)

        pipe.set(f"epoch:{epoch_id}:had_ws_updates", 0, ex=self.epoch_ttl_sec)

        pipe.sadd(self.epoch_dirty_set, epoch_id)
        pipe.srem(self.epoch_clean_set, epoch_id)

        timeline_key = f"{self.epoch_timeline_prefix}{symbol}"
        pipe.rpush(
            timeline_key,
            f"{int(created_ts)}|{epoch_id}|forced={int(force_dirty)}|dormant={dormant_count}",
        )
        pipe.expire(timeline_key, self.epoch_ttl_sec)

        await pipe.execute()

        self.logger.debug(
            f"[EPOCH {'FORCED DIRTY' if force_dirty else 'NEW'}] {epoch_id} dormant_count={dormant_count}",
            emoji="🧊" if force_dirty else "🆕",
        )

        return epoch_id

    # ------------------------------------------------------------
    # Compatibility check — REMOVED
    # ------------------------------------------------------------
    # We no longer reuse epochs — every chain snapshot gets its own
    # _is_epoch_compatible has been intentionally removed

    # ------------------------------------------------------------
    # Promotion / retirement
    # ------------------------------------------------------------

    async def mark_epoch_clean(self, epoch_id: str) -> None:
        pipe = self.redis.pipeline(transaction=False)
        pipe.srem(self.epoch_dirty_set, epoch_id)
        pipe.sadd(self.epoch_clean_set, epoch_id)
        await pipe.execute()

        self.logger.debug(f"[EPOCH CLEAN] {epoch_id}", emoji="🧼")

    # ------------------------------------------------------------
    # Debug / Introspection
    # ------------------------------------------------------------

    async def debug_epoch_state(
        self,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        state: Dict[str, Any] = {
            "active": {},
            "dirty": [],
            "clean": [],
            "timelines": {},
        }

        state["dirty"] = list(await self.redis.smembers(self.epoch_dirty_set))
        state["clean"] = list(await self.redis.smembers(self.epoch_clean_set))

        active = await self.redis.hgetall(self.active_epoch_key)
        for sym, epoch_id in active.items():
            if symbol and sym != symbol:
                continue

            meta = await self.redis.hgetall(f"{self.epoch_meta_prefix}{epoch_id}")
            had_ws = await self.redis.get(f"epoch:{epoch_id}:had_ws_updates")

            state["active"][sym] = {
                "epoch_id": epoch_id,
                "meta": meta,
                "had_ws_updates": bool(int(had_ws or 0)),
            }

            timeline_key = f"{self.epoch_timeline_prefix}{sym}"
            state["timelines"][sym] = await self.redis.lrange(timeline_key, 0, -1)

        return state

    # ------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------

    def _generate_epoch_id(self, symbol: str) -> str:
        ts = int(time.time() * 1000)
        uid = uuid.uuid4().hex[:6]
        return f"{symbol}:{ts}:{uid}"