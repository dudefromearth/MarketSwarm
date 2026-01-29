# services/massive/intel/model_builders/model_publisher.py

import asyncio
import json
import time
from typing import Dict, Any

from redis.asyncio import Redis


class ModelPublisher:
    """
    Model Publisher Worker — Model stage.
    Receives delta patches from Builder.
    Applies deltas to current model state.
    Publishes live model to :latest key (short TTL).
    Appends deltas to replay stream (full-day TTL).

    Instrumentation:
    - Periodic throughput stats (every 30s)
    - Gap detection and alerting
    - Per-symbol and aggregate metrics
    """

    STATS_INTERVAL_SEC = 30
    GAP_ALERT_THRESHOLD_SEC = 5

    def __init__(self, config: Dict[str, Any], logger):
        self.config = config
        self.logger = logger

        self.symbols = [
            s.strip()
            for s in config.get("MASSIVE_CHAIN_SYMBOLS", "I:SPX,I:NDX").split(",")
            if s.strip()
        ]

        self.market_redis_url = config["buses"]["market-redis"]["url"]
        self._redis: Redis | None = None

        # 72 hours default for off-market stale chain support (weekends)
        self.live_ttl_sec = int(config.get("MASSIVE_MODEL_LIVE_TTL_SEC", 259200))
        self.replay_ttl_sec = int(config.get("MASSIVE_REPLAY_TTL_SEC", 86400))

        self.analytics_key = "massive:model:analytics"

        # Per-symbol current model state (tiles dict)
        self.current_models: Dict[str, Dict[str, Any]] = {sym: {} for sym in self.symbols}

        # ─────────────────────────────────────────────────────────────
        # Throughput tracking (reset each stats interval)
        # ─────────────────────────────────────────────────────────────
        self._session_start = time.time()
        self._interval_start = time.time()

        # Per-symbol interval counters
        self._interval_publishes: Dict[str, int] = {sym: 0 for sym in self.symbols}
        self._interval_tiles: Dict[str, int] = {sym: 0 for sym in self.symbols}
        self._interval_empty: Dict[str, int] = {sym: 0 for sym in self.symbols}

        # Session totals
        self._total_publishes: Dict[str, int] = {sym: 0 for sym in self.symbols}
        self._total_tiles: Dict[str, int] = {sym: 0 for sym in self.symbols}

        # Gap tracking
        self._last_publish_ts: Dict[str, float] = {sym: 0.0 for sym in self.symbols}
        self._max_gap: Dict[str, float] = {sym: 0.0 for sym in self.symbols}
        self._gap_alerts: int = 0

        # Latency tracking
        self._latencies: list[float] = []

        self.logger.info(
            f"[MODEL PUBLISHER INIT] symbols={self.symbols}, stats_interval={self.STATS_INTERVAL_SEC}s",
            emoji="📤"
        )

    async def _redis_conn(self) -> Redis:
        if not self._redis:
            self._redis = Redis.from_url(self.market_redis_url, decode_responses=True)
        return self._redis

    def _extract_dtes(self, tiles: Dict[str, Any]) -> Dict[int, int]:
        """Extract DTE → tile count from tiles dict."""
        dte_counts: Dict[int, int] = {}
        for tile in tiles.values():
            dte = tile.get("dte", 0)
            dte_counts[dte] = dte_counts.get(dte, 0) + 1
        return dte_counts

    async def receive_delta(self, symbol: str, delta_patch: Dict[str, Any]) -> None:
        """Called by Builder with {changed: {...}, removed: [...]}."""
        if symbol not in self.symbols:
            self.logger.warning(f"[MODEL] Unknown symbol delta: {symbol}", emoji="⚠️")
            return

        t_start = time.monotonic()
        ts_now = time.time()

        # ─────────────────────────────────────────────────────────────
        # Gap detection
        # ─────────────────────────────────────────────────────────────
        if self._last_publish_ts[symbol] > 0:
            gap = ts_now - self._last_publish_ts[symbol]
            if gap > self._max_gap[symbol]:
                self._max_gap[symbol] = gap
            if gap > self.GAP_ALERT_THRESHOLD_SEC:
                self._gap_alerts += 1
                self.logger.warning(
                    f"[MODEL GAP] {symbol} gap={gap:.1f}s (threshold={self.GAP_ALERT_THRESHOLD_SEC}s)",
                    emoji="⚠️"
                )
        self._last_publish_ts[symbol] = ts_now

        # Extract changed tiles and removed keys
        changed = delta_patch.get("changed", {})
        removed = delta_patch.get("removed", [])

        # Apply changed tiles to current model state
        self.current_models[symbol].update(changed)

        # Remove deleted tiles
        for key in removed:
            self.current_models[symbol].pop(key, None)

        # Compute DTE metadata for SSE Gateway
        dte_counts = self._extract_dtes(self.current_models[symbol])
        dtes_available = sorted(dte_counts.keys())

        # Sub-second timestamp for versioning
        version = int(ts_now * 1000)  # millisecond version

        # Publish live model (full current state with DTE metadata)
        live_key = f"massive:heatmap:model:{symbol}:latest"
        live_payload = json.dumps({
            "ts": ts_now,
            "symbol": symbol,
            "epoch": "current",
            "version": version,
            "dtes_available": dtes_available,
            "dte_tile_counts": dte_counts,
            "tiles": self.current_models[symbol]
        })
        r = await self._redis_conn()
        await r.set(live_key, live_payload, ex=self.live_ttl_sec)

        # Append delta to replay stream
        replay_stream = f"massive:heatmap:replay:{symbol}"
        delta_payload = json.dumps({
            "ts": ts_now,
            "version": version,
            "changed": changed,
            "removed": removed,
        })
        await r.xadd(replay_stream, {"payload": delta_payload})
        await r.expire(replay_stream, self.replay_ttl_sec)

        # Publish diff via pub/sub for real-time SSE streaming
        diff_channel = f"massive:heatmap:diff:{symbol}"
        diff_payload = json.dumps({
            "ts": ts_now,
            "version": version,
            "symbol": symbol,
            "changed": changed,
            "removed": removed,
            "dtes_available": dtes_available,
        })
        await r.publish(diff_channel, diff_payload)

        # ─────────────────────────────────────────────────────────────
        # Throughput tracking
        # ─────────────────────────────────────────────────────────────
        latency_ms = (time.monotonic() - t_start) * 1000
        self._latencies.append(latency_ms)

        self._interval_publishes[symbol] += 1
        self._interval_tiles[symbol] += len(changed)
        self._total_publishes[symbol] += 1
        self._total_tiles[symbol] += len(changed)

        if len(changed) == 0:
            self._interval_empty[symbol] += 1

        # Redis analytics (lightweight)
        await r.hincrby(self.analytics_key, "publishes", 1)
        await r.hset(self.analytics_key, "latency_last_ms", int(latency_ms))

    def _format_rate(self, count: int, elapsed: float) -> str:
        """Format count as rate per second."""
        if elapsed <= 0:
            return "0.0"
        return f"{count / elapsed:.1f}"

    async def _emit_stats(self) -> None:
        """Emit periodic throughput statistics."""
        now = time.time()
        interval_elapsed = now - self._interval_start
        session_elapsed = now - self._session_start

        # Per-symbol stats
        symbol_stats = []
        for sym in self.symbols:
            pub_count = self._interval_publishes[sym]
            tile_count = self._interval_tiles[sym]
            empty_count = self._interval_empty[sym]
            pub_rate = self._format_rate(pub_count, interval_elapsed)
            tile_rate = self._format_rate(tile_count, interval_elapsed)
            total_tiles = len(self.current_models.get(sym, {}))
            max_gap = self._max_gap[sym]

            symbol_stats.append(
                f"{sym.replace('I:', '')}[pub={pub_rate}/s tiles={tile_rate}/s "
                f"empty={empty_count} model={total_tiles} max_gap={max_gap:.1f}s]"
            )

        # Aggregate stats
        total_pub = sum(self._interval_publishes.values())
        total_tiles = sum(self._interval_tiles.values())
        session_pub = sum(self._total_publishes.values())
        session_tiles = sum(self._total_tiles.values())

        # Latency stats
        avg_latency = sum(self._latencies) / len(self._latencies) if self._latencies else 0
        max_latency = max(self._latencies) if self._latencies else 0

        # Format uptime
        hours, remainder = divmod(int(session_elapsed), 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h{minutes:02d}m" if hours else f"{minutes}m{seconds:02d}s"

        # Log stats
        self.logger.info(
            f"[MODEL STATS] {' | '.join(symbol_stats)} | "
            f"latency={avg_latency:.0f}ms(avg)/{max_latency:.0f}ms(max) | "
            f"session: {session_pub} pub / {session_tiles} tiles / {uptime_str} | "
            f"gap_alerts={self._gap_alerts}",
            emoji="📊"
        )

        # Write to Redis for external monitoring
        r = await self._redis_conn()
        await r.hset(self.analytics_key, mapping={
            "interval_publishes": total_pub,
            "interval_tiles": total_tiles,
            "session_publishes": session_pub,
            "session_tiles": session_tiles,
            "avg_latency_ms": int(avg_latency),
            "max_latency_ms": int(max_latency),
            "uptime_sec": int(session_elapsed),
            "gap_alerts": self._gap_alerts,
            "last_stats_ts": now,
        })

        # Reset interval counters
        self._interval_start = now
        for sym in self.symbols:
            self._interval_publishes[sym] = 0
            self._interval_tiles[sym] = 0
            self._interval_empty[sym] = 0
        self._latencies.clear()

    async def run(self, stop_event: asyncio.Event) -> None:
        self.logger.info("[MODEL PUBLISHER START] running", emoji="📤")

        try:
            while not stop_event.is_set():
                # Wait for stats interval or stop
                try:
                    await asyncio.wait_for(
                        stop_event.wait(),
                        timeout=self.STATS_INTERVAL_SEC
                    )
                    break  # stop_event was set
                except asyncio.TimeoutError:
                    # Interval elapsed, emit stats
                    await self._emit_stats()

        except asyncio.CancelledError:
            self.logger.info("[MODEL PUBLISHER] cancelled", emoji="🛑")

        except Exception as e:
            self.logger.error(f"[MODEL PUBLISHER ERROR] {e}", emoji="💥")

        finally:
            # Final stats on shutdown
            await self._emit_stats()
            self.logger.info("[MODEL PUBLISHER STOP] halted", emoji="🛑")
