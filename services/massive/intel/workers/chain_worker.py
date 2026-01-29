#!/usr/bin/env python3
# services/massive/intel/chain_worker.py

from __future__ import annotations

import asyncio
import json
import math
import time
from datetime import date
from typing import Any, Dict, List, Set

from redis.asyncio import Redis
from massive import RESTClient


# ============================================================
# Helpers
# ============================================================

def _round_to_nearest_5(x: float) -> int:
    return int(round(x / 5.0)) * 5


def _extract_strike_from_ticker(ticker: str) -> float | None:
    """Extract strike price from option ticker (last 8 digits / 1000)."""
    try:
        return int(ticker[-8:]) / 1000
    except (ValueError, IndexError):
        return None


def _is_on_strike_grid(strike: float, increment: int) -> bool:
    """Check if strike is on the specified increment grid."""
    return strike % increment == 0


# ============================================================
# ChainWorker — Geometry Authority (RAW PAYLOAD MODE)
# ============================================================

class ChainWorker:
    """
    ChainWorker
    - Sole authority for option chain geometry
    - Uses ticker as identity
    - Stores raw vendor payloads (opaque)
    - Computes geometry diffs ONLY on ticker presence
    - Emits geometry events
    """

    def __init__(self, config: Dict[str, Any], logger) -> None:
        self.config = config
        self.logger = logger

        self.chain_symbols = [
            s.strip()
            for s in config.get("MASSIVE_CHAIN_SYMBOLS", "I:SPX,I:NDX").split(",")
            if s.strip()
        ]

        self.interval_sec = int(config.get("MASSIVE_CHAIN_INTERVAL_SEC", "10"))
        self.num_expirations = int(config.get("MASSIVE_CHAIN_NUM_EXPIRATIONS", "5"))
        self.surface_ttl_sec = int(config.get("MASSIVE_SURFACE_TTL_MINUTES", 390)) * 60

        self.em_days = int(config.get("MASSIVE_CHAIN_EM_DAYS", "1"))

        # Per-symbol configuration - SPX and NDX are fundamentally different indexes
        # Each has its own: EM multiplier, strike increment, and strike grid filter
        self.symbol_config = {
            "I:SPX": {
                "em_mult": float(config.get("MASSIVE_SPX_EM_MULT", "2.25")),
                "strike_increment": int(config.get("MASSIVE_SPX_STRIKE_INCREMENT", "5")),
                "filter_strikes": config.get("MASSIVE_SPX_FILTER_STRIKES", "false").lower() == "true",
            },
            "I:NDX": {
                "em_mult": float(config.get("MASSIVE_NDX_EM_MULT", "3.25")),
                "strike_increment": int(config.get("MASSIVE_NDX_STRIKE_INCREMENT", "25")),
                "filter_strikes": config.get("MASSIVE_NDX_FILTER_STRIKES", "true").lower() == "true",
            },
        }

        self.client = RESTClient(config["MASSIVE_API_KEY"])
        self.market_redis_url = config["buses"]["market-redis"]["url"]
        self._redis: Redis | None = None

        # Geometry state
        self._last_geometry: Set[str] | None = None
        self._geometry_version: int = 0

        self.logger.info(
            f"[CHAIN INIT] symbols={self.chain_symbols} interval={self.interval_sec}s",
            emoji="🧱",
        )
        for sym, cfg in self.symbol_config.items():
            self.logger.info(
                f"[CHAIN CONFIG] {sym}: em_mult={cfg['em_mult']} strike_inc={cfg['strike_increment']} filter={cfg['filter_strikes']}",
                emoji="⚙️",
            )

    async def _redis_conn(self) -> Redis:
        if not self._redis:
            self._redis = Redis.from_url(self.market_redis_url, decode_responses=True)
        return self._redis

    async def _load_spot(self, sym: str) -> float | None:
        r = await self._redis_conn()
        raw = await r.get(f"massive:model:spot:{sym}")
        if not raw:
            return None
        return float(json.loads(raw).get("value"))

    def _compute_range(self, spot: float, vix: float | None, symbol: str) -> int:
        cfg = self.symbol_config.get(symbol, {"em_mult": 2.25})
        em_mult = cfg["em_mult"]

        if not vix or vix <= 0:
            # Fallback: use a percentage of spot when VIX unavailable
            return int(spot * 0.03)  # ~3% of spot as default range

        em = spot * (vix / 100.0) * math.sqrt(self.em_days / 252.0)
        computed_range = int(round(em_mult * em)) or 50

        self.logger.debug(
            f"[CHAIN RANGE] {symbol}: spot={spot:.0f} vix={vix:.1f} em_mult={em_mult} range={computed_range}",
            emoji="📏",
        )
        return computed_range

    def _list_expirations_sync(self, underlying: str) -> List[str]:
        """Synchronous helper - runs in thread pool."""
        exps = set()
        for opt in self.client.list_snapshot_options_chain(
            underlying, params={"limit": 250}
        ):
            exp = getattr(opt.details, "expiration_date", None)
            if exp:
                exps.add(exp)
        return sorted(exps)[:self.num_expirations]

    async def _list_expirations(self, underlying: str) -> List[str]:
        """Async wrapper - prevents blocking the event loop."""
        return await asyncio.to_thread(self._list_expirations_sync, underlying)

    def _fetch_chain_sync(
        self, underlying: str, exp: str, atm: int, rng: int
    ) -> List[tuple[str, Dict[str, Any]]]:
        """
        Synchronous chain fetch - runs in thread pool.
        Returns list of (ticker, raw_payload) tuples.
        """
        results = []
        params = {
            "underlying": underlying.replace("I:", ""),
            "expiration_date": exp,
            "strike_price.gte": atm - rng,
            "strike_price.lte": atm + rng,
            "limit": 250,
        }

        sym_cfg = self.symbol_config.get(underlying, {})
        filter_strikes = sym_cfg.get("filter_strikes", False)
        increment = sym_cfg.get("strike_increment", 5)

        for opt in self.client.list_snapshot_options_chain(underlying, params=params):
            raw = json.loads(json.dumps(opt, default=lambda o: o.__dict__))
            details = raw.get("details") or {}
            ticker = details.get("ticker")

            if not ticker:
                continue

            # Per-symbol strike grid filtering
            if filter_strikes:
                strike = _extract_strike_from_ticker(ticker)
                if strike is not None and not _is_on_strike_grid(strike, increment):
                    continue

            results.append((ticker, raw))

        return results

    async def _fetch_chain(
        self, underlying: str, exp: str, atm: int, rng: int
    ) -> List[tuple[str, Dict[str, Any]]]:
        """Async wrapper - prevents blocking the event loop."""
        return await asyncio.to_thread(
            self._fetch_chain_sync, underlying, exp, atm, rng
        )

    # ============================================================
    # WS Subscription Management
    # ============================================================

    async def _update_ws_subscriptions(self, r: Redis, contracts: Dict[str, Any]) -> None:
        """
        Update WS subscription list with 0-DTE tickers.
        Format: Q.{ticker} for quote subscription (bid/ask updates for real-time pricing).
        """
        today = date.today().strftime("%y%m%d")
        today_long = date.today().strftime("%Y%m%d")

        # Filter for 0-DTE contracts
        zero_dte_tickers = set()
        for ticker in contracts.keys():
            # Check if expiration matches today (YYMMDD or YYYYMMDD format)
            if today in ticker or today_long in ticker:
                zero_dte_tickers.add(f"T.{ticker}")  # T for trades

        if not zero_dte_tickers:
            self.logger.debug("[CHAIN] No 0-DTE tickers for WS subscription")
            return

        # Replace subscription set
        ws_sub_key = "massive:ws:subscription_list"
        pipe = r.pipeline(transaction=False)
        pipe.delete(ws_sub_key)
        pipe.sadd(ws_sub_key, *zero_dte_tickers)
        await pipe.execute()

        # Notify WsWorker of subscription update
        await r.publish(
            "massive:ws:subscription_updated",
            json.dumps({"count": len(zero_dte_tickers)})
        )

        self.logger.info(
            f"[CHAIN] Updated WS subscriptions: {len(zero_dte_tickers)} 0-DTE tickers",
            emoji="📡",
        )

    # ============================================================
    # Main cycle
    # ============================================================

    async def _run_once(self) -> None:
        r = await self._redis_conn()
        vix = await self._load_spot("VIX")
        ts = int(time.time())

        start = time.monotonic()

        all_contracts: Dict[str, Dict[str, Any]] = {}

        try:
            for underlying in self.chain_symbols:
                spot = await self._load_spot(underlying)
                if spot is None:
                    self.logger.warning(f"[CHAIN SKIP] no spot for {underlying}")
                    continue

                atm = _round_to_nearest_5(spot)
                rng = self._compute_range(spot, vix, underlying)
                expirations = await self._list_expirations(underlying.replace("I:", ""))

                self.logger.info(
                    f"[CHAIN RANGE] {underlying}: atm={atm} range=±{rng} ({atm-rng} to {atm+rng})",
                    emoji="📏",
                )

                for exp in expirations:
                    self.logger.info(f"[CHAIN FETCH] {underlying} {exp}", emoji="📡")

                    # Fetch chain in thread pool to avoid blocking event loop
                    contracts = await self._fetch_chain(underlying, exp, atm, rng)
                    for ticker, raw in contracts:
                        all_contracts[ticker] = raw

            # ====================================================
            # Geometry diff (authoritative, ticker-only)
            # ====================================================

            current_geometry = set(all_contracts.keys())

            if self._last_geometry is None:
                entered = current_geometry
                exited = set()
            else:
                entered = current_geometry - self._last_geometry
                exited = self._last_geometry - current_geometry

            if entered or exited:
                self._geometry_version += 1

                geometry_event = {
                    "version": self._geometry_version,
                    "ts": ts,
                    "entered": list(entered),
                    "exited": list(exited),
                }

                await r.set(
                    "massive:chain:latest",
                    json.dumps(
                        {
                            "version": self._geometry_version,
                            "ts": ts,
                            "contracts": all_contracts,
                        }
                    ),
                )

                await r.set(
                    "massive:chain:delta:latest",
                    json.dumps(geometry_event),
                )

                await r.publish(
                    "massive:chain:geometry_updated",
                    json.dumps({"version": self._geometry_version}),
                )

                self.logger.ok(
                    f"[GEOMETRY UPDATE] v={self._geometry_version} "
                    f"+{len(entered)} -{len(exited)}",
                    emoji="📐",
                )

                # Update WS subscription list with 0-DTE tickers
                await self._update_ws_subscriptions(r, all_contracts)

            else:
                self.logger.debug("[GEOMETRY NO-OP] unchanged", emoji="➖")

            self._last_geometry = current_geometry

            latency_ms = int((time.monotonic() - start) * 1000)
            await r.hset("massive:chain:analytics", "latency_last_ms", latency_ms)
            await r.hincrby("massive:chain:analytics", "runs", 1)

            self.logger.info(
                f"[CHAIN CYCLE COMPLETE] {latency_ms}ms",
                emoji="🔁",
            )

        except Exception as e:
            self.logger.error(f"[CHAIN ERROR] {e}", emoji="💥")
            await r.hincrby("massive:chain:analytics", "errors", 1)
            raise

    async def run(self, stop_event: asyncio.Event) -> None:
        self.logger.info("[CHAIN START] running", emoji="🚀")
        try:
            while not stop_event.is_set():
                await self._run_once()
                await asyncio.sleep(self.interval_sec)
        finally:
            self.logger.info("[CHAIN STOP] halted", emoji="🛑")