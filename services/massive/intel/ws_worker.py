#!/usr/bin/env python3
"""
ws_worker.py — Massive options WebSocket ingestor

Responsibility:
  - Maintain a live WebSocket connection to the provider
  - Subscribe to option contracts for a given underlying (SPX, NDX, etc.)
  - Forward raw diff events into Market-Redis as a stream

It does *not* try to update chain snapshots or models directly.
Those are left to a downstream ModelMaker service.

Environment (all optional):

  MASSIVE_WS_ENABLED              = "true" | "false" (default: false)
  MASSIVE_WS_URL                  = WebSocket endpoint (e.g. wss://...)
  MASSIVE_WS_RECONNECT_DELAY_SEC  = seconds to wait before reconnect (default: 5)
  MASSIVE_WS_SUBSCRIBE_TEMPLATE   = JSON template for subscribe message
  MASSIVE_SYMBOL                  = underlying API symbol (e.g. I:SPX)
  MASSIVE_API_KEY                 = provider API key
  MARKET_REDIS_URL                = market bus (default: redis://127.0.0.1:6380)

Output:

  Stream key: massive:ws:raw:{UNDERLYING}
    XADD massive:ws:raw:SPX * symbol=SPX payload=<raw_json>

Later, a ModelMaker service can consume this stream and update models.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict

from redis.asyncio import Redis as AsyncRedis

# Try to import websockets; if missing, we'll log and no-op
try:
    import websockets  # type: ignore[import]
except ImportError:  # pragma: no cover - runtime environment concern
    websockets = None  # type: ignore[assignment]

# Robust import for logutil, regardless of package context
try:
    from .. import logutil  # type: ignore[import]
except ImportError:
    import logutil  # type: ignore[no-redef]


class WsWorker:
    """
    Long-running WebSocket worker.

    - If MASSIVE_WS_ENABLED != "true", it logs and returns immediately.
    - On connect, sends a subscription message (configurable template).
    - For each message, pushes a raw record into Market-Redis stream.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.service_name = config.get("service_name", "massive")

        # Enable/disable switch
        self.enabled = os.getenv("MASSIVE_WS_ENABLED", "false").lower() == "true"

        # API symbol / underlying
        api_symbol = os.getenv("MASSIVE_SYMBOL", "I:SPX").strip()
        if api_symbol.startswith("I:"):
            underlying = api_symbol[2:]
        else:
            underlying = api_symbol

        self.api_symbol = api_symbol
        self.underlying = underlying

        # Provider details
        self.api_key = os.getenv("MASSIVE_API_KEY", "").strip()

        # WebSocket endpoint & reconnect
        self.ws_url = os.getenv("MASSIVE_WS_URL", "wss://example.massive.com/options")
        self.reconnect_delay = float(
            os.getenv("MASSIVE_WS_RECONNECT_DELAY_SEC", "5.0")
        )

        # Market-Redis stream for raw diffs
        market_url = os.getenv("MARKET_REDIS_URL", "redis://127.0.0.1:6380")
        self.redis: AsyncRedis = AsyncRedis.from_url(  # type: ignore[assignment]
            market_url,
            decode_responses=True,
        )
        self.stream_key = f"massive:ws:raw:{self.underlying}"

        # Optional subscribe template override
        # If present, should be a JSON string with placeholders {api_symbol}, {underlying}, {api_key}
        self.subscribe_template = os.getenv("MASSIVE_WS_SUBSCRIBE_TEMPLATE", "").strip()

        # Debug switch piggybacks existing env
        self.debug = os.getenv("DEBUG_MASSIVE", "false").lower() == "true"

        logutil.log(
            self.service_name,
            "INFO",
            "🔧",
            f"WsWorker init: enabled={self.enabled}, api_symbol={self.api_symbol}, "
            f"U={self.underlying}, ws_url={self.ws_url}, reconnect={self.reconnect_delay}s",
        )

    def _build_subscribe_payload(self) -> str:
        """
        Build the JSON subscription payload to send on connect.

        There are two modes:

        1) Explicit template (MASSIVE_WS_SUBSCRIBE_TEMPLATE):
           e.g. '{"action": "subscribe", "symbol": "{api_symbol}", "api_key": "{api_key}"}'

        2) Fallback generic pattern:
           {
             "action": "subscribe",
             "symbols": ["I:SPX"],
             "api_key": "..."
           }

        The exact schema depends on the provider; this is intentionally simple
        and can be customized by setting MASSIVE_WS_SUBSCRIBE_TEMPLATE.
        """
        if self.subscribe_template:
            try:
                rendered = self.subscribe_template.format(
                    api_symbol=self.api_symbol,
                    underlying=self.underlying,
                    api_key=self.api_key,
                )
                # Validate it's valid JSON
                json.loads(rendered)
                return rendered
            except Exception as e:
                logutil.log(
                    self.service_name,
                    "WARN",
                    "⚠️",
                    f"Invalid MASSIVE_WS_SUBSCRIBE_TEMPLATE: {e}; falling back to default",
                )

        payload = {
            "action": "subscribe",
            "symbols": [self.api_symbol],
        }
        # Only include api_key if we actually have one
        if self.api_key:
            payload["api_key"] = self.api_key

        return json.dumps(payload)

    async def _handle_message(self, raw: str) -> None:
        """
        Given a single WebSocket message (raw string), push it into
        Market-Redis stream for downstream consumers.
        """
        if not raw:
            return

        # Optional: small debug log
        if self.debug:
            logutil.log(
                self.service_name,
                "DEBUG",
                "📨",
                f"WsWorker received message (len={len(raw)})",
            )

        # We don't interpret the payload here; just envelope it.
        try:
            await self.redis.xadd(
                self.stream_key,
                fields={
                    "symbol": self.underlying,
                    "payload": raw,
                },
            )
        except Exception as e:
            logutil.log(
                self.service_name,
                "ERROR",
                "💥",
                f"WsWorker failed to XADD to {self.stream_key}: {e}",
            )

    async def _run_loop(self, stop_event: asyncio.Event) -> None:
        """
        Core reconnect loop:

          while not stop_event:
            connect
            subscribe
            for msg in ws:
              handle
            on error → log and sleep(reconnect_delay)
        """
        if not self.enabled:
            logutil.log(
                self.service_name,
                "INFO",
                "⏸️",
                "WsWorker disabled (MASSIVE_WS_ENABLED != 'true'); exiting",
            )
            return

        if websockets is None:
            logutil.log(
                self.service_name,
                "ERROR",
                "💥",
                "websockets library not installed; run `pip install websockets`",
            )
            return

        subscribe_payload = self._build_subscribe_payload()

        while not stop_event.is_set():
            try:
                logutil.log(
                    self.service_name,
                    "INFO",
                    "🌐",
                    f"WsWorker connecting to {self.ws_url}",
                )

                async with websockets.connect(self.ws_url) as ws:  # type: ignore[attr-defined]
                    # Send subscription message
                    await ws.send(subscribe_payload)
                    logutil.log(
                        self.service_name,
                        "INFO",
                        "📡",
                        f"WsWorker subscribed for {self.api_symbol}",
                    )

                    # Main receive loop
                    async for message in ws:
                        if stop_event.is_set():
                            break
                        await self._handle_message(message)

            except asyncio.CancelledError:
                # Normal shutdown path
                raise
            except Exception as e:
                logutil.log(
                    self.service_name,
                    "ERROR",
                    "💥",
                    f"WsWorker connection error: {e}; retrying in {self.reconnect_delay}s",
                )
                await asyncio.sleep(self.reconnect_delay)

        logutil.log(
            self.service_name,
            "INFO",
            "🛑",
            "WsWorker stopping (stop_event set)",
        )

    async def run(self, stop_event: asyncio.Event) -> None:
        """
        Public entry for orchestrator.

        Mirrors the pattern used by SpotWorker / ChainWorker:
          - log start
          - call internal loop
          - log stop
        """
        logutil.log(
            self.service_name,
            "INFO",
            "🚀",
            f"WsWorker starting for {self.api_symbol} (enabled={self.enabled})",
        )
        try:
            await self._run_loop(stop_event)
        finally:
            logutil.log(
                self.service_name,
                "INFO",
                "🛑",
                "WsWorker stopped",
            )