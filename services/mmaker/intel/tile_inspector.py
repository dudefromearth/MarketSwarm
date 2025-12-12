# services/mmaker/intel/tile_inspector.py

import json
from typing import Optional, Dict, Any, List
from redis.asyncio import Redis


class TileInspector:
    """
    Professional-grade, read-only inspection toolkit for mmaker tiles.
    """

    def __init__(self, redis: Redis, ul: str, exp: str):
        self.redis = redis
        self.ul = ul
        self.exp = exp

    # ------------------------------------------------------------
    # Fetch All
    # ------------------------------------------------------------
    async def fetch_all(self, strategy: str) -> Dict[str, Any]:
        key = f"mm:tiles:{self.ul}:{self.exp}:{strategy}"
        raw = await self.redis.hgetall(key)
        return {tid: json.loads(blob) for tid, blob in raw.items()}

    # ------------------------------------------------------------
    # Pretty Print
    # ------------------------------------------------------------
    def pretty(self, tile: Dict[str, Any]) -> str:
        legs = tile.get("legs", [])
        last = tile.get("last", {})
        built = tile.get("built", False)
        h = tile.get("hash", "—")
        return (
            f"legs={legs} | last={last} | built={built} | hash={h}"
        )

    # ------------------------------------------------------------
    # Filter helpers
    # ------------------------------------------------------------
    def filter_by_strike(self, tiles: Dict[str, Any], strike: int):
        return {tid: t for tid, t in tiles.items() if strike in t.get("legs", [])}

    def filter_built(self, tiles: Dict[str, Any]):
        return {tid: t for tid, t in tiles.items() if t.get("built")}

    def filter_unbuilt(self, tiles: Dict[str, Any]):
        return {tid: t for tid, t in tiles.items() if not t.get("built")}

    # ------------------------------------------------------------
    # Unified Query Interface
    # ------------------------------------------------------------
    async def inspect(
        self,
        strategy: str,
        strike: Optional[int] = None,
        built: Optional[bool] = None,
        limit: Optional[int] = None,
    ) -> List[str]:
        """
        Returns pretty-printed rows.
        Perfect for human inspection or logs.
        """
        tiles = await self.fetch_all(strategy)

        # Apply filters
        if strike is not None:
            tiles = self.filter_by_strike(tiles, strike)

        if built is True:
            tiles = self.filter_built(tiles)
        elif built is False:
            tiles = self.filter_unbuilt(tiles)

        # Optional limit
        items = list(tiles.items())
        if limit:
            items = items[:limit]

        # Pretty-print each tile
        return [f"{tid}: {self.pretty(tile)}" for tid, tile in items]