# services/massive/intel/vp_worker.py

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, UTC
from typing import Any, Dict, Optional

import redis.asyncio as aioredis

import logutil


class VPWorker:
    """
    Intraday Volume Profile updater.

    Design:
      - Reads base profile from SYSTEM_REDIS (massive:volume_profile)
      - Listens to an intraday bar stream (e.g. massive:bars:SPY) on MARKET_REDIS
      - For each bar: map ETF price -> synthetic price (e.g. SPY → SPX),
        and increment volume bins in a session overlay key:

          massive:vp:session:SPX:{YYYY-MM-DD}

      - Optionally rebuild/update a merged model key:

          massive:model:volume_profile:SPX

    This is intentionally conservative: no assumptions about
    your final bar stream yet – just a place to plug it in.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self.service_name = config.get("service_name", "massive")

        # Redis URLs
        self.system_redis_url = os.getenv(
            "SYSTEM_REDIS_URL", "redis://127.0.0.1:6379"
        )
        self.market_redis_url = os.getenv(
            "MARKET_REDIS_URL", "redis://127.0.0.1:6380"
        )

        # Stream & symbols
        self.bar_stream_key = os.getenv(
            "MASSIVE_VP_BAR_STREAM", "massive:bars:SPY"
        )
        # Synthetic mapping SPY → SPX for now
        self.synthetic_symbol = os.getenv("MASSIVE_VP_SYNTHETIC", "SPX")
        self.multiplier = int(os.getenv("MASSIVE_VP_MULTIPLIER", "10"))

        # Loop interval (when idle)
        self.poll_block_ms = int(os.getenv("MASSIVE_VP_BLOCK_MS", "5000"))

        self._sys = aioredis.from_url(
            self.system_redis_url, decode_responses=True
        )
        self._mkt = aioredis.from_url(
            self.market_redis_url, decode_responses=True
        )

    async def _load_base_profile(self) -> Optional[Dict[str, Any]]:
        raw = await self._sys.get("massive:volume_profile")
        if not raw:
            logutil.log(
                self.service_name,
                "WARN",
                "⚠️",
                "No base volume profile found at massive:volume_profile",
            )
            return None
        try:
            return json.loads(raw)
        except Exception as e:
            logutil.log(
                self.service_name,
                "ERROR",
                "💥",
                f"Failed to decode base profile JSON: {e}",
            )
            return None

    async def _apply_bar(self, price: float, volume: float) -> None:
        """
        Apply a single bar (ETF price + volume) to session overlay bins.
        """
        session_date = datetime.now(UTC).date().isoformat()
        session_key = f"massive:vp:session:{self.synthetic_symbol}:{session_date}"

        synthetic_price = int(round(price * self.multiplier))
        # Use hash of bins: field=price, value=volume
        # We increment: HINCRBYFLOAT
        try:
            await self._sys.hincrbyfloat(
                session_key, str(synthetic_price), float(volume)
            )
            # Reasonable TTL, e.g. keep session overlays for a few days
            await self._sys.expire(session_key, 86400 * 3)
        except Exception as e:
            logutil.log(
                self.service_name,
                "ERROR",
                "💥",
                f"Failed to update session VP bin: {e}",
            )

    async def _merge_and_publish(self) -> None:
        """
        Optional: merge base + session into a single live model.
        For now this is a placeholder; you can fill with your own
        POC / value area computations later.
        """
        base = await self._load_base_profile()
        if not base:
            return

        session_date = datetime.now(UTC).date().isoformat()
        session_key = f"massive:vp:session:{self.synthetic_symbol}:{session_date}"

        try:
            session_bins = await self._sys.hgetall(session_key)
        except Exception as e:
            logutil.log(
                self.service_name,
                "ERROR",
                "💥",
                f"Failed to read session VP bins: {e}",
            )
            session_bins = {}

        # Combine buckets_raw + session bins
        base_bins = {
            int(k): float(v)
            for k, v in base.get("buckets_raw", {}).items()
        }
        for k_str, v_str in session_bins.items():
            k = int(k_str)
            v = float(v_str)
            base_bins[k] = base_bins.get(k, 0.0) + v

        # Build a light model (no OHLC to keep it small)
        model_key = f"massive:model:volume_profile:{self.synthetic_symbol}"
        now_ts = datetime.now(UTC).isoformat(timespec="seconds")

        model = {
            "symbol": self.synthetic_symbol,
            "ts": now_ts,
            "bin_size": base.get("bin_size", 1),
            "buckets": {str(k): v for k, v in base_bins.items()},
        }

        try:
            await self._sys.set(model_key, json.dumps(model))
            logutil.log(
                self.service_name,
                "INFO",
                "📡",
                f"Updated live volume_profile model at {model_key}",
            )
        except Exception as e:
            logutil.log(
                self.service_name,
                "ERROR",
                "💥",
                f"Failed to write live volume_profile model: {e}",
            )

    async def run(self, stop_event: asyncio.Event) -> None:
        """
        Main VPWorker loop.

        Current behavior:
          - Blocks on XREAD from massive:bars:SPY (or configured stream).
          - For each bar with fields {price, volume}, updates session overlay.
          - Periodically merges base + session into a model key.

        Until you wire in the real bar stream, this will mostly idle.
        """
        logutil.log(
            self.service_name,
            "INFO",
            "🎛️",
            f"VPWorker starting: stream={self.bar_stream_key}, synthetic={self.synthetic_symbol}, mult={self.multiplier}",
        )

        last_merge = datetime.now(UTC)
        merge_interval_sec = int(os.getenv("MASSIVE_VP_MERGE_INTERVAL_SEC", "60"))

        # Start by attempting to load base profile once
        await self._load_base_profile()

        # XREAD requires a starting ID; use "$" to start from new messages
        last_id = "$"

        try:
            while not stop_event.is_set():
                try:
                    streams = await self._mkt.xread(
                        {self.bar_stream_key: last_id},
                        block=self.poll_block_ms,
                        count=100,
                    )
                except Exception as e:
                    logutil.log(
                        self.service_name,
                        "ERROR",
                        "💥",
                        f"XREAD error on {self.bar_stream_key}: {e}",
                    )
                    await asyncio.sleep(1.0)
                    continue

                if streams:
                    for stream_key, messages in streams:
                        for msg_id, fields in messages:
                            last_id = msg_id
                            # Expect fields like {"price": "...", "volume": "..."}
                            try:
                                price = float(fields.get("price"))
                                volume = float(fields.get("volume"))
                            except Exception:
                                continue
                            await self._apply_bar(price, volume)

                # Periodic merge
                now = datetime.now(UTC)
                if (now - last_merge).total_seconds() >= merge_interval_sec:
                    await self._merge_and_publish()
                    last_merge = now

        except asyncio.CancelledError:
            logutil.log(
                self.service_name,
                "INFO",
                "🛑",
                "VPWorker cancelled (shutdown)",
            )
            raise
        except Exception as e:
            logutil.log(
                self.service_name,
                "ERROR",
                "❌",
                f"VPWorker fatal error: {e}",
            )
            raise
        finally:
            logutil.log(
                self.service_name,
                "INFO",
                "✅",
                "VPWorker stopped",
            )