from __future__ import annotations

import asyncio
import json
import time
from typing import Dict, Any, List

from redis.asyncio import Redis


class HeatmapModelBuilder:
    """
    Heatmap Model Builder — pulls from unified surface hash (no epochs)
    Always publishes if surface exists — shows last good data after close
    """

    ANALYTICS_KEY = "massive:model:analytics"
    BUILDER_NAME = "heatmap"

    def __init__(self, config: Dict[str, Any], logger):
        self.config = config
        self.logger = logger

        self.interval_sec = int(config.get("MASSIVE_HEATMAP_INTERVAL_SEC", 1))

        # Read widths from config (comma-separated strings)
        spx_widths_str = config.get("MASSIVE_WIDTHS_SPX", "20,25,30,35,40,45,50")
        ndx_widths_str = config.get("MASSIVE_WIDTHS_NDX", "50,100,150,200,250,300")

        self.widths_map: Dict[str, List[int]] = {
            "I:SPX": [int(w.strip()) for w in spx_widths_str.split(",") if w.strip()],
            "I:NDX": [int(w.strip()) for w in ndx_widths_str.split(",") if w.strip()],
        }

        self.market_redis_url = config["buses"]["market-redis"]["url"]
        self._redis: Redis | None = None

        self.logger.info(
            f"[HEATMAP BUILDER INIT] interval={self.interval_sec}s widths_map={self.widths_map}",
            emoji="🔥",
        )

    async def _redis_conn(self) -> Redis:
        if not self._redis:
            self._redis = Redis.from_url(
                self.market_redis_url,
                decode_responses=True,
            )
        return self._redis

    # ------------------------------------------------------------
    # Strategy calculators (unchanged)
    # ------------------------------------------------------------

    @staticmethod
    def _butterfly_debit(mids: Dict[float, float], center: float, width: int) -> Optional[float]:
        low = mids.get(center - width)
        high = mids.get(center + width)
        if low is None or high is None:
            return None
        return low + high - 2 * mids[center]

    @staticmethod
    def _vertical_debit_long(mids: Dict[float, float], long_strike: float, width: int, side: str) -> Optional[float]:
        if side == "call":
            long_mid = mids.get(long_strike)
            short_mid = mids.get(long_strike + width)
        else:
            long_mid = mids.get(long_strike)
            short_mid = mids.get(long_strike - width)
        if long_mid is None or short_mid is None:
            return None
        return long_mid - short_mid

    @staticmethod
    def _single_value(mids: Dict[float, float], strike: float) -> Optional[float]:
        return mids.get(strike)

    @staticmethod
    def _tile_payload(strategy: str, side: str, strike: float, width: int = None) -> Dict[str, Any]:
        if strategy == "single":
            legs = [{"strike": strike, "type": side}]
            tos = f"{side.upper()} {strike}"
        elif strategy == "vertical":
            if side == "call":
                long_strike = strike
                short_strike = strike + width
            else:
                long_strike = strike
                short_strike = strike - width
            legs = [
                {"strike": long_strike, "type": side},
                {"strike": short_strike, "type": "put" if side == "call" else "call"}
            ]
            tos = f"{side.upper()} VERTICAL {min(long_strike, short_strike)}-{max(long_strike, short_strike)}"
        else:  # butterfly
            low = strike - width
            center = strike
            high = strike + width
            legs = [
                {"strike": low, "type": side},
                {"strike": center, "type": side, "qty": -2},
                {"strike": high, "type": side},
            ]
            tos = f"{side.upper()} BUTTERFLY {low}-{center}-{high}"

        return {"legs": legs, "tos_script": tos}

    async def _build_once(self) -> None:
        r = await self._redis_conn()
        pipe = r.pipeline(transaction=False)

        t_start = time.monotonic()
        total_tiles = 0

        symbols = [
            s.strip()
            for s in self.config.get("MASSIVE_CHAIN_SYMBOLS", "I:SPX").split(",")
            if s.strip()
        ]

        try:
            for symbol in symbols:
                widths = self.widths_map.get(symbol, [])
                if not widths:
                    self.logger.warning(f"[HEATMAP] No widths defined for {symbol} — skipping")
                    continue

                surface_key = f"massive:surface:{symbol}:latest"
                if not await r.exists(surface_key):
                    self.logger.debug(f"[HEATMAP] No surface yet for {symbol}")
                    continue

                surface = await r.hgetall(surface_key)
                if not surface:
                    self.logger.debug(f"[HEATMAP] Empty surface for {symbol} — skipping publish")
                    continue

                # Parse mids per type — even if mid is None (stale), we keep the strike
                call_mids = {}
                put_mids = {}
                for strike_str, contract_json in surface.items():
                    try:
                        contract = json.loads(contract_json)
                        strike = float(strike_str)
                        mid = contract.get("mid")
                        typ = contract.get("type")
                        if typ in ("call", "put"):
                            if typ == "call":
                                call_mids[strike] = mid if mid is not None else 0.0
                            else:
                                put_mids[strike] = mid if mid is not None else 0.0
                    except Exception as e:
                        self.logger.debug(f"[HEATMAP] Bad contract JSON: {e}")

                strikes = sorted(set(list(call_mids.keys()) + list(put_mids.keys())), reverse=True)

                model_base = {
                    "ts": time.time(),
                    "symbol": symbol,
                    "market_state": "closed" if time.time() % 86400 > 57600 else "open",  # rough after-hours detect
                }

                # Butterfly & Vertical per side
                for side, mids in [("call", call_mids), ("put", put_mids)]:
                    if not mids:
                        continue

                    butterfly_tiles = {}
                    vertical_tiles = {}

                    for strike in strikes:
                        if strike not in mids:
                            continue

                        b_tile = {}
                        for w in widths:
                            debit = self._butterfly_debit(mids, strike, w)
                            if debit is not None:
                                payload = self._tile_payload("butterfly", side, strike, w)
                                b_tile[str(w)] = {"value": round(debit, 2), "payload": payload}
                        if b_tile:
                            butterfly_tiles[str(int(strike))] = b_tile

                        v_tile = {}
                        for w in widths:
                            debit = self._vertical_debit_long(mids, strike, w, side)
                            if debit is not None:
                                payload = self._tile_payload("vertical", side, strike, w)
                                v_tile[str(w)] = {"value": round(debit, 2), "payload": payload}
                        if v_tile:
                            vertical_tiles[str(int(strike))] = v_tile

                    if butterfly_tiles:
                        await r.set(
                            f"massive:heatmap:model:{symbol}:butterfly:{side}:latest",
                            json.dumps({**model_base, "tiles": butterfly_tiles}),
                            ex=86400,  # 24h so closing data survives overnight
                        )
                        total_tiles += len(butterfly_tiles)

                    if vertical_tiles:
                        await r.set(
                            f"massive:heatmap:model:{symbol}:vertical:{side}:latest",
                            json.dumps({**model_base, "tiles": vertical_tiles}),
                            ex=86400,
                        )
                        total_tiles += len(vertical_tiles)

                # Single (both sides)
                single_tiles = {}
                for strike in strikes:
                    tile = {}
                    if strike in call_mids:
                        payload = self._tile_payload("single", "call", strike)
                        tile["call"] = {"value": round(call_mids[strike], 2), "payload": payload}
                    if strike in put_mids:
                        payload = self._tile_payload("single", "put", strike)
                        tile["put"] = {"value": round(put_mids[strike], 2), "payload": payload}
                    if tile:
                        single_tiles[str(int(strike))] = tile

                if single_tiles:
                    await r.set(
                        f"massive:heatmap:model:{symbol}:single:both:latest",
                        json.dumps({**model_base, "tiles": single_tiles}),
                        ex=86400,
                    )
                    total_tiles += len(single_tiles)

            # Analytics
            pipe.incr(f"{self.ANALYTICS_KEY}:{self.BUILDER_NAME}:runs")
            pipe.set(f"{self.ANALYTICS_KEY}:{self.BUILDER_NAME}:last_ts", time.time())
            pipe.hincrby(f"{self.ANALYTICS_KEY}", f"{self.BUILDER_NAME}:tiles_total", total_tiles)

        except Exception as e:
            pipe.incr(f"{self.ANALYTICS_KEY}:model:errors")
            self.logger.error(f"[HEATMAP BUILDER ERROR] {e}", emoji="💥")
            raise

        finally:
            dt = time.monotonic() - t_start
            latency_ms = int(dt * 1000)

            count = await r.hincrby(f"{self.ANALYTICS_KEY}", f"{self.BUILDER_NAME}:latency_count", 1)
            prev_avg = float(await r.get(f"{self.ANALYTICS_KEY}:{self.BUILDER_NAME}:latency_avg_ms") or 0)
            new_avg = (prev_avg * (count - 1) + latency_ms) / count if count > 1 else latency_ms

            pipe.set(f"{self.ANALYTICS_KEY}:{self.BUILDER_NAME}:latency_last_ms", latency_ms)
            pipe.set(f"{self.ANALYTICS_KEY}:{self.BUILDER_NAME}:latency_avg_ms", int(new_avg))

            await pipe.execute()

        self.logger.info(
            f"[HEATMAP MODEL] total_tiles={total_tiles} latency={latency_ms}ms",
            emoji="🧩",
        )

    async def run(self, stop_event: asyncio.Event) -> None:
        self.logger.info("[HEATMAP BUILDER START] running", emoji="🔥")

        try:
            while not stop_event.is_set():
                t0 = time.monotonic()
                await self._build_once()
                dt = time.monotonic() - t0
                await asyncio.sleep(max(0.0, self.interval_sec - dt))
        finally:
            self.logger.info("HeatmapModelBuilder stopped", emoji="🛑")