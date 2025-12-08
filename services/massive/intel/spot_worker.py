# services/massive/intel/spot_worker.py

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict

from redis.asyncio import Redis

from .utils.get_spot import MassiveSpotClient

# Robust import for logutil, regardless of how module is executed
try:
    # Preferred: package-relative when intel is a subpackage of massive
    from .. import logutil  # type: ignore[import]
except ImportError:
    # Fallback: direct import when massive/ is on sys.path (as main.py does)
    import logutil  # type: ignore[no-redef]


class SpotWorker:
    """
    Periodically fetches spot for primary index + VIX and publishes:

      massive:model:spot:{SYM}        -> latest snapshot (STRING JSON)
      massive:model:spot:{SYM}:trail  -> ZSET of snapshots, score=epoch

    Cadence (frequency + TTL) is fully controlled by env:

      MASSIVE_SPOT_INTERVAL_SEC        -> seconds between spot fetches
      MASSIVE_SPOT_TRAIL_WINDOW_SEC    -> how far back to keep in ZSET
      MASSIVE_SPOT_TRAIL_TTL_SEC       -> Redis TTL on trail keys
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.service_name = config.get("service_name", "massive")

        env = config.get("env", {})

        # --- API key / Massive client --------------------------------------
        api_key = env.get("MASSIVE_API_KEY") or os.getenv("MASSIVE_API_KEY", "")
        if not api_key:
            raise ValueError("SpotWorker requires MASSIVE_API_KEY in environment")

        self.client = MassiveSpotClient(api_key=api_key)

        # --- Cadence: frequency + TTL --------------------------------------
        self.interval_sec = int(
            env.get("MASSIVE_SPOT_INTERVAL_SEC")
            or os.getenv("MASSIVE_SPOT_INTERVAL_SEC", "1")
        )

        # Rolling window length for trail (e.g. 86400 = 24h)
        self.trail_window_sec = int(
            env.get("MASSIVE_SPOT_TRAIL_WINDOW_SEC")
            or os.getenv("MASSIVE_SPOT_TRAIL_WINDOW_SEC", "86400")
        )

        # Hard TTL on trail keys (e.g. 172800 = 48h)
        self.trail_ttl_sec = int(
            env.get("MASSIVE_SPOT_TRAIL_TTL_SEC")
            or os.getenv("MASSIVE_SPOT_TRAIL_TTL_SEC", "172800")
        )

        # --- Market-Redis client -------------------------------------------
        market_url = env.get("MARKET_REDIS_URL") or os.getenv(
            "MARKET_REDIS_URL", "redis://127.0.0.1:6380"
        )
        self.r: Redis = Redis.from_url(market_url, decode_responses=True)

        # --- Symbols: primary index + VIX ----------------------------------
        api_symbol = os.getenv("MASSIVE_SYMBOL", "I:SPX")
        self.symbol_map = {
            api_symbol: api_symbol.replace("I:", ""),  # "I:SPX" -> "SPX"
            "I:VIX": "VIX",
        }

    # ------------------------------------------------------------------ utils
    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _latest_key(self, sym: str) -> str:
        return f"massive:model:spot:{sym}"

    def _trail_key(self, sym: str) -> str:
        return f"massive:model:spot:{sym}:trail"

    # ------------------------------------------------------------------ core
    async def _tick_once(self) -> None:
        """
        One cadence tick: fetch spot for each symbol, update latest + trail.
        """
        now_epoch = time.time()

        for api_sym, sym in self.symbol_map.items():
            try:
                spot_val = self.client.get_spot(api_sym)
            except Exception as e:
                logutil.log(
                    self.service_name,
                    "ERROR",
                    "💥",
                    f"spot fetch failed for {api_sym}: {e}",
                )
                continue

            payload = {
                "symbol": sym,
                "api_symbol": api_sym,
                "value": spot_val,
                "ts": self._now_iso(),
                "source": "massive/spot",
                "timeframe": "REAL-TIME",
            }
            snap = json.dumps(payload)

            # latest
            latest_key = self._latest_key(sym)
            await self.r.set(latest_key, snap)

            # trail (ZSET with rolling window)
            trail_key = self._trail_key(sym)
            await self.r.zadd(trail_key, {snap: now_epoch})
            await self.r.zremrangebyscore(
                trail_key,
                0,
                now_epoch - self.trail_window_sec,
            )
            await self.r.expire(trail_key, self.trail_ttl_sec)

            logutil.log(
                self.service_name,
                "INFO",
                "📡",
                f"spot updated {sym}={spot_val} "
                f"(latest={latest_key}, trail={trail_key})",
            )

    async def run(self, stop_event: asyncio.Event) -> None:
        """
        Worker loop. Runs until stop_event is set.
        """
        logutil.log(
            self.service_name,
            "INFO",
            "🌐",
            f"SpotWorker running "
            f"(interval={self.interval_sec}s, "
            f"window={self.trail_window_sec}s, ttl={self.trail_ttl_sec}s)",
        )

        try:
            while not stop_event.is_set():
                await self._tick_once()
                await asyncio.sleep(self.interval_sec)
        finally:
            await self.r.close()
            logutil.log(self.service_name, "INFO", "🛑", "SpotWorker stopped")