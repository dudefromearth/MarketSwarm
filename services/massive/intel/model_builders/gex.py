# services/massive/intel/model_builders/gex.py

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Dict, Any, List

from redis.asyncio import Redis


_TICKER_RE = re.compile(
    r"^O:(?P<root>[A-Z]+)(?P<yymmdd>\d{6,8})(?P<cp>[CP])(?P<strike>\d+)$"
)


class GexModelBuilder:
    """
    GEX (Gamma Exposure) Model Builder

    Calculates gamma exposure per strike per expiration.
    GEX = Gamma × Open Interest × 100 (contract multiplier)

    Publishes separate models for calls and puts to:
    - massive:gex:model:{symbol}:calls
    - massive:gex:model:{symbol}:puts
    """

    ANALYTICS_KEY = "massive:model:analytics"
    BUILDER_NAME = "gex"

    def __init__(self, config: Dict[str, Any], logger):
        self.config = config
        self.logger = logger

        self.interval_sec = int(config.get("MASSIVE_GEX_INTERVAL_SEC", 5))

        self.symbols = [
            s.strip()
            for s in config.get("MASSIVE_CHAIN_SYMBOLS", "I:SPX,I:NDX").split(",")
            if s.strip()
        ]

        self.market_redis_url = config["buses"]["market-redis"]["url"]
        self._redis: Redis | None = None

        # Contract multiplier (standard options = 100)
        self.contract_multiplier = 100

        self.logger.info(
            f"[GEX BUILDER INIT] symbols={self.symbols} interval={self.interval_sec}s",
            emoji="📊",
        )

    async def _redis_conn(self) -> Redis:
        if not self._redis:
            self._redis = Redis.from_url(
                self.market_redis_url,
                decode_responses=True,
            )
        return self._redis

    def _parse_ticker(self, ticker: str) -> tuple[str, str, float, str] | None:
        """
        Parse ticker to extract (root, expiration, strike, option_type).
        Returns None if invalid.
        """
        m = _TICKER_RE.match(ticker)
        if not m:
            return None

        root = m.group("root")
        yymmdd = m.group("yymmdd")
        cp = m.group("cp")
        strike_raw = m.group("strike")

        # Convert strike (last 3 digits are decimals)
        strike = int(strike_raw) / 1000.0

        # Convert expiration to ISO date
        if len(yymmdd) == 6:
            exp = f"20{yymmdd[:2]}-{yymmdd[2:4]}-{yymmdd[4:6]}"
        else:
            exp = f"{yymmdd[:4]}-{yymmdd[4:6]}-{yymmdd[6:8]}"

        option_type = "call" if cp == "C" else "put"

        # Map root to symbol
        if root in ("SPX", "SPXW", "SPXM"):
            symbol = "I:SPX"
        elif root in ("NDX", "NDXP"):
            symbol = "I:NDX"
        else:
            return None

        return symbol, exp, strike, option_type

    async def _build_once(self) -> None:
        r = await self._redis_conn()
        t_start = time.monotonic()

        try:
            # Read chain data
            raw = await r.get("massive:chain:latest")
            if not raw:
                self.logger.debug("[GEX] No chain data available")
                return

            chain = json.loads(raw)
            contracts = chain.get("contracts", {})
            if not contracts:
                self.logger.debug("[GEX] Empty chain")
                return

            # Structure: {symbol: {expiration: {strike: gex_value}}}
            calls_by_symbol: Dict[str, Dict[str, Dict[str, float]]] = {s: {} for s in self.symbols}
            puts_by_symbol: Dict[str, Dict[str, Dict[str, float]]] = {s: {} for s in self.symbols}

            processed = 0
            skipped = 0

            for ticker, payload in contracts.items():
                parsed = self._parse_ticker(ticker)
                if parsed is None:
                    skipped += 1
                    continue

                symbol, expiration, strike, option_type = parsed

                if symbol not in self.symbols:
                    skipped += 1
                    continue

                # Extract gamma and OI
                greeks = payload.get("greeks") or {}
                gamma = greeks.get("gamma")
                oi = payload.get("open_interest") or 0

                if gamma is None or oi == 0:
                    skipped += 1
                    continue

                # Calculate GEX = gamma × OI × 100
                # No rounding - preserve full precision
                gex = gamma * oi * self.contract_multiplier

                strike_str = str(int(strike))

                if option_type == "call":
                    calls_by_symbol[symbol].setdefault(expiration, {})[strike_str] = gex
                else:
                    puts_by_symbol[symbol].setdefault(expiration, {})[strike_str] = gex

                processed += 1

            # Publish models per symbol
            ts = time.time()
            for symbol in self.symbols:
                calls_exps = calls_by_symbol[symbol]
                puts_exps = puts_by_symbol[symbol]

                if calls_exps:
                    calls_model = {
                        "ts": ts,
                        "symbol": symbol,
                        "expirations": dict(sorted(calls_exps.items())),
                    }
                    await r.set(
                        f"massive:gex:model:{symbol}:calls",
                        json.dumps(calls_model),
                        ex=86400,
                    )

                if puts_exps:
                    puts_model = {
                        "ts": ts,
                        "symbol": symbol,
                        "expirations": dict(sorted(puts_exps.items())),
                    }
                    await r.set(
                        f"massive:gex:model:{symbol}:puts",
                        json.dumps(puts_model),
                        ex=86400,
                    )

            latency_ms = int((time.monotonic() - t_start) * 1000)

            # Analytics
            await r.hincrby(self.ANALYTICS_KEY, f"{self.BUILDER_NAME}:runs", 1)
            await r.hset(self.ANALYTICS_KEY, f"{self.BUILDER_NAME}:latency_last_ms", latency_ms)
            await r.hset(self.ANALYTICS_KEY, f"{self.BUILDER_NAME}:contracts_processed", processed)

            self.logger.info(
                f"[GEX MODEL] processed={processed} skipped={skipped} latency={latency_ms}ms",
                emoji="📊",
            )

        except Exception as e:
            self.logger.error(f"[GEX BUILDER ERROR] {e}", emoji="💥")
            await r.hincrby(self.ANALYTICS_KEY, f"{self.BUILDER_NAME}:errors", 1)
            raise

    async def run(self, stop_event: asyncio.Event) -> None:
        self.logger.info("[GEX BUILDER START] running", emoji="📊")

        try:
            while not stop_event.is_set():
                t0 = time.monotonic()
                await self._build_once()
                dt = time.monotonic() - t0
                await asyncio.sleep(max(0.0, self.interval_sec - dt))
        finally:
            self.logger.info("GexModelBuilder stopped", emoji="🛑")
