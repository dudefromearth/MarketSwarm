#!/usr/bin/env python3
"""
Stock WebSocket Worker - Real-time Spot Prices

Subscribes to per-second aggregates via Polygon WebSocket for stocks and ETFs.
Writes to the same Redis key pattern as SpotWorker so SSE picks up automatically.

Futures support is built but disabled by default (Polygon futures WS is in beta).
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, List

import websockets
from websockets.exceptions import ConnectionClosedError
from redis.asyncio import Redis


class StockWsWorker:
    """
    Real-time spot price updater for stocks and ETFs via Polygon WebSocket.

    Subscribes to per-second aggregates (A.*) for configured symbols.
    Writes to massive:model:spot:{SYM} (same format as SpotWorker).
    """

    FUTURES_WS_URL = "wss://socket.polygon.io/futures"

    def __init__(self, config: Dict[str, Any], logger):
        self.config = config
        self.logger = logger
        self.api_key = config.get("MASSIVE_API_KEY", "")

        self.redis_url = config["buses"]["market-redis"]["url"]
        self._redis: Redis | None = None

        # Stock/ETF symbols from config
        raw_symbols = config.get("MASSIVE_STOCK_WS_SYMBOLS", "")
        self.stock_symbols: List[str] = [
            s.strip() for s in raw_symbols.split(",") if s.strip()
        ]

        # Futures symbols (disabled by default)
        raw_futures = config.get("MASSIVE_FUTURES_WS_SYMBOLS", "")
        self.futures_symbols: List[str] = [
            s.strip() for s in raw_futures.split(",") if s.strip()
        ]
        # Config flag — string "true"/"false" or bool
        futures_flag = config.get("MASSIVE_FUTURES_WS_ENABLED", False)
        if isinstance(futures_flag, str):
            self.futures_enabled = futures_flag.lower() == "true"
        else:
            self.futures_enabled = bool(futures_flag)

        # Trail write settings (match SpotWorker)
        self.trail_window_sec = int(config.get("MASSIVE_SPOT_TRAIL_WINDOW_SEC", 604800))
        self.trail_ttl_sec = int(config.get("MASSIVE_SPOT_TRAIL_TTL_SEC", 691200))
        self.redis_timeout = float(config.get("MASSIVE_REDIS_OP_TIMEOUT_SEC", "1.0"))

        # Dedup: skip writes when value unchanged
        self._last_values: Dict[str, float] = {}

        self.logger.info(
            f"[STOCK WS INIT] symbols={self.stock_symbols}, "
            f"futures={'enabled' if self.futures_enabled else 'disabled (beta)'}",
            emoji="📡",
        )

    async def _redis_conn(self) -> Redis:
        if not self._redis:
            self._redis = Redis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    def _latest_key(self, sym: str) -> str:
        return f"massive:model:spot:{sym}"

    def _trail_key(self, sym: str) -> str:
        return f"massive:model:spot:{sym}:trail"

    async def _write_spot(self, payload: Dict[str, Any]) -> None:
        """Write spot update to Redis (latest key + trail ZSET)."""
        sym = payload["symbol"]
        value = payload.get("value")

        # Dedup: skip if price unchanged
        if value is not None and self._last_values.get(sym) == value:
            return
        if value is not None:
            self._last_values[sym] = value

        r = await self._redis_conn()
        now_epoch = time.time()
        snap = json.dumps(payload)

        try:
            await asyncio.wait_for(
                r.set(self._latest_key(sym), snap),
                timeout=self.redis_timeout,
            )
            await asyncio.wait_for(
                r.zadd(self._trail_key(sym), {snap: now_epoch}),
                timeout=self.redis_timeout,
            )
            await asyncio.wait_for(
                r.zremrangebyscore(
                    self._trail_key(sym), 0, now_epoch - self.trail_window_sec
                ),
                timeout=self.redis_timeout,
            )
            await asyncio.wait_for(
                r.expire(self._trail_key(sym), self.trail_ttl_sec),
                timeout=self.redis_timeout,
            )
        except asyncio.TimeoutError:
            self.logger.warning(f"[STOCK WS] Redis timeout writing {sym}", emoji="⏱")
        except Exception as e:
            self.logger.error(f"[STOCK WS] Redis error writing {sym}: {e}", emoji="💥")

    def _parse_stock_aggregate(self, event: Dict[str, Any]) -> Dict[str, Any] | None:
        """Parse a Polygon stocks per-second aggregate message into spot payload."""
        sym = event.get("sym")
        close = event.get("c")
        if not sym or close is None:
            return None

        ts_ms = event.get("s") or event.get("e")
        ts_iso = (
            datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat(timespec="seconds")
            if ts_ms
            else datetime.now(timezone.utc).isoformat(timespec="seconds")
        )

        return {
            "symbol": sym,
            "value": close,
            "open": event.get("o"),
            "high": event.get("h"),
            "low": event.get("l"),
            "close": close,
            "volume": event.get("v"),
            "ts": ts_iso,
            "source": "massive/ws",
            "instrument_type": "stock",
            "timeframe": "REAL-TIME",
        }

    def _parse_futures_aggregate(self, event: Dict[str, Any]) -> Dict[str, Any] | None:
        """Parse a Polygon futures per-second aggregate message into spot payload."""
        sym = event.get("sym")
        close = event.get("c")
        if not sym or close is None:
            return None

        ts_ms = event.get("s") or event.get("e")
        ts_iso = (
            datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat(timespec="seconds")
            if ts_ms
            else datetime.now(timezone.utc).isoformat(timespec="seconds")
        )

        return {
            "symbol": sym,
            "value": close,
            "open": event.get("o"),
            "high": event.get("h"),
            "low": event.get("l"),
            "close": close,
            "volume": event.get("v"),
            "dollar_volume": event.get("dv"),
            "ts": ts_iso,
            "source": "massive/ws",
            "instrument_type": "future",
            "timeframe": "REAL-TIME",
        }

    async def _stream_stocks(self, stop_event: asyncio.Event) -> None:
        """Connect to Polygon stocks WebSocket and stream per-second aggregates."""
        if not self.stock_symbols:
            self.logger.info("[STOCK WS] No stock symbols configured, skipping", emoji="⏭")
            return

        ws_url = "wss://socket.polygon.io/stocks"
        subscription = ",".join(f"A.{s}" for s in self.stock_symbols)
        backoff = 5

        while not stop_event.is_set():
            try:
                async with websockets.connect(
                    ws_url,
                    open_timeout=30,
                    ping_interval=20,
                    ping_timeout=60,
                ) as ws:
                    self.logger.info("[STOCK WS] Connected to stocks", emoji="✅")
                    backoff = 5

                    await ws.send(json.dumps({
                        "action": "auth",
                        "params": self.api_key,
                    }))

                    await ws.send(json.dumps({
                        "action": "subscribe",
                        "params": subscription,
                    }))
                    self.logger.info(
                        f"[STOCK WS] Subscribed to {subscription}",
                        emoji="📡",
                    )

                    async for msg in ws:
                        if stop_event.is_set():
                            break
                        try:
                            events = json.loads(msg)
                            if not isinstance(events, list):
                                events = [events]

                            for event in events:
                                if event.get("ev") == "A":
                                    payload = self._parse_stock_aggregate(event)
                                    if payload and payload["symbol"] in self.stock_symbols:
                                        await self._write_spot(payload)
                        except json.JSONDecodeError:
                            pass

            except asyncio.CancelledError:
                return

            except (ConnectionClosedError, TimeoutError) as e:
                self.logger.warning(
                    f"[STOCK WS] Stocks connection error: {e}, reconnecting in {backoff}s...",
                    emoji="🔁",
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

            except Exception as e:
                self.logger.error(f"[STOCK WS] Stocks error: {e}", emoji="💥")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _stream_futures(self, stop_event: asyncio.Event) -> None:
        """Connect to Polygon futures WebSocket and stream per-second aggregates."""
        if not self.futures_symbols:
            self.logger.info("[STOCK WS] No futures symbols configured, skipping", emoji="⏭")
            return

        subscription = ",".join(f"A.{s}" for s in self.futures_symbols)
        backoff = 5

        while not stop_event.is_set():
            try:
                async with websockets.connect(
                    self.FUTURES_WS_URL,
                    open_timeout=30,
                    ping_interval=20,
                    ping_timeout=60,
                ) as ws:
                    self.logger.info("[STOCK WS] Connected to futures", emoji="✅")
                    backoff = 5

                    await ws.send(json.dumps({
                        "action": "auth",
                        "params": self.api_key,
                    }))

                    await ws.send(json.dumps({
                        "action": "subscribe",
                        "params": subscription,
                    }))
                    self.logger.info(
                        f"[STOCK WS] Subscribed to futures {subscription}",
                        emoji="📡",
                    )

                    async for msg in ws:
                        if stop_event.is_set():
                            break
                        try:
                            events = json.loads(msg)
                            if not isinstance(events, list):
                                events = [events]

                            for event in events:
                                if event.get("ev") == "A":
                                    payload = self._parse_futures_aggregate(event)
                                    if payload and payload["symbol"] in self.futures_symbols:
                                        await self._write_spot(payload)
                        except json.JSONDecodeError:
                            pass

            except asyncio.CancelledError:
                return

            except (ConnectionClosedError, TimeoutError) as e:
                self.logger.warning(
                    f"[STOCK WS] Futures connection error: {e}, reconnecting in {backoff}s...",
                    emoji="🔁",
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

            except Exception as e:
                self.logger.error(f"[STOCK WS] Futures error: {e}", emoji="💥")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def run(self, stop_event: asyncio.Event) -> None:
        """Main entry point — manages stock and futures WebSocket connections."""
        self.logger.info(
            f"[STOCK WS WORKER START] stocks={self.stock_symbols}, "
            f"futures={'enabled' if self.futures_enabled else 'disabled'}",
            emoji="📡",
        )

        try:
            tasks = []

            # Stocks WebSocket
            if self.stock_symbols:
                tasks.append(asyncio.create_task(
                    self._stream_stocks(stop_event), name="stock-ws-stocks"
                ))

            # Futures WebSocket (gated by config flag)
            if self.futures_enabled:
                tasks.append(asyncio.create_task(
                    self._stream_futures(stop_event), name="stock-ws-futures"
                ))
            else:
                self.logger.info(
                    "[STOCK WS] Futures WS disabled (beta) — set MASSIVE_FUTURES_WS_ENABLED=true to enable",
                    emoji="⏭",
                )

            if tasks:
                await stop_event.wait()
                for t in tasks:
                    t.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
            else:
                await stop_event.wait()

        except asyncio.CancelledError:
            self.logger.info("[STOCK WS WORKER] cancelled", emoji="🛑")

        finally:
            if self._redis:
                await self._redis.close()
            self.logger.info("[STOCK WS WORKER STOP] halted", emoji="🛑")
