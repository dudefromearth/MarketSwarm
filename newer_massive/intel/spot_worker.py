# services/massive/intel/spot_worker.py

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from redis.asyncio import Redis

from .utils.get_spot import MassiveSpotClient
from massive import RESTClient  # for stock/ETF snapshot


# ============================================================
# Spot Snapshot Capture (raw diagnostic)
# ============================================================

class SpotSnapshotCapture:
    def __init__(self, capture_dir: str, logger, debug: bool = False):
        self.logger = logger
        self.debug = debug
        self.fh = None

        if self.debug:
            self.logger.info(
                f"[SPOT CAPTURE DEBUG] init dir={capture_dir}",
                emoji="🧪",
            )

        try:
            os.makedirs(capture_dir, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            path = os.path.join(capture_dir, f"spot_{ts}.jsonl")
            self.fh = open(path, "a", buffering=1)

            self.logger.info(
                f"[SPOT CAPTURE] enabled → {path}",
                emoji="📸",
            )
        except Exception as e:
            self.logger.error(
                f"[SPOT CAPTURE] disabled (filesystem error): {e}",
                emoji="❌",
            )
            self.fh = None

    def write(self, payload: Dict[str, Any]) -> None:
        if not self.fh:
            if self.debug:
                self.logger.info(
                    "[SPOT CAPTURE DEBUG] write skipped (fh=None)",
                    emoji="🧪",
                )
            return

        if self.debug:
            self.logger.info(
                f"[SPOT CAPTURE DEBUG] writing {payload.get('symbol')}",
                emoji="🧪",
            )

        self.fh.write(json.dumps(payload) + "\n")


# ============================================================
# SpotWorker
# ============================================================

class SpotWorker:
    def __init__(self, config: Dict[str, Any], logger) -> None:
        self.config = config
        self.logger = logger
        self.service_name = config.get("service_name", "massive")

        self.debug = config.get("DEBUG_MASSIVE", "false").lower() == "true"

        api_key = config.get("MASSIVE_API_KEY", "")
        if not api_key:
            raise ValueError("SpotWorker requires MASSIVE_API_KEY in config")

        self.index_client = MassiveSpotClient(api_key=api_key)
        self.general_client = RESTClient(api_key)  # for SPY, QQQ

        self.interval_sec = int(config.get("MASSIVE_SPOT_INTERVAL_SEC", "1"))
        self.trail_window_sec = int(config.get("MASSIVE_SPOT_TRAIL_WINDOW_SEC", 86400))
        self.trail_ttl_sec = int(config.get("MASSIVE_SPOT_TRAIL_TTL_SEC", 172800))

        market_url = config["buses"]["market-redis"]["url"]
        self.r: Redis = Redis.from_url(market_url, decode_responses=True)

        index_str = config.get("MASSIVE_SPOT_SYMBOLS", "SPX,NDX,VIX")
        self.index_symbols = [s.strip() for s in index_str.split(",") if s.strip()]

        stock_str = config.get("MASSIVE_STOCK_SYMBOLS", "SPY,QQQ")
        self.stock_symbols = [s.strip() for s in stock_str.split(",") if s.strip()]

        all_symbols = self.index_symbols + self.stock_symbols
        self.logger.info(
            f"SpotWorker running for symbols {all_symbols} (interval={self.interval_sec}s)",
            emoji="🌐"
        )

        self.indices_needing_prefix = {"SPX", "NDX", "VIX"}
        self.last_values: Dict[str, float] = {}
        self.last_payloads: Dict[str, Dict] = {}

        self.analytics_key = "massive:spot:analytics"

        # ====================================================
        # Capture wiring (matches ws / chain)
        # ====================================================
        self.capture_enabled = (
            str(config.get("MASSIVE_WS_CAPTURE", "false")).lower() == "true"
        )

        if self.debug:
            self.logger.info(
                f"[SPOT CAPTURE DEBUG] capture_enabled={self.capture_enabled}",
                emoji="🧪",
            )

        self.spot_capture: Optional[SpotSnapshotCapture] = None

        if self.capture_enabled:
            capture_dir = config.get("MASSIVE_WS_CAPTURE_SPOT_DIR")

            if self.debug:
                self.logger.info(
                    f"[SPOT CAPTURE DEBUG] capture_dir={capture_dir}",
                    emoji="🧪",
                )

            if not capture_dir:
                self.logger.error(
                    "[SPOT CAPTURE] MASSIVE_WS_CAPTURE_SPOT_DIR missing; "
                    "capture disabled",
                    emoji="❌",
                )
            else:
                self.spot_capture = SpotSnapshotCapture(
                    capture_dir=capture_dir,
                    logger=self.logger,
                    debug=self.debug,
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

    async def _publish_unified_stream(self, payload: Dict) -> None:
        await self.r.xadd("massive:spot", {"event": json.dumps(payload)}, maxlen=10000)

    # ========================================================
    # Fetch + process
    # ========================================================

    async def _fetch_index_spot(self, sym: str) -> Optional[float]:
        api_sym = self._api_symbol(sym)
        try:
            return self.index_client.get_spot(api_sym)
        except Exception as e:
            self.logger.error(
                f"index spot fetch failed for {sym} ({api_sym}): {e}",
                emoji="💥",
            )
            return None

    async def _fetch_stock_spot(self, sym: str) -> Optional[Dict]:
        try:
            snapshot = self.general_client.get_snapshot_ticker("stocks", sym)
            day = snapshot.day
            minute = snapshot.min

            if not day or not minute or not day.volume or day.volume <= 0:
                return None

            payload = {
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

            self.logger.info(
                f"stock spot fetched {sym} close={day.close} volume={day.volume}",
                emoji="✅"
            )

            return payload

        except Exception as e:
            self.logger.error(
                f"stock spot fetch failed for {sym}: {e}",
                emoji="💥",
            )
            return None

    async def _process_spot_update(self, payload: Dict, now_epoch: float) -> None:
        sym = payload["symbol"]

        if self.last_payloads.get(sym) == payload:
            return

        self.last_payloads[sym] = payload
        self.last_values[sym] = payload["value"]

        snap = json.dumps(payload)

        await self.r.set(self._latest_key(sym), snap)
        await self.r.zadd(self._trail_key(sym), {snap: now_epoch})
        await self.r.zremrangebyscore(
            self._trail_key(sym), 0, now_epoch - self.trail_window_sec
        )
        await self.r.expire(self._trail_key(sym), self.trail_ttl_sec)

        await self._publish_unified_stream(payload)

        if self.spot_capture:
            self.spot_capture.write(payload)

        self.logger.debug(
            f"spot updated {sym}={payload['value']} "
            f"(volume={payload.get('volume', 'N/A')})",
            emoji="📡",
        )

    # ========================================================
    # Loop
    # ========================================================

    async def _tick_once(self) -> None:
        now_epoch = time.time()

        for sym in self.index_symbols:
            spot_val = await self._fetch_index_spot(sym)
            if spot_val is not None:
                payload = {
                    "symbol": sym,
                    "value": spot_val,
                    "ts": self._now_iso(),
                    "source": "massive/spot",
                    "timeframe": "REAL-TIME",
                }
                await self._process_spot_update(payload, now_epoch)

        for sym in self.stock_symbols:
            stock_payload = await self._fetch_stock_spot(sym)
            if stock_payload:
                await self._process_spot_update(stock_payload, now_epoch)

    async def run(self, stop_event: asyncio.Event) -> None:
        try:
            while not stop_event.is_set():
                await self._tick_once()
                await asyncio.sleep(self.interval_sec)
        finally:
            await self.r.close()
            self.logger.info("SpotWorker stopped", emoji="🛑")