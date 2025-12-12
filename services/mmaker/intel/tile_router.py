# services/mmaker/intel/tile_router.py

import json
from typing import Dict, Any, List
from redis.asyncio import Redis
from .tile_hash import compute_tile_hash


class TileRouter:
    """
    The central dispatcher:
    - Receives normalized trades (strike, cp_flag, price, ts)
    - Updates Singles
    - Updates Verticals (if strike matches a leg)
    - Updates Butterflies (if strike matches a leg)
    - Computes new hash
    - Publishes tile if hash changed
    """

    def __init__(self, redis: Redis, ul: str, exp: str, publisher):
        self.redis = redis
        self.ul = ul
        self.exp = exp
        self.publisher = publisher  # callback to publish updated model slices

    # ------------------------------------------------------------
    # SINGLE UPDATE
    # ------------------------------------------------------------
    async def update_single(self, strike: int, cp: str, price: float, ts: int):
        key = f"mm:tiles:{self.ul}:{self.exp}:single"
        tid = f"{strike}"

        raw = await self.redis.hget(key, tid)
        if not raw:
            return  # shouldn't happen if startup prepopulated properly

        tile = json.loads(raw)

        # Update last values
        tile["last"][cp] = price
        tile["last"]["ts"] = ts

        # Compute new hash
        new_hash = compute_tile_hash(tile)
        if new_hash != tile["hash"]:
            tile["hash"] = new_hash
            await self.redis.hset(key, tid, json.dumps(tile))
            await self.publisher("single", tid, tile)

    # ------------------------------------------------------------
    # VERTICAL UPDATE
    # ------------------------------------------------------------
    async def update_verticals(self, strike: int, cp: str, price: float, ts: int):
        key = f"mm:tiles:{self.ul}:{self.exp}:vertical"

        # Scan for any vertical that has this strike in its legs
        all_tiles = await self.redis.hgetall(key)
        for tid, raw in all_tiles.items():
            tile = json.loads(raw)
            if strike not in tile["legs"]:
                continue

            # Update leg
            tile["last"][cp] = price
            tile["last"]["ts"] = ts

            # Built if both C and P have values OR both legs are priced
            tile["built"] = (tile["last"]["C"] is not None and tile["last"]["P"] is not None)

            new_hash = compute_tile_hash(tile)
            if new_hash != tile["hash"]:
                tile["hash"] = new_hash
                await self.redis.hset(key, tid, json.dumps(tile))
                await self.publisher("vertical", tid, tile)

    # ------------------------------------------------------------
    # BUTTERFLY UPDATE
    # ------------------------------------------------------------
    async def update_butterflies(self, strike: int, cp: str, price: float, ts: int):
        key = f"mm:tiles:{self.ul}:{self.exp}:butterfly"

        all_tiles = await self.redis.hgetall(key)
        for tid, raw in all_tiles.items():
            tile = json.loads(raw)
            if strike not in tile["legs"]:
                continue

            # Update one leg
            tile["last"][cp] = price
            tile["last"]["ts"] = ts

            # Built when all three legs have last prices
            tile["built"] = (
                tile["last"]["C"] is not None and
                tile["last"]["P"] is not None
            )

            new_hash = compute_tile_hash(tile)
            if new_hash != tile["hash"]:
                tile["hash"] = new_hash
                await self.redis.hset(key, tid, json.dumps(tile))
                await self.publisher("butterfly", tid, tile)

    # ------------------------------------------------------------
    # Main dispatch entry
    # ------------------------------------------------------------
    async def process_trade(self, strike: int, cp: str, price: float, ts: int):
        await self.update_single(strike, cp, price, ts)
        await self.update_verticals(strike, cp, price, ts)
        await self.update_butterflies(strike, cp, price, ts)