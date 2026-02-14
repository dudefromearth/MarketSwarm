"""
Market Source — Reads market context from market-redis.

Fetches regime, VIX, spot, GEX, and economic data that massive
publishes. Read-only, never writes to market-redis.
"""

import json
import time
from typing import Any, Dict, Optional

from redis import Redis


class MarketSource:
    """Reads market state from market-redis for snapshot hydration."""

    def __init__(self, market_redis: Redis, logger: Any):
        self._redis = market_redis
        self._logger = logger

    async def fetch(self, timeout_ms: int = 300) -> Dict[str, Any]:
        """
        Fetch market context from market-redis.

        Returns dict with regime, volatility, spot data.
        Times out gracefully — returns partial data on slow reads.
        """
        t0 = time.time()
        result: Dict[str, Any] = {}
        stale: list = []

        try:
            # VIX regime
            raw = self._redis.get("massive:vix_regime:model:SPX")
            if raw:
                data = json.loads(raw) if isinstance(raw, str) else raw
                result["volatility_tag"] = data.get("regime", "")
                result["vix_level"] = data.get("vix", data.get("level"))
            else:
                stale.append("vix_regime")

            # Market mode
            raw = self._redis.get("massive:market_mode:model:SPX")
            if raw:
                data = json.loads(raw) if isinstance(raw, str) else raw
                result["market_regime"] = data.get("mode", "")
            else:
                stale.append("market_mode")

            # Spot
            raw = self._redis.get("massive:model:spot:SPX")
            if raw:
                data = json.loads(raw) if isinstance(raw, str) else raw
                result["spot"] = data.get("price") or data.get("last")
            else:
                stale.append("spot")

            # Bias / LFI
            raw = self._redis.get("massive:bias_lfi:model:SPX")
            if raw:
                data = json.loads(raw) if isinstance(raw, str) else raw
                result["bias_lfi"] = data.get("quadrant", "")

        except Exception as e:
            self._logger.warning(f"Market source fetch error: {e}")
            stale.append("market_source_error")

        result["_stale"] = stale
        result["_latency_ms"] = int((time.time() - t0) * 1000)
        return result
