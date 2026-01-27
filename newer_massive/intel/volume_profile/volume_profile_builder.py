from __future__ import annotations

import asyncio
import json
import time
from typing import Dict, Any

from redis.asyncio import Redis

from .epoch_manager import EpochManager


class VolumeProfileBuilder:
    """
    VolumeProfileBuilder

    Responsibilities:
    - Consume epoch WS-hydrated contracts
    - Aggregate volume by strike
    - Publish per-symbol volume profile
    - Mark epoch clean on success

    Volume profile is strike → total traded size.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        logger,
        redis: Redis | None = None,
    ):
        self.logger = logger
        self.config = config

        # Redis
        self.redis = redis or Redis.from_url(
            config["buses"]["market-redis"]["url"],
            decode_responses=True,
        )

        # Epoch manager
        self.epoch_mgr = EpochManager(self.redis, logger, config)

        # Keys
        self.epoch_dirty_set = "epoch:dirty"
        self.model_prefix = "massive:volume_profile:model"

        # Cadence
        self.poll_interval_sec = float(
            config.get("MASSIVE_VOLUME_PROFILE_POLL_SEC", "1.0")
        )

        self.logger.info(
            "[VP INIT] ready",
            emoji="📊",
        )

    # ------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------

    async def run(self, stop_event: asyncio.Event) -> None:
        self.logger.info("[VP RUN] starting", emoji="🚀")

        while not stop_event.is_set():
            try:
                epoch_id = await self._get_next_dirty_epoch()
                if not epoch_id:
                    await asyncio.sleep(self.poll_interval_sec)
                    continue

                await self._build_epoch(epoch_id)

            except asyncio.CancelledError:
                break

            except Exception as e:
                self.logger.error(
                    f"[VP ERROR] {e}",
                    emoji="💥",
                )
                await asyncio.sleep(1)

        self.logger.info("[VP STOP] stopped", emoji="🛑")

    # ------------------------------------------------------------
    # Epoch selection
    # ------------------------------------------------------------

    async def _get_next_dirty_epoch(self) -> str | None:
        return await self.redis.srandmember(self.epoch_dirty_set)

    # ------------------------------------------------------------
    # Epoch build
    # ------------------------------------------------------------

    async def _build_epoch(self, epoch_id: str) -> None:
        start_ts = time.time()

        meta = await self.redis.hgetall(f"epoch:meta:{epoch_id}")
        if not meta:
            await self.redis.srem(self.epoch_dirty_set, epoch_id)
            return

        symbol = meta["symbol"]

        profile = await self._compute_volume_profile(epoch_id, symbol)
        if not profile:
            return

        model_key = f"{self.model_prefix}:{symbol}"

        await self.redis.set(
            model_key,
            json.dumps(
                {
                    "epoch": epoch_id,
                    "symbol": symbol,
                    "generated_ts": time.time(),
                    "volume_profile": profile,
                },
                separators=(",", ":"),
            ),
        )

        await self.epoch_mgr.mark_epoch_clean(epoch_id)

        elapsed = round(time.time() - start_ts, 3)

        self.logger.info(
            f"[VP OK] {symbol} epoch={epoch_id} ({elapsed}s)",
            emoji="✅",
        )

    # ------------------------------------------------------------
    # Volume computation
    # ------------------------------------------------------------

    async def _compute_volume_profile(
        self,
        epoch_id: str,
        symbol: str,
    ) -> Dict[str, int]:
        """
        Aggregates WS-hydrated volume by strike.

        Output:
          { strike: total_size }
        """

        prefix = f"epoch:{epoch_id}:ws:{symbol}"
        zkeys = await self.redis.keys(f"{prefix}:*")
        if not zkeys:
            return {}

        volume: Dict[str, int] = {}

        for zkey in zkeys:
            entries = await self.redis.zrange(zkey, 0, -1)

            for raw in entries:
                try:
                    c = json.loads(raw)

                    strike = str(c["strike"])
                    size = int(c.get("size", 0))

                    if size <= 0:
                        continue

                    volume[strike] = volume.get(strike, 0) + size

                except Exception:
                    continue

        return volume
