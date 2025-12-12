# services/mmaker/intel/butterfly_transformer.py

import json
import hashlib
from typing import Dict, Any

class ButterflyTransformer:
    """
    Butterfly: (low, mid, high).
    All tiles exist; value computed only when all three legs present.

    Tile ID:
       FLY:{cp}:{low}:{mid}:{high}

    Redis key:
       mm:tiles:{UL}:{EXP}:butterfly
    """

    def __init__(self, redis, ul: str, exp: str, widths: list[int]):
        self.redis = redis
        self.ul = ul
        self.exp = exp
        self.widths = widths

        # local price cache
        self.last_seen = {}  # (cp, strike) -> price

    async def update_from_trade(self, trade: Dict[str, Any]):
        cp = trade["cp"]
        strike = trade["strike"]
        price = trade["price"]
        ts = trade["ts"]

        self.last_seen[(cp, strike)] = price

        redis_key = f"mm:tiles:{self.ul}:{self.exp}:butterfly"

        # recompute every fly whose legs include this strike
        for width in self.widths:

            low = strike - width
            mid = strike
            high = strike + width

            # Check all three legs
            p_low = self.last_seen.get((cp, low))
            p_mid = self.last_seen.get((cp, mid))
            p_high = self.last_seen.get((cp, high))

            if p_low is None or p_mid is None or p_high is None:
                continue

            tile_id = f"FLY:{cp}:{low}:{mid}:{high}"

            blob = {
                "type": "butterfly",
                "ul": self.ul,
                "exp": self.exp,
                "cp": cp,
                "low": low,
                "mid": mid,
                "high": high,
                "width": width,
                "legs": {
                    "low": p_low,
                    "mid": p_mid,
                    "high": p_high
                },
                "value": (p_low - 2*p_mid + p_high),
                "complete": True,
                "ts": ts,
            }

            h = hashlib.sha1(json.dumps(blob, sort_keys=True).encode()).hexdigest()

            old = await self.redis.hget(redis_key, tile_id)
            if old:
                old_hash = json.loads(old)["hash"]
                if old_hash == h:
                    continue

            await self.redis.hset(redis_key, tile_id, json.dumps({"tile": blob, "hash": h}))