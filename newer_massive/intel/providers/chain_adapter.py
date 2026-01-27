# services/massive/intel/providers/chain_adapter.py

from typing import Dict, Any, List
import time
import httpx


async def fetch_chain_snapshot(
    symbol: str,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Fetch a full option chain snapshot for a single underlying.

    This function is intentionally dumb:
    - no Redis
    - no hydration
    - no modeling
    - no retries

    It is a pure provider adapter.
    """

    api_key = config["MASSIVE_API_KEY"]
    base_url = config.get(
        "MASSIVE_CHAIN_URL",
        "https://api.massive.com/options/chain",  # adjust if needed
    )

    params = {
        "symbol": symbol,
        "expirations": int(config.get("MASSIVE_CHAIN_NUM_EXPIRATIONS", 5)),
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(base_url, params=params, headers=headers)
        resp.raise_for_status()
        payload = resp.json()

    return {
        "symbol": symbol,
        "ts": time.time(),
        "raw": payload,
    }