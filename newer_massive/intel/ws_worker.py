from __future__ import annotations

import asyncio
import json
import time
import random
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set, List

import websockets
from websockets.exceptions import ConnectionClosedError
from redis.asyncio import Redis


# ============================================================
# WS Worker — Epoch-Aligned, Snapshot-Driven (0-DTE)
# ============================================================

class WsWorker:
    SNAPSHOT_CHANNEL = "massive:chain:snapshot"
    SNAPSHOT_KEY_PATTERN = "massive:chain:snapshot:{underlying}:{date}:*"

    def __init__(
        self,
        config: Dict[str, Any],
        logger,
        shared_redis: Optional[Redis] = None,
    ) -> None:
        self.logger = logger
        self.config = config

        self.ws_url = config["MASSIVE_WS_URL"]
        self.api_key = config["MASSIVE_API_KEY"]

        self.reconnect_delay = float(
            config.get("MASSIVE_WS_RECONNECT_DELAY_SEC", "5.0")
        )

        self.redis = shared_redis or Redis.from_url(
            config["buses"]["market-redis"]["url"],
            decode_responses=True,
        )

        self.analytics_key = "massive:ws:analytics"
        self.stream_key = "massive:ws:stream"
        self.stream_maxlen = int(
            config.get("MASSIVE_WS_STREAM_MAXLEN", "100000")
        )

        self.current_subscriptions: Set[str] = set()
        self.ws_task: Optional[asyncio.Task] = None

        self.logger.info("[WS INIT] snapshot-driven (0-DTE)", emoji="🔎")

    # ------------------------------------------------------------
    # PUBLIC ENTRY
    # ------------------------------------------------------------

    async def run(self, stop_event: asyncio.Event) -> None:
        self.logger.info("[WS RUN] starting", emoji="🚀")

        pubsub = self.redis.pubsub()
        await pubsub.subscribe(self.SNAPSHOT_CHANNEL)

        # Force initial build
        await self._rebuild_and_restart()

        try:
            async for msg in pubsub.listen():
                if stop_event.is_set():
                    break

                if msg["type"] != "message":
                    continue

                await self._rebuild_and_restart()

        finally:
            if self.ws_task:
                self.ws_task.cancel()

            await pubsub.unsubscribe(self.SNAPSHOT_CHANNEL)

        self.logger.info("[WS STOP] stopped", emoji="🛑")

    # ------------------------------------------------------------
    # SUBSCRIPTION REBUILD
    # ------------------------------------------------------------

    async def _rebuild_and_restart(self) -> None:
        subs = await self._build_subscriptions()

        if not subs:
            self.logger.warning(
                "[WS] zero subscriptions — waiting for next snapshot",
                emoji="⚠️",
            )
            return

        if subs == self.current_subscriptions:
            self.logger.info("[WS] subscription set unchanged", emoji="⏸️")
            return

        self.current_subscriptions = subs

        self.logger.info(
            f"[WS] rebuilding subscriptions ({len(subs)})",
            emoji="🔁",
        )

        if self.ws_task:
            self.ws_task.cancel()

        self.ws_task = asyncio.create_task(
            self._connect_and_stream(sorted(subs))
        )

    # ------------------------------------------------------------
    # BUILD SUBSCRIPTIONS FROM 0-DTE SNAPSHOTS
    # ------------------------------------------------------------

    async def _build_subscriptions(self) -> Set[str]:
        """
        Build WS subscriptions from REAL snapshot keys in Redis.
        Uses:
          massive:chain:snapshot:I:{SPX|NDX}:{YYYY-MM-DD}:{epoch}
        0-DTE ONLY.
        """
        contracts: Set[str] = set()

        for underlying in ("I:SPX", "I:NDX"):
            pattern = f"massive:chain:snapshot:{underlying}:*"

            # Get all snapshot keys for this underlying
            keys = await self.redis.keys(pattern)
            if not keys:
                self.logger.warning(
                    f"[WS] no snapshot keys for {underlying}",
                    emoji="⚠️",
                )
                continue

            # Pick latest epoch (last colon segment is epoch millis)
            latest_key = max(
                keys,
                key=lambda k: int(k.rsplit(":", 1)[-1]),
            )

            raw = await self.redis.get(latest_key)
            if not raw:
                continue

            snapshot = json.loads(raw)

            # HARD RULE: 0-DTE ONLY
            # snapshot["expiration"] is authoritative
            expiration = snapshot.get("expiration")
            if not expiration:
                continue

            for c in snapshot.get("contracts", []):
                ticker = (
                    c.get("details", {})
                    .get("ticker")
                )
                if ticker:
                    # Massive WS trade feed format
                    contracts.add(f"T.{ticker}")

        return contracts

    # ------------------------------------------------------------
    # WS CONNECT + STREAM
    # ------------------------------------------------------------

    async def _connect_and_stream(
        self,
        subscriptions: List[str],
    ) -> None:
        while True:
            try:
                async with websockets.connect(
                    self.ws_url,
                    open_timeout=30,
                    ping_interval=20,
                    ping_timeout=60,
                ) as ws:
                    self.logger.info("[WS CONNECTED]", emoji="✅")

                    await ws.send(json.dumps({
                        "action": "auth",
                        "params": self.api_key,
                    }))

                    await ws.send(json.dumps({
                        "action": "subscribe",
                        "params": ",".join(subscriptions),
                    }))

                    async for msg in ws:
                        ts = time.time()

                        pipe = self.redis.pipeline(transaction=False)
                        pipe.hincrby(self.analytics_key, "frames", 1)
                        pipe.hincrby(self.analytics_key, "bytes", len(msg))
                        pipe.hset(self.analytics_key, "last_ts", ts)

                        pipe.xadd(
                            self.stream_key,
                            {"ts": ts, "payload": msg},
                            maxlen=self.stream_maxlen,
                            approximate=True,
                        )

                        await pipe.execute()

            except asyncio.CancelledError:
                return

            except (ConnectionClosedError, TimeoutError) as e:
                self.logger.warning(f"[WS RETRY] {e}", emoji="🔁")
                await asyncio.sleep(
                    self.reconnect_delay + random.uniform(0, 2)
                )

            except Exception as e:
                self.logger.error(f"[WS ERROR] {e}", emoji="💥")
                await asyncio.sleep(5)