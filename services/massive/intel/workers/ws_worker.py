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
# WS Worker — Snapshot-Driven Subscription from Redis List
# ============================================================

class WsWorker:
    SUBSCRIPTION_SET_KEY = "massive:ws:subscription_list"
    SUBSCRIPTION_UPDATE_CHANNEL = "massive:ws:subscription_updated"

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
        await pubsub.subscribe(self.SUBSCRIPTION_UPDATE_CHANNEL)

        # Force initial build with retry
        await self._rebuild_subscriptions_with_retry(stop_event)

        try:
            async for msg in pubsub.listen():
                if stop_event.is_set():
                    break

                if msg["type"] != "message":
                    continue

                await self._rebuild_subscriptions()

        finally:
            if self.ws_task:
                self.ws_task.cancel()

            await pubsub.unsubscribe(self.SUBSCRIPTION_UPDATE_CHANNEL)

        self.logger.info("[WS STOP] stopped", emoji="🛑")

    # ------------------------------------------------------------
    # SUBSCRIPTION REBUILD WITH RETRY ON EMPTY
    # ------------------------------------------------------------

    async def _rebuild_subscriptions_with_retry(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            new_subs = await self._get_subscription_list()

            if new_subs:
                await self._rebuild_subscriptions(new_subs)
                return

            self.logger.error(
                "[WS] No subscriptions found — retrying in 5s",
                emoji="💥"
            )
            await asyncio.sleep(5.0)

    async def _rebuild_subscriptions(self, new_subs: Set[str] = None) -> None:
        if new_subs is None:
            new_subs = await self._get_subscription_list()

        if not new_subs:
            self.logger.error("[WS] Empty subscription list after retry — continuing to wait", emoji="💥")
            return

        if new_subs == self.current_subscriptions:
            self.logger.debug("[WS] subscription set unchanged")
            return

        added = new_subs - self.current_subscriptions
        removed = self.current_subscriptions - new_subs

        self.logger.info(
            f"[WS] Rebuilding subscriptions: added {len(added)}, removed {len(removed)}, total {len(new_subs)}",
            emoji="🔁",
        )

        self.current_subscriptions = new_subs.copy()

        # Update analytics
        r = self.redis
        await r.hset(self.analytics_key, mapping={
            "subscriptions_current": len(new_subs),
            "subscriptions_added_last": len(added),
            "subscriptions_removed_last": len(removed),
            "last_subscription_update_ts": time.time()
        })

        if self.ws_task:
            self.ws_task.cancel()

        self.ws_task = asyncio.create_task(
            self._connect_and_stream(sorted(new_subs))
        )

    # ------------------------------------------------------------
    # LOAD SUBSCRIPTION LIST FROM REDIS
    # ------------------------------------------------------------

    async def _get_subscription_list(self) -> Set[str]:
        """
        Fetch current subscription list from Redis set.
        Returns set of "T.{ticker}" strings.
        """
        tickers = await self.redis.smembers(self.SUBSCRIPTION_SET_KEY)
        return set(tickers) if tickers else set()

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

                    if subscriptions:
                        await ws.send(json.dumps({
                            "action": "subscribe",
                            "params": ",".join(subscriptions),
                        }))
                        self.logger.info(f"[WS] Subscribed to {len(subscriptions)} tickers", emoji="📡")
                    else:
                        self.logger.error("[WS] No tickers to subscribe — should not happen", emoji="💥")

                    async for msg in ws:
                        ts = time.time()

                        pipe = self.redis.pipeline(transaction=False)
                        pipe.hincrby(self.analytics_key, "frames", 1)
                        pipe.hincrby(self.analytics_key, "bytes", len(msg))
                        pipe.hset(self.analytics_key, "last_ts", ts)
                        pipe.hset(self.analytics_key, "last_tick_ts", ts)
                        pipe.hset(self.analytics_key, "last_tick_ts_human", datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))
                        pipe.hincrby(self.analytics_key, "messages_processed", 1)

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