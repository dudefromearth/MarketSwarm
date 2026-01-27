from __future__ import annotations

import time
from typing import Dict, Any

from redis.asyncio import Redis


class HeatmapBuilder:
    """
    HeatmapBuilder

    Builds and maintains the heatmap model for an epoch.

    Flow:
      epoch created →
      chain snapshot decomposed →
      ZSET substrate populated →
      WS hydration →
      calculate →
      publish →
      epoch marked clean
    """

    def __init__(
        self,
        redis: Redis,
        logger,
        config: Dict[str, Any],
        epoch_mgr,
    ):
        self.redis = redis
        self.logger = logger
        self.config = config
        self.epoch_mgr = epoch_mgr

        # Redis keys
        self.model_key = "massive:heatmap:model"

        # Heatmap policy
        self.snapshot_interval_sec = int(
            config.get("MASSIVE_HEATMAP_SNAPSHOT_SEC", "5")
        )

        self.logger.info(
            "[HEATMAP INIT] ready",
            emoji="🧊",
        )

    # ------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------

    async def process(
        self,
        symbol: str,
        epoch_id: str,
        snapshot: Dict[str, Any],
    ) -> None:
        """
        Called by ChainWorker after snapshot + epoch resolution.
        """

        # Build substrate ZSET
        await self._build_substrate(symbol, epoch_id, snapshot)

        # Calculate heatmap tiles
        model = await self._calculate(symbol, epoch_id)

        if model:
            await self._publish(symbol, epoch_id, model)
            await self.epoch_mgr.mark_epoch_clean(epoch_id)

    # ------------------------------------------------------------
    # Substrate
    # ------------------------------------------------------------

    async def _build_substrate(
        self,
        symbol: str,
        epoch_id: str,
        snapshot: Dict[str, Any],
    ) -> None:
        """
        Decompose chain snapshot into a heatmap substrate ZSET.

        ZSET score = normalized DTE
        ZSET member = compact strike descriptor
        """

        zkey = f"epoch:{epoch_id}:heatmap"

        pipe = self.redis.pipeline(transaction=False)

        for opt in snapshot["options"]:
            strike = opt.strike_price
            dte = opt.days_to_expiration

            score = float(dte)

            member = f"{strike}"

            pipe.zadd(zkey, {member: score})

        pipe.expire(
            zkey,
            int(self.config.get("MASSIVE_EPOCH_TTL_SEC", "300")),
        )

        await pipe.execute()

        self.logger.info(
            f"[HEATMAP SUBSTRATE] {symbol} {epoch_id}",
            emoji="🧱",
        )

    # ------------------------------------------------------------
    # Calculation
    # ------------------------------------------------------------

    async def _calculate(
        self,
        symbol: str,
        epoch_id: str,
    ) -> Dict[str, Any] | None:
        """
        Convert hydrated substrate into a finalized heatmap model.
        """

        zkey = f"epoch:{epoch_id}:heatmap"

        strikes = await self.redis.zrange(zkey, 0, -1, withscores=True)
        if not strikes:
            return None

        tiles = []

        for strike, dte in strikes:
            tiles.append(
                {
                    "strike": float(strike),
                    "dte": int(dte),
                    "value": 0.0,  # hydrated later by WS
                    "dirty": False,
                }
            )

        return {
            "symbol": symbol,
            "epoch": epoch_id,
            "ts": time.time(),
            "tiles": tiles,
        }

    # ------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------

    async def _publish(
        self,
        symbol: str,
        epoch_id: str,
        model: Dict[str, Any],
    ) -> None:
        """
        Publish finalized heatmap model.
        """

        key = f"{self.model_key}:{symbol}"

        await self.redis.set(key, str(model))

        self.logger.info(
            f"[HEATMAP PUBLISHED] {symbol} {epoch_id}",
            emoji="📤",
        )