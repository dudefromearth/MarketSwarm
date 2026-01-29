# services/massive/intel/spot_worker.py

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from redis.asyncio import Redis

from ..utils.get_spot import MassiveSpotClient
from massive import RESTClient  # for stock/ETF snapshot


# ============================================================
# Spot Snapshot Capture (raw diagnostic)
# ============================================================

class SpotSnapshotCapture:
    def __init__(self, capture_dir: str, logger, debug: bool = False):
        self.logger = logger
        self.debug = debug
        self.fh = None

        try:
            os.makedirs(capture_dir, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            path = os.path.join(capture_dir, f"spot_{ts}.jsonl")
            self.fh = open(path, "a", buffering=1)

            self.logger.info(f"[SPOT CAPTURE] enabled → {path}", emoji="📸")
        except Exception as e:
            self.logger.error(
                f"[SPOT CAPTURE] disabled (filesystem error): {e}",
                emoji="❌",
            )
            self.fh = None

    def write(self, payload: Dict[str, Any]) -> None:
        if self.fh:
            self.fh.write(json.dumps(payload) + "\n")


# ============================================================
# SpotWorker
# ============================================================

class SpotWorker:
    def __init__(self, config: Dict[str, Any], logger) -> None:
        self.config = config
        self.logger = logger

        api_key = config.get("MASSIVE_API_KEY")
        if not api_key:
            raise ValueError("SpotWorker requires MASSIVE_API_KEY")

        self.index_client = MassiveSpotClient(api_key=api_key)
        self.general_client = RESTClient(api_key)

        # ====================================================
        # Timing + timeouts (NEW)
        # ====================================================
        self.interval_sec = int(config.get("MASSIVE_SPOT_INTERVAL_SEC", "1"))

        self.index_timeout = float(config.get("MASSIVE_SPOT_INDEX_TIMEOUT_SEC", "2.0"))
        self.stock_timeout = float(config.get("MASSIVE_SPOT_STOCK_TIMEOUT_SEC", "2.5"))
        self.tick_timeout = float(config.get("MASSIVE_SPOT_TICK_TIMEOUT_SEC", "5.0"))
        self.redis_timeout = float(config.get("MASSIVE_REDIS_OP_TIMEOUT_SEC", "1.0"))

        self.trail_window_sec = int(config.get("MASSIVE_SPOT_TRAIL_WINDOW_SEC", 86400))
        self.trail_ttl_sec = int(config.get("MASSIVE_SPOT_TRAIL_TTL_SEC", 172800))

        market_url = config["buses"]["market-redis"]["url"]
        self.r: Redis = Redis.from_url(market_url, decode_responses=True)

        self.index_symbols = [
            s.strip() for s in config.get("MASSIVE_SPOT_SYMBOLS", "").split(",") if s.strip()
        ]
        self.stock_symbols = [
            s.strip() for s in config.get("MASSIVE_STOCK_SYMBOLS", "").split(",") if s.strip()
        ]

        self.indices_needing_prefix = {"SPX", "NDX", "VIX"}
        self.last_payloads: Dict[str, Dict] = {}

        self.analytics_key = "massive:spot:analytics"

        self.spot_capture: Optional[SpotSnapshotCapture] = None
        if config.get("MASSIVE_WS_CAPTURE", "false").lower() == "true":
            cap_dir = config.get("MASSIVE_WS_CAPTURE_SPOT_DIR")
            if cap_dir:
                self.spot_capture = SpotSnapshotCapture(cap_dir, logger)

        self.logger.info(
            f"SpotWorker running (interval={self.interval_sec}s)",
            emoji="🌐",
        )

    # ========================================================
    # Helpers
    # ========================================================

    def _api_symbol(self, sym: str) -> str:
        return f"I:{sym}" if sym in self.indices_needing_prefix else sym

    def _latest_key(self, sym: str) -> str:
        return f"massive:model:spot:{sym}"

    def _trail_key(self, sym: str) -> str:
        return f"massive:model:spot:{sym}:trail"

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    async def _redis_safe(self, coro):
        try:
            return await asyncio.wait_for(coro, timeout=self.redis_timeout)
        except asyncio.TimeoutError:
            await self.r.hincrby(self.analytics_key, "timeouts_redis", 1)
            return None

    # ========================================================
    # Fetchers (timeout wrapped)
    # ========================================================

    async def _fetch_index_spot(self, sym: str) -> Optional[float]:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self.index_client.get_spot, self._api_symbol(sym)),
                timeout=self.index_timeout,
            )
        except asyncio.TimeoutError:
            await self.r.hincrby(self.analytics_key, "timeouts_index", 1)
        except Exception as e:
            self.logger.error(f"index spot failed {sym}: {e}", emoji="💥")
        return None

    async def _fetch_stock_spot(self, sym: str) -> Optional[Dict]:
        try:
            snapshot = await asyncio.wait_for(
                asyncio.to_thread(
                    self.general_client.get_snapshot_ticker, "stocks", sym
                ),
                timeout=self.stock_timeout,
            )

            day = snapshot.day
            minute = snapshot.min
            if not day or not minute or not day.volume:
                return None

            return {
                "symbol": sym,
                "value": day.close,
                "open": day.open,
                "high": day.high,
                "low": day.low,
                "close": day.close,
                "volume": day.volume,
                "ts_epoch_ms": minute.timestamp,
                "ts": datetime.fromtimestamp(
                    minute.timestamp / 1000, tz=timezone.utc
                ).isoformat(timespec="seconds"),
                "source": "massive/spot",
                "instrument_type": "ETF",
                "timeframe": "REAL-TIME",
            }

        except asyncio.TimeoutError:
            await self.r.hincrby(self.analytics_key, "timeouts_stock", 1)
        except Exception as e:
            self.logger.error(f"stock spot failed {sym}: {e}", emoji="💥")
        return None

    # ========================================================
    # Processing
    # ========================================================

    async def _process_spot_update(self, payload: Dict, now_epoch: float) -> None:
        sym = payload["symbol"]
        if self.last_payloads.get(sym) == payload:
            return

        self.last_payloads[sym] = payload
        snap = json.dumps(payload)

        await self._redis_safe(self.r.set(self._latest_key(sym), snap))
        await self._redis_safe(self.r.zadd(self._trail_key(sym), {snap: now_epoch}))
        await self._redis_safe(
            self.r.zremrangebyscore(
                self._trail_key(sym), 0, now_epoch - self.trail_window_sec
            )
        )
        await self._redis_safe(self.r.expire(self._trail_key(sym), self.trail_ttl_sec))

        if self.spot_capture:
            self.spot_capture.write(payload)

        self.logger.debug(
            f"spot updated {sym}={payload['value']}",
            emoji="📡",
        )

    # ========================================================
    # Tick loop (hard timeout)
    # ========================================================

    async def _tick_once(self) -> None:
        now_epoch = time.time()

        for sym in self.index_symbols:
            val = await self._fetch_index_spot(sym)
            if val is not None:
                await self._process_spot_update(
                    {
                        "symbol": sym,
                        "value": val,
                        "ts": self._now_iso(),
                        "source": "massive/spot",
                        "timeframe": "REAL-TIME",
                    },
                    now_epoch,
                )

        for sym in self.stock_symbols:
            payload = await self._fetch_stock_spot(sym)
            if payload:
                await self._process_spot_update(payload, now_epoch)

    async def run(self, stop_event: asyncio.Event) -> None:
        try:
            while not stop_event.is_set():
                try:
                    await asyncio.wait_for(
                        self._tick_once(),
                        timeout=self.tick_timeout,
                    )
                except asyncio.TimeoutError:
                    await self.r.hincrby(self.analytics_key, "timeouts_tick", 1)

                await asyncio.sleep(self.interval_sec)

        finally:
            await self.r.close()
            self.logger.info("SpotWorker stopped", emoji="🛑")