# services/massive/intel/workers/ws_consumer.py

from __future__ import annotations

import asyncio
import json
import time
from typing import Dict, Any, Optional

from redis.asyncio import Redis


class WsConsumer:
    """
    WsConsumer — Reads WS stream and drives the hydrator at target frequency.

    - Consumes from massive:ws:stream
    - Batches messages to WsHydrator
    - Triggers snapshot emission at configurable Hz (2-5 Hz default)
    - Direct injection to Builder for minimal latency
    """

    STREAM_KEY = "massive:ws:stream"
    ANALYTICS_KEY = "massive:ws:consumer:analytics"

    def __init__(self, config: Dict[str, Any], logger):
        self.config = config
        self.logger = logger

        # Target frequency: 2-5 Hz = 200-500ms intervals
        self.snapshot_interval_ms = int(config.get("MASSIVE_WS_SNAPSHOT_INTERVAL_MS", 250))
        self.batch_size = int(config.get("MASSIVE_WS_BATCH_SIZE", 100))

        self.market_redis_url = config["buses"]["market-redis"]["url"]
        self._redis: Redis | None = None

        # Injected dependencies
        self._hydrator = None
        self._builder = None

        # Stream position
        self._last_id = "0-0"

        self.logger.info(
            f"[WS CONSUMER INIT] interval={self.snapshot_interval_ms}ms batch={self.batch_size}",
            emoji="📥",
        )

    async def _redis_conn(self) -> Redis:
        if not self._redis:
            self._redis = Redis.from_url(self.market_redis_url, decode_responses=True)
        return self._redis

    def set_hydrator(self, hydrator) -> None:
        self._hydrator = hydrator
        self.logger.info("[WS CONSUMER] Hydrator injected", emoji="🔗")

    def set_builder(self, builder) -> None:
        self._builder = builder
        self.logger.info("[WS CONSUMER] Builder injected", emoji="🔗")

    async def _consume_stream(self) -> int:
        """
        Consume available messages from stream.
        Returns count of messages processed.
        """
        r = await self._redis_conn()

        # Read batch from stream
        results = await r.xread(
            {self.STREAM_KEY: self._last_id},
            count=self.batch_size,
            block=50,  # Short block to stay responsive
        )

        if not results:
            return 0

        messages = []
        for stream_name, entries in results:
            for entry_id, fields in entries:
                self._last_id = entry_id
                messages.append(fields)

        if messages and self._hydrator:
            await self._hydrator.hydrate_batch(messages)

        return len(messages)

    async def _emit_snapshot(self) -> None:
        """
        Emit current state to Builder for tile calculation.
        """
        if not self._hydrator or not self._builder:
            return

        # Get merged snapshot from hydrator (chain baseline + WS updates)
        snapshots = await self._hydrator.get_merged_snapshots()

        if snapshots:
            self.logger.debug(
                f"[WS EMIT] symbols={list(snapshots.keys())} contracts={sum(len(v) for v in snapshots.values())}",
                emoji="📤",
            )
            await self._builder.receive_snapshot(snapshots)

    async def run(self, stop_event: asyncio.Event) -> None:
        self.logger.info("[WS CONSUMER START] running", emoji="📥")

        r = await self._redis_conn()
        last_snapshot_time = time.monotonic()
        total_consumed = 0

        try:
            while not stop_event.is_set():
                # Consume available messages
                count = await self._consume_stream()
                total_consumed += count

                # Check if it's time to emit snapshot
                now = time.monotonic()
                elapsed_ms = (now - last_snapshot_time) * 1000

                if elapsed_ms >= self.snapshot_interval_ms:
                    await self._emit_snapshot()
                    last_snapshot_time = now

                    # Analytics for performance instrumentation
                    await r.hset(self.ANALYTICS_KEY, mapping={
                        "last_snapshot_ts": time.time(),
                        "messages_consumed": total_consumed,
                        "snapshot_interval_ms": self.snapshot_interval_ms,
                        "actual_interval_ms": int(elapsed_ms),
                        "emit_count": await r.hincrby(self.ANALYTICS_KEY, "emit_count", 0) + 1,
                    })
                    await r.hincrby(self.ANALYTICS_KEY, "emit_count", 1)

        except asyncio.CancelledError:
            self.logger.info("[WS CONSUMER] cancelled", emoji="🛑")

        finally:
            self.logger.info("[WS CONSUMER STOP] halted", emoji="🛑")
