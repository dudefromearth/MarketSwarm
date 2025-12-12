# services/mmaker/intel/startup_tiles.py

import json
from typing import List, Dict, Any
from redis.asyncio import Redis


# ------------------------------------------------------------
# Helper: build the tile payload
# ------------------------------------------------------------

def _empty_payload(tile_type: str, ul: str, exp: str,
                   strike: int = None,
                   width: int = None,
                   legs: List[int] = None) -> str:
    """
    Construct the JSON payload for a tile.
    Stored as a string for Redis HSET.
    """

    payload = {
        "ul": ul,
        "exp": exp,
        "type": tile_type,
        "strike": strike,
        "width": width,
        "legs": legs or [],
        "last": {
            "C": None,
            "P": None,
            "ts": None
        },
        "built": False,     # true when all legs receive prices
        "hash": ""          # recomputed by transformers
    }

    return json.dumps(payload)


# ------------------------------------------------------------
# Build all Singles
# ------------------------------------------------------------

async def _prepopulate_singles(redis: Redis, ul: str, exp: str, strikes: List[int]):
    key = f"mm:tiles:{ul}:{exp}:single"

    pipe = redis.pipeline()

    for strike in strikes:
        tile_id = f"{strike}"
        payload = _empty_payload("single", ul, exp, strike=strike)
        pipe.hset(key, tile_id, payload)

    await pipe.execute()


# ------------------------------------------------------------
# Build all Verticals
# ------------------------------------------------------------

async def _prepopulate_verticals(redis: Redis, ul: str, exp: str,
                                 strikes: List[int],
                                 widths: List[int]):

    key = f"mm:tiles:{ul}:{exp}:vertical"
    pipe = redis.pipeline()

    # Example: width=5 → vertical uses legs: [strike, strike+5]
    for width in widths:
        for strike in strikes:
            s2 = strike + width
            if s2 not in strikes:
                continue

            legs = [strike, s2]
            tile_id = f"{strike}:{width}"

            payload = _empty_payload(
                "vertical",
                ul,
                exp,
                strike=strike,
                width=width,
                legs=legs
            )

            pipe.hset(key, tile_id, payload)

    await pipe.execute()


# ------------------------------------------------------------
# Build all Butterflies
# ------------------------------------------------------------

async def _prepopulate_butterflies(redis: Redis, ul: str, exp: str,
                                   strikes: List[int],
                                   widths: List[int]):

    key = f"mm:tiles:{ul}:{exp}:butterfly"
    pipe = redis.pipeline()

    # width=5 → fly legs: [s, s+5, s+10]
    for width in widths:
        for strike in strikes:
            s2 = strike + width
            s3 = strike + 2 * width
            if s2 not in strikes or s3 not in strikes:
                continue

            legs = [strike, s2, s3]
            tile_id = f"{strike}:{width}"

            payload = _empty_payload(
                "butterfly",
                ul,
                exp,
                strike=strike,
                width=width,
                legs=legs
            )

            pipe.hset(key, tile_id, payload)

    await pipe.execute()


# ------------------------------------------------------------
# Main startup entry point
# ------------------------------------------------------------

async def initialize_tiles(redis: Redis,
                           ul: str,
                           exp: str,
                           option_chain: List[Dict[str, Any]],
                           vertical_widths: List[int],
                           fly_widths: List[int]):
    """
    Build the full tile graph at startup:

    - Extract unique strikes
    - Prepopulate Singles
    - Prepopulate Verticals
    - Prepopulate Butterflies
    """

    # Extract sorted strikes from chain
    strikes = sorted({int(opt["strike"]) for opt in option_chain})

    # Build Singles
    await _prepopulate_singles(redis, ul, exp, strikes)

    # Build Verticals
    await _prepopulate_verticals(redis, ul, exp, strikes, vertical_widths)

    # Build Butterflies
    await _prepopulate_butterflies(redis, ul, exp, strikes, fly_widths)

    print(f"[startup_tiles] built tiles for {ul} {exp}: "
          f"{len(strikes)} singles, "
          f"{len(vertical_widths)} vertical widths, "
          f"{len(fly_widths)} fly widths")