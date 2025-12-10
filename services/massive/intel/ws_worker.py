# services/massive/intel/ws_worker.py

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import websockets
from redis.asyncio import Redis

# Robust import for logutil, regardless of how module is executed
try:
    # Preferred: package-relative when intel is a subpackage of massive
    from .. import logutil  # type: ignore[import]
except ImportError:
    # Fallback: direct import when massive/ is on sys.path (as main.py does)
    import logutil  # type: ignore[no-redef]


def _iso_utc_now() -> str:
    # Match previous snapshot keys: seconds, with timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class WsWorker:
    """
    WebSocket worker for subscribing to Massive options trade channels (T.O).

    Integration:

      - ChainWorker now derives WS trade channels as part of its snapshot and
        publishes a params key per expiry:

            massive:ws:params:{YYYYMMDD}

        Typically this is a comma-joined string, but older tooling may have
        written it as a Redis SET. We support both.

        The chain snapshot also embeds metadata:

            {
              ...,
              "ws_params_key": "massive:ws:params:20251209",
              "ws_channels": [...],
              "ws_channels_count": N,
              ...
            }

      - WsWorker prefers the params key, and falls back to the latest chain
        snapshot's ws_channels if the params key is missing.

      - Subscribes via WS and publishes parsed trades to Redis stream:

            massive:trades:{underlying}:{expiry_yyyymmdd}

        Each event: XADD with fields {contract, price, size, ts, side?}.

    Reconnection: Exponential backoff on disconnects.
    Resubscribe: On reconnect/poll, re-read params from Redis (handles Chain updates/expansions).
    Expand Only: New ranges add contracts; ignore trims for session coverage.
    """

    def __init__(self, config: Dict[str, Any], shared_redis: Optional[Redis] = None) -> None:
        self.config = config
        self.service_name = config.get("service_name", "massive")

        # Core symbol wiring
        self.api_symbol: str = config.get("api_symbol", os.getenv("MASSIVE_SYMBOL", "I:SPX")).strip()
        if self.api_symbol.startswith("I:"):
            self.underlying: str = self.api_symbol[2:]
            self.underlying_prefix: str = f"{self.underlying}W"  # e.g., SPXW
        else:
            self.underlying = self.api_symbol
            self.underlying_prefix = f"{self.underlying}W"

        # WS config
        self.ws_url: str = config.get("ws_url", os.getenv("MASSIVE_WS_URL", "wss://socket.massive.com/options"))
        self.api_key: str = config.get("api_key", os.getenv("MASSIVE_API_KEY", ""))
        if not self.api_key:
            raise RuntimeError("MASSIVE_API_KEY must be set for WsWorker")

        # Expiry (single, from config/env) – accepts 'YYYYMMDD' or 'YYYY-MM-DD'
        raw_expiry = config.get("ws_expiry_yyyymmdd", os.getenv("MASSIVE_WS_EXPIRY_YYYYMMDD", "")).strip()
        if not raw_expiry:
            raise RuntimeError("MASSIVE_WS_EXPIRY_YYYYMMDD must be set for WsWorker")
        self.expiry_yyyymmdd: str = raw_expiry.replace("-", "")
        # ISO form, used by CHAIN snapshots (CHAIN:SPX:EXP:YYYY-MM-DD:latest)
        self.expiry_iso: str = f"{self.expiry_yyyymmdd[0:4]}-{self.expiry_yyyymmdd[4:6]}-{self.expiry_yyyymmdd[6:8]}"

        # Redis (shared or create)
        self.market_redis_url: str = config.get("market_redis_url", os.getenv("MARKET_REDIS_URL", "redis://127.0.0.1:6380"))
        self._redis_market: Redis = shared_redis or Redis.from_url(self.market_redis_url, decode_responses=True)

        # Strike step from env/shell (for logging only – chain_worker owns the geometry)
        self.strike_step: int = int(os.getenv("MASSIVE_WS_STRIKE_STEP", "5"))

        # Reconnect / resubscribe
        self.reconnect_delay_sec: float = config.get("ws_reconnect_delay_sec", float(os.getenv("MASSIVE_WS_RECONNECT_DELAY_SEC", "5.0")))
        self.max_reconnect_delay: float = 60.0
        self.poll_interval_sec: float = 120.0  # Poll params every 2 min for updates

        # Trades stream key
        #   massive:trades:SPX:20251209
        self.trades_stream_key = f"massive:trades:{self.underlying}:{self.expiry_yyyymmdd}"

        # Params key from ChainWorker
        #   massive:ws:params:{YYYYMMDD}
        self.params_key = f"massive:ws:params:{self.expiry_yyyymmdd}"

        # Latest CHAIN snapshot pointer for this expiry:
        #   CHAIN:SPX:EXP:2025-12-09:latest -> CHAIN:SPX:EXP:2025-12-09:snap:...
        self.chain_latest_key = f"CHAIN:{self.underlying}:EXP:{self.expiry_iso}:latest"

        self.debug_enabled: bool = config.get("debug_enabled", os.getenv("DEBUG_MASSIVE", "false").lower() == "true")

        self.backoff_delay = self.reconnect_delay_sec  # Initial backoff
        self.current_params = ""  # Track current comma-joined params
        self.last_poll = 0

        logutil.log(
            self.service_name,
            "INFO",
            "🔌",
            (
                f"WsWorker init: U={self.underlying} ({self.underlying_prefix}), "
                f"exp={self.expiry_yyyymmdd}, "
                f"ws_url={self.ws_url}, "
                f"strike_step={self.strike_step}, "
                f"trades_stream={self.trades_stream_key}, "
                f"params_key={self.params_key}, "
                f"chain_latest_key={self.chain_latest_key}"
            ),
        )

    # ------------------------------------------------------------
    # Channel readers
    # ------------------------------------------------------------
    async def _read_channels_from_params_key(self) -> List[str]:
        """
        Primary path: read channels from massive:ws:params:{YYYYMMDD}.

        Supports:
          - STRING: comma-joined "T.O:...,T.O:..."
          - SET: SMEMBERS (older or alternative writers)
        """
        channels: List[str] = []

        # Try string GET first
        raw: Optional[str] = None
        try:
            raw = await self._redis_market.get(self.params_key)
        except Exception as e:
            logutil.log(
                self.service_name,
                "WARN",
                "⚠️",
                f"Error reading WS params via GET {self.params_key}: {e}",
            )

        if raw:
            channels = [ch.strip() for ch in raw.split(",") if ch.strip()]

        # Fallback to SET if no usable string
        if not channels:
            try:
                members = await self._redis_market.smembers(self.params_key)
            except Exception as e:
                logutil.log(
                    self.service_name,
                    "WARN",
                    "⚠️",
                    f"Error reading WS params via SMEMBERS {self.params_key}: {e}",
                )
                members = set()

            if members:
                channels = sorted(str(m).strip() for m in members if m)

        if channels and self.debug_enabled:
            logutil.log(
                self.service_name,
                "DEBUG",
                "📺",
                f"Params key {self.params_key} yielded {len(channels)} channels",
            )

        return channels

    async def _read_channels_from_chain_snapshot(self) -> List[str]:
        """
        Fallback: read ws_channels from the latest CHAIN snapshot:

          CHAIN:{U}:EXP:{YYYY-MM-DD}:latest -> CHAIN:{U}:EXP:{YYYY-MM-DD}:snap:{ts}

        and then:

          snapshot["ws_channels"]  (list[str])   – if present.
        """
        latest = await self._redis_market.get(self.chain_latest_key)
        if not latest:
            logutil.log(
                self.service_name,
                "WARN",
                "⚠️",
                f"No latest chain key for expiry {self.expiry_iso} ({self.chain_latest_key})",
            )
            return []

        snap_raw = await self._redis_market.get(latest)
        if not snap_raw:
            logutil.log(
                self.service_name,
                "WARN",
                "⚠️",
                f"Snapshot key missing for latest chain: {latest}",
            )
            return []

        try:
            snap = json.loads(snap_raw)
        except Exception as e:
            logutil.log(
                self.service_name,
                "ERROR",
                "💥",
                f"Invalid chain snapshot JSON at {latest}: {e}",
            )
            return []

        channels = snap.get("ws_channels") or []
        if isinstance(channels, list):
            out = [str(ch).strip() for ch in channels if ch]
            if out:
                logutil.log(
                    self.service_name,
                    "INFO",
                    "📺",
                    f"Loaded {len(out)} WS channels from chain snapshot for {self.expiry_iso}",
                )
            return out

        # If someone stored it as a comma string by mistake, handle that too
        if isinstance(channels, str):
            out = [ch.strip() for ch in channels.split(",") if ch.strip()]
            if out:
                logutil.log(
                    self.service_name,
                    "INFO",
                    "📺",
                    f"Loaded {len(out)} WS channels (string) from chain snapshot for {self.expiry_iso}",
                )
            return out

        logutil.log(
            self.service_name,
            "WARN",
            "⚠️",
            f"ws_channels missing or invalid in chain snapshot {latest}",
        )
        return []

    async def _read_channels(self) -> List[str]:
        """
        Read active WS channels for this expiry.

        Preference:
          1) massive:ws:params:{YYYYMMDD} (string or set)
          2) CHAIN latest snapshot's ws_channels (list or comma string)

        Expand-only semantics preserved using self.current_params.
        """
        # 1) Try params key
        channels = await self._read_channels_from_params_key()

        # 2) Fallback to chain snapshot if params key missing/empty
        if not channels:
            channels = await self._read_channels_from_chain_snapshot()

        if not channels:
            # Nothing new; either keep current or bail
            if self.current_params:
                existing = [ch for ch in self.current_params.split(",") if ch]
                logutil.log(
                    self.service_name,
                    "WARN",
                    "⚠️",
                    f"No new WS params; keeping current {len(existing)} channels",
                )
                return existing

            logutil.log(
                self.service_name,
                "WARN",
                "⚠️",
                f"No WS channel config found for expiry {self.expiry_iso}; skipping subscribe",
            )
            return []

        # At this point we have a fresh list
        channels = [ch for ch in channels if ch]
        new_params = ",".join(channels)
        new_set = set(channels)

        if self.current_params:
            current_list = [ch for ch in self.current_params.split(",") if ch]
            current_set = set(current_list)

            if len(new_set) > len(current_set):
                added = new_set - current_set
                self.current_params = new_params
                logutil.log(
                    self.service_name,
                    "INFO",
                    "➕",
                    f"Range expanded: +{len(added)} channels (total {len(new_set)})",
                )
            else:
                # No change or trim—keep current (expand-only semantics)
                channels = current_list
                logutil.log(
                    self.service_name,
                    "DEBUG",
                    "📊",
                    f"WS params unchanged; keeping {len(channels)} channels",
                )
        else:
            # First time
            self.current_params = new_params
            logutil.log(
                self.service_name,
                "INFO",
                "📺",
                f"Loaded initial {len(channels)} channels "
                f"for expiry {self.expiry_iso} from WS config",
            )

        if self.debug_enabled:
            logutil.log(
                self.service_name,
                "DEBUG",
                "📺",
                f"Active channels: {len(channels)}",
            )

        return channels

    # ------------------------------------------------------------
    # Trade publisher
    # ------------------------------------------------------------
    async def _publish_trade(self, msg: str) -> None:
        """
        Parse WS msg (assume array of trade events) and XADD to trades stream.
        Vendor format: [{"ev":"T","sym":"O:SPXW251208C06840000","x":302,"p":5.5,"s":1,"c":[236],"t":1765227583506,"q":1864261653}]
        Normalize: contract=sym, price=p, size=s, ts=t (ms epoch), side=U (unknown).

        Redis requirement: field values must be str/int/float/bytes.
        We sanitize everything before XADD.
        """
        try:
            data = json.loads(msg)
            if not isinstance(data, list):
                data = [data]  # Handle single object

            for event in data:
                if event.get("ev") != "T":  # Trades only
                    continue

                # Build raw event dict
                trade_event = {
                    "contract": event.get("sym", ""),
                    "price": event.get("p"),
                    "size": event.get("s"),
                    "ts": event.get("t", int(time.time() * 1000)),  # ms epoch fallback
                    "side": "U",  # Unknown
                    "exchange": event.get("x"),
                    "conditions": event.get("c"),
                    "raw": msg,  # Full WS payload for debug
                }

                # Sanitize for Redis: no lists/dicts/None
                safe_event: Dict[str, Any] = {}
                for k, v in trade_event.items():
                    if v is None:
                        continue
                    if isinstance(v, (list, dict)):
                        v = json.dumps(v)
                    safe_event[k] = v

                if not safe_event:
                    continue

                await self._redis_market.xadd(
                    self.trades_stream_key,
                    safe_event,
                    maxlen=10000,  # Trim old
                )

                if self.debug_enabled:
                    logutil.log(
                        self.service_name,
                        "DEBUG",
                        "💰",
                        f"Trade: {safe_event.get('contract')} "
                        f"@ {safe_event.get('price')} x {safe_event.get('size')}",
                    )

        except Exception as e:
            logutil.log(
                self.service_name,
                "WARN",
                "⚠️",
                f"Publish failed: {e}",
            )

    # ------------------------------------------------------------
    # WS connection loop
    # ------------------------------------------------------------
    async def _connect_and_stream(self, stop_event: asyncio.Event) -> None:
        """
        Single WS connection: read channels, auth, subscribe, stream until disconnect/stop.
        Poll for updates every poll_interval_sec.
        """
        try:
            # Read initial channels
            channels = await self._read_channels()
            if not channels:
                logutil.log(self.service_name, "WARN", "⚠️", "No channels; skipping connect")
                return

            params = ",".join(channels)

            async with websockets.connect(self.ws_url) as ws:
                # Auth
                auth = {"action": "auth", "params": self.api_key}
                await ws.send(json.dumps(auth))
                logutil.log(self.service_name, "INFO", "🔐", "Auth sent")

                # Subscribe
                sub = {"action": "subscribe", "params": params}
                await ws.send(json.dumps(sub))
                logutil.log(self.service_name, "INFO", "📺", f"Subscribed: {len(channels)} channels")

                # Stream with poll
                self.last_poll = time.time()
                async for msg in ws:
                    if stop_event.is_set():
                        break

                    # Poll for range updates
                    now = time.time()
                    if now - self.last_poll > self.poll_interval_sec:
                        new_channels = await self._read_channels()
                        if new_channels and len(new_channels) > len(channels):
                            params = ",".join(new_channels)
                            await ws.send(json.dumps({"action": "subscribe", "params": params}))
                            logutil.log(self.service_name, "INFO", "🔄", f"Resub to expanded range: {len(new_channels)} channels")
                            channels = new_channels
                        self.last_poll = now

                    await self._publish_trade(msg)

        except websockets.exceptions.ConnectionClosed:
            logutil.log(self.service_name, "WARN", "🔌", "Connection closed")
        except Exception as e:
            logutil.log(self.service_name, "ERROR", "💥", f"Stream error: {e}")

    # ------------------------------------------------------------
    # Public entrypoint
    # ------------------------------------------------------------
    async def run(self, stop_event: asyncio.Event) -> None:
        """
        Long-running WS worker with reconnection.
        """
        logutil.log(
            self.service_name,
            "INFO",
            "🚀",
            f"WsWorker starting: {self.underlying} exp={self.expiry_yyyymmdd}",
        )

        try:
            while not stop_event.is_set():
                try:
                    await self._connect_and_stream(stop_event)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logutil.log(
                        self.service_name,
                        "ERROR",
                        "💥",
                        f"Connection failed: {e}; retry in {self.backoff_delay}s",
                    )

                # Backoff wait
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=self.backoff_delay)
                except asyncio.TimeoutError:
                    pass

                # Backoff grow (1.5x, cap 60s)
                self.backoff_delay = min(self.backoff_delay * 1.5, self.max_reconnect_delay)

        except asyncio.CancelledError:
            logutil.log(self.service_name, "INFO", "🛑", "WsWorker shutdown")
        finally:
            logutil.log(self.service_name, "INFO", "🛑", "WsWorker stopped")