# services/mmaker/intel/startup_chain_builder.py

import json
from typing import Dict, Any, Tuple
from redis.asyncio import Redis

from .tile_factory import build_tiles_from_chain


CHAIN_KEY_TEMPLATE = "market:chain:{underlying}:{expiry}"


async def load_chain_from_market(redis: Redis, underlying: str, expiry_iso: str) -> Dict[str, Any]:
    """
    Load the options chain from Market-Redis.
    Chain stored as JSON under:
        market:chain:{underlying}:{expiry_iso}
    """
    key = CHAIN_KEY_TEMPLATE.format(underlying=underlying, expiry=expiry_iso)
    raw = await redis.get(key)

    if not raw:
        raise RuntimeError(f"[startup_chain_builder] chain missing at key={key}")

    try:
        chain = json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"[startup_chain_builder] chain decode error: {e}")

    return chain


async def build_startup_tiles(
    redis: Redis,
    underlying: str,
    expiry_iso: str,
) -> Tuple[int, int, int, int]:
    """
    Loads the full chain and constructs all singles, verticals, and butterflies.
    Tiles are stored as HASHes in Redis.

    Returns: (num_tiles, num_singles, num_verticals, num_butterflies)
    """

    chain = await load_chain_from_market(redis, underlying, expiry_iso)

    # Run factory
    tile_keys = await build_tiles_from_chain(
        redis=redis,
        chain=chain,
        underlying=underlying,
        expiry_iso=expiry_iso
    )

    # Collect statistics
    singles = [k for k in tile_keys if ":single:" in k]
    verticals = [k for k in tile_keys if ":vertical:" in k]
    butterflies = [k for k in tile_keys if ":butterfly:" in k]

    return (len(tile_keys), len(singles), len(verticals), len(butterflies))