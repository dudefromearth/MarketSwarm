from __future__ import annotations

import asyncio
import json
import time
from typing import Dict, Any

from redis.asyncio import Redis

from .epoch_manager import EpochManager


class GEXBuilder:
    """
    GEXBuilder

    Responsibilities:
    - Consume epoch heatmap ZSETs
    - Compute dealer gamma exposure (GEX)
    - Publish per-symbol GEX model
    - Mark epochs clean on success

    GEX is computed as:
      gamma * open_interest * contract_multiplier
    """

    CONTRACT_MULTIPLIER = 100

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
        self.model_prefix = "massive:gex:model"

        # Builder cadence
        self.poll_interval_sec = float(
            config.get("MASSIVE_GEX_POLL_SEC", "1.0")
        )

        self.logger.info(
            "[GEX INIT] ready",
            emoji="🟣",
        )

    # ------------------------------------------------------------
    # Main control loop
    # ------------------------------------------------------------

    async def run(self, stop_event: asyncio.Event) -> None:
        self.logger.info("[GEX RUN] starting", emoji="🚀")

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
                    f"[GEX ERROR] {e}",
                    emoji="💥",
                )
                await asyncio.sleep(1)

        self.logger.info("[GEX STOP] stopped", emoji="🛑")

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

        gex = await self._compute_gex(epoch_id, symbol)
        if not gex:
            return

        model_key = f"{self.model_prefix}:{symbol}"

        await self.redis.set(
            model_key,
            json.dumps(
                {
                    "epoch": epoch_id,
                    "symbol": symbol,
                    "generated_ts": time.time(),
                    "gex": gex,
                },
                separators=(",", ":"),
            ),
        )

        # Mark epoch clean
        await self.epoch_mgr.mark_epoch_clean(epoch_id)

        elapsed = round(time.time() - start_ts, 3)

        self.logger.info(
            f"[GEX OK] {symbol} epoch={epoch_id} ({elapsed}s)",
            emoji="✅",
        )

    # ------------------------------------------------------------
    # GEX computation
    # ------------------------------------------------------------

    async def _compute_gex(
        self,
        epoch_id: str,
        symbol: str,
    ) -> Dict[str, float]:
        """
        Computes total gamma exposure per strike.

        Output:
          { strike: gex_value }
        """

        prefix = f"epoch:{epoch_id}:heatmap:{symbol}"
        plane_keys = await self.redis.keys(f"{prefix}:*")
        if not plane_keys:
            return {}

        gex: Dict[str, float] = {}

        for zkey in plane_keys:
            entries = await self.redis.zrange(zkey, 0, -1)

            for raw in entries:
                try:
                    c = json.loads(raw)

                    strike = str(c["strike"])
                    gamma = c.get("gamma")
                    oi = c.get("oi")

                    if gamma is None or oi is None:
                        continue

                    exposure = (
                        gamma
                        * oi
                        * self.CONTRACT_MULTIPLIER
                    )

                    # Calls positive, puts negative
                    if c.get("right") == "P":
                        exposure *= -1

                    gex[strike] = gex.get(strike, 0.0) + exposure

                except Exception:
                    continue

        return gex