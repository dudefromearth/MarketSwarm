#!/usr/bin/env python3
"""
Volume Profile Worker - Real-time Updates

Subscribes to SPY trades via WebSocket.
Updates volume profile every second.
Scales SPY prices to SPX ($0.01 SPY → $0.10 SPX).
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Dict, Any

import websockets
from websockets.exceptions import ConnectionClosedError
from redis.asyncio import Redis


class VolumeProfileWorker:
    """
    Real-time volume profile updater.

    Subscribes to SPY trades and accumulates volume at each price level.
    Flushes to Redis every second.
    """

    REDIS_KEY = "massive:volume_profile:spx"
    ANALYTICS_KEY = "massive:volume_profile:analytics"
    WS_URL = "wss://socket.polygon.io/stocks"

    def __init__(self, config: Dict[str, Any], logger):
        self.config = config
        self.logger = logger
        self.api_key = config.get("MASSIVE_API_KEY", "")

        self.redis_url = config["buses"]["market-redis"]["url"]
        self._redis: Redis | None = None

        # Accumulator: spy_cents -> volume (flushed every second)
        self.pending_volume: Dict[int, int] = {}
        self.last_flush = time.time()
        self.flush_interval = 1.0  # seconds

        # Stats
        self.trades_processed = 0
        self.volume_added = 0

        self.logger.info("[VP WORKER INIT] SPY → SPX volume profile", emoji="📊")

    async def _redis_conn(self) -> Redis:
        if not self._redis:
            self._redis = Redis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    def spy_to_spx_bucket(self, spy_price: float) -> int:
        """
        Convert SPY price to SPX bucket (in cents).
        SPY $697.50 → SPX bucket 697500 (represents $6975.00)
        Buckets are $0.10 SPX increments (10 cents).
        """
        spy_cents = int(round(spy_price * 100))
        spx_cents = spy_cents * 10
        # Round to nearest 10 cents
        return (spx_cents // 10) * 10

    def accumulate_trade(self, price: float, size: int):
        """Add trade volume to pending accumulator."""
        bucket = self.spy_to_spx_bucket(price)
        if bucket not in self.pending_volume:
            self.pending_volume[bucket] = 0
        self.pending_volume[bucket] += size
        self.trades_processed += 1
        self.volume_added += size

    async def flush_to_redis(self):
        """Flush accumulated volume to Redis."""
        if not self.pending_volume:
            return

        r = await self._redis_conn()
        pipe = r.pipeline(transaction=False)

        for bucket, volume in self.pending_volume.items():
            pipe.hincrby(self.REDIS_KEY, str(bucket), volume)

        # Update analytics
        pipe.hset(self.ANALYTICS_KEY, mapping={
            "last_flush": time.time(),
            "trades_processed": self.trades_processed,
            "volume_added": self.volume_added,
            "pending_buckets": len(self.pending_volume),
        })

        await pipe.execute()

        self.logger.debug(
            f"[VP] Flushed {len(self.pending_volume)} buckets, {sum(self.pending_volume.values()):,} volume",
            emoji="💾"
        )

        self.pending_volume.clear()
        self.last_flush = time.time()

    async def process_message(self, msg: str):
        """Process WebSocket message containing trade events."""
        try:
            events = json.loads(msg)
            if not isinstance(events, list):
                events = [events]

            for event in events:
                ev_type = event.get("ev")

                # Trade event
                if ev_type == "T" and event.get("sym") == "SPY":
                    price = event.get("p")
                    size = event.get("s", 0)
                    if price and size > 0:
                        self.accumulate_trade(price, size)

            # Check if we should flush
            if time.time() - self.last_flush >= self.flush_interval:
                await self.flush_to_redis()

        except json.JSONDecodeError:
            pass

    async def _connect_and_stream(self):
        """Connect to Polygon WebSocket and stream SPY trades."""
        while True:
            try:
                async with websockets.connect(
                    self.WS_URL,
                    open_timeout=30,
                    ping_interval=20,
                    ping_timeout=60,
                ) as ws:
                    self.logger.info("[VP WS] Connected", emoji="✅")

                    # Authenticate
                    await ws.send(json.dumps({
                        "action": "auth",
                        "params": self.api_key,
                    }))

                    # Subscribe to SPY trades
                    await ws.send(json.dumps({
                        "action": "subscribe",
                        "params": "T.SPY",
                    }))
                    self.logger.info("[VP WS] Subscribed to T.SPY", emoji="📡")

                    # Process messages
                    async for msg in ws:
                        await self.process_message(msg)

            except asyncio.CancelledError:
                return

            except (ConnectionClosedError, TimeoutError) as e:
                self.logger.warning(f"[VP WS] Connection error: {e}, reconnecting...", emoji="🔁")
                await asyncio.sleep(5)

            except Exception as e:
                self.logger.error(f"[VP WS] Error: {e}", emoji="💥")
                await asyncio.sleep(5)

    async def run(self, stop_event: asyncio.Event):
        """Main entry point."""
        self.logger.info("[VP WORKER START] running", emoji="📊")

        try:
            # Run WebSocket connection
            ws_task = asyncio.create_task(self._connect_and_stream())

            # Wait for stop signal
            await stop_event.wait()

            ws_task.cancel()
            try:
                await ws_task
            except asyncio.CancelledError:
                pass

            # Final flush
            await self.flush_to_redis()

        except asyncio.CancelledError:
            self.logger.info("[VP WORKER] cancelled", emoji="🛑")

        finally:
            self.logger.info("[VP WORKER STOP] halted", emoji="🛑")
