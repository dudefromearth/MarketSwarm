"""
GEX Normalizer (NO-OP, ASYNC)

Purpose:
- Satisfy the normalizer registry
- Accept all pipeline arguments
- Do absolutely nothing
- Be safely awaitable
"""

from typing import Any, Dict


async def normalize_chain_snapshot_for_gex(
    *,
    snapshot: Dict[str, Any],
    **kwargs,  # accepts epoch_id, symbol, expiration, ttl_sec, etc.
) -> None:
    return None