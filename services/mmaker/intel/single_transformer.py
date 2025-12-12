# services/mmaker/intel/single_transformer.py

import json
import hashlib
from typing import Dict, Any

class SingleTransformer:
    """
    Maintains single-contract tiles.

    Tile key ID format:
      SINGLE:{cp}:{strike}

    Stored in Redis hash under:
      mm:tiles:{UL}:{EXP}:single
    """

    def __init__(self, redis, ul: str, exp: str):
        self.redis = redis
        self.ul = ul
        self.exp = exp

    async def update_from_trade(self, trade: Dict[str, Any]):
        cp = trade["cp"]
        strike = trade["strike"]

        tile_id = f"SINGLE:{cp}:{strike}"
        redis_key = f"mm:tiles:{self.ul}:{self.exp}:single"

        blob = {
            "type": "single",
            "ul": self.ul,
            "exp": self.exp,
            "cp": cp,
            "strike": strike,
            "last": trade["price"],
            "ts": trade["ts"],
        }

        # compute hash
        h = hashlib.sha1(json.dumps(blob, sort_keys=True).encode()).hexdigest()

        # read old hash
        old = await self.redis.hget(redis_key, tile_id)
        if old:
            old_hash = json.loads(old)["hash"]
            if old_hash == h:
                return  # no change → skip write

        # write updated tile
        await self.redis.hset(redis_key, tile_id, json.dumps({"tile": blob, "hash": h}))