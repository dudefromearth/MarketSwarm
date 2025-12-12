# services/mmaker/intel/vertical_transformer.py

import json
import hashlib
from typing import Dict, Any

class VerticalTransformer:
    """
    Vertical depends on two strikes: (strike, strike + width)

    Tile ID:
       VERT:{cp}:{low}:{high}

    Redis key:
       mm:tiles:{UL}:{EXP}:vertical
    """

    def __init__(self, redis, ul: str, exp: str, widths: list[int]):
        self.redis = redis
        self.ul = ul
        self.exp = exp
        self.widths = widths

        # local table of last quotes
        self.last_seen = {}  # (cp, strike) -> price

    async def update_from_trade(self, trade: Dict[str, Any]):
        cp = trade["cp"]
        strike = trade["strike"]
        price = trade["price"]
        ts = trade["ts"]

        self.last_seen[(cp, strike)] = price

        redis_key = f"mm:tiles:{self.ul}:{self.exp}:vertical"

        # recompute all verticals using this strike across all widths
        for width in self.widths:
            high = strike + width
            low = strike

            # both legs needed
            p_low = self.last_seen.get((cp, low))
            p_high = self.last_seen.get((cp, high))
            if p_low is None or p_high is None:
                continue

            tile_id = f"VERT:{cp}:{low}:{high}"
            blob = {
                "type": "vertical",
                "ul": self.ul,
                "exp": self.exp,
                "cp": cp,
                "low": low,
                "high": high,
                "width": width,
                "legs": {
                    "low": p_low,
                    "high": p_high,
                },
                "value": p_low - p_high,
                "ts": ts,
            }

            h = hashlib.sha1(json.dumps(blob, sort_keys=True).encode()).hexdigest()

            old = await self.redis.hget(redis_key, tile_id)
            if old:
                old_hash = json.loads(old)["hash"]
                if old_hash == h:
                    continue

            await self.redis.hset(redis_key, tile_id, json.dumps({"tile": blob, "hash": h}))