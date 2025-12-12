# services/mmaker/intel/tile_factory.py

import hashlib
from typing import Dict, Any, List, Tuple


def sha1_hash(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()


# ----------------------------------------------------------
# Helpers
# ----------------------------------------------------------

def parse_oc_symbol(symbol: str) -> Tuple[str, int]:
    """
    Takes 'O:SPXW251211C06905000'
    Returns ('C', 6905000)
    """
    cp = symbol[-10]  # 'C' or 'P'
    strike = int(symbol[-9:])
    return cp, strike


def vertical_id(cp: str, strike1: int, strike2: int) -> str:
    lo = min(strike1, strike2)
    hi = max(strike1, strike2)
    return f"{cp}{lo}-{hi}"


def butterfly_id(cp: str, s1: int, s2: int, s3: int) -> str:
    sorted_strikes = sorted([s1, s2, s3])
    return f"{cp}{sorted_strikes[0]}-{sorted_strikes[1]}-{sorted_strikes[2]}"


def single_id(symbol: str) -> str:
    return symbol  # full OCC contract key


# ----------------------------------------------------------
# Tile creation
# ----------------------------------------------------------

async def build_tiles_from_chain(redis, chain: Dict[str, Any],
                                 underlying: str,
                                 expiry_iso: str) -> List[str]:
    """
    Creates ALL singles, verticals, and butterflies from the chain snapshot.
    Stores them into Redis as HASHES (unpriced initially).
    Returns list of tile keys.
    """

    tile_keys = []

    # Extract all contracts
    contracts = chain.get("contracts", [])
    parsed = []
    for c in contracts:
        cp, strike = parse_oc_symbol(c["symbol"])
        parsed.append((c["symbol"], cp, strike))

    # Build singles
    for sym, cp, strike in parsed:
        key = f"mm:tile:single:{underlying}:{expiry_iso}:{single_id(sym)}"
        await redis.hset(key, mapping={
            "last": "",
            "timestamp": "",
            "complete": 0,
            "hash": ""
        })
        tile_keys.append(key)

    # Build verticals
    by_cp = {"C": [], "P": []}
    for sym, cp, strike in parsed:
        by_cp[cp].append(strike)

    for cp, strikes in by_cp.items():
        strikes = sorted(strikes)
        for i in range(len(strikes) - 1):
            s1 = strikes[i]
            s2 = strikes[i + 1]
            vid = vertical_id(cp, s1, s2)
            key = f"mm:tile:vertical:{underlying}:{expiry_iso}:{vid}"
            await redis.hset(key, mapping={
                "last": "",
                "timestamp": "",
                "complete": 0,
                "hash": ""
            })
            tile_keys.append(key)

    # Build butterflies (width = 5 ATM assumption)
    for cp, strikes in by_cp.items():
        strikes = sorted(strikes)
        for i in range(len(strikes) - 2):
            s1 = strikes[i]
            s2 = strikes[i + 1]
            s3 = strikes[i + 2]
            bid = butterfly_id(cp, s1, s2, s3)
            key = f"mm:tile:butterfly:{underlying}:{expiry_iso}:{bid}"
            await redis.hset(key, mapping={
                "last": "",
                "timestamp": "",
                "complete": 0,
                "hash": ""
            })
            tile_keys.append(key)

    return tile_keys