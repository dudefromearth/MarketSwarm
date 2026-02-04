# services/massive/intel/hydrators/ws_hydrator.py

import json
import time
from typing import Dict, Set, Any, List

from redis.asyncio import Redis


class WsHydrator:
    """
    Hydrates websocket ticks into in-memory chain_states dict.

    Dirty semantics:
    - First-seen contract with any price field → dirty
    - Subsequent dirty flips only on real field change
    - Timestamp alone never flips dirty

    Strike-level tracking:
    - Tracks tick activity per strike for reversal signal analysis
    - Separates bid vs ask updates for directional pressure
    - Emits time-series data for correlation with gamma walls / volume profile
    """

    def __init__(self, config: Dict[str, Any], logger):
        self.config = config
        self.logger = logger

        self.chain_states: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.dirty: Dict[str, Set[str]] = {}
        self.ws_paused: Dict[str, bool] = {}

        # Per-strike activity tracking (reset on each emit)
        # Structure: {symbol: {strike: {ticks, bids, asks, calls, puts}}}
        self.strike_activity: Dict[str, Dict[int, Dict[str, int]]] = {}

        # Symbols to track for strike activity (from config or default to SPX/NDX)
        chain_symbols = config.get("env", {}).get("MASSIVE_CHAIN_SYMBOLS", "I:SPX,I:NDX")
        self.tracked_symbols: Set[str] = set(s.strip() for s in chain_symbols.split(","))

        # Cached chain baseline - persists across snapshots so WS can work
        # even when chain worker hasn't updated recently
        self._cached_chain: Dict[str, Any] | None = None
        self._cached_chain_ts: float = 0

        self.market_redis_url = config["buses"]["market-redis"]["url"]
        self._redis: Redis | None = None

        self.logger.info(
            f"[WS HYDRATOR INIT] hydration + strike-level activity tracking for {self.tracked_symbols}",
            emoji="💧",
        )

    async def _redis_conn(self) -> Redis:
        if not self._redis:
            self._redis = Redis.from_url(self.market_redis_url, decode_responses=True)
        return self._redis

    # -------------------------
    # Symbol utilities
    # -------------------------

    def _parse_contract(self, ticker: str) -> tuple[str, float, str] | None:
        """
        Parse option ticker to extract underlying, strike, and side.
        Format: O:SPXW260127P06985000
                  ^^^^------^^^^^^^^^
                  root|date |C/P|strike (8 digits, divide by 1000)

        Returns: (underlying, strike, side) where side is 'C' or 'P'
        """
        if not ticker.startswith("O:"):
            return None

        clean = ticker[2:]  # "SPXW260127P06985000"

        # Find where the date starts (first digit)
        date_start = None
        for i, c in enumerate(clean):
            if c.isdigit():
                date_start = i
                break

        if date_start is None:
            return None

        underlying = clean[:date_start]  # "SPXW"
        rest = clean[date_start:]  # "260127P06985000"

        # Extract C/P at position 6 (after YYMMDD)
        try:
            side = rest[6]  # 'C' or 'P'
            strike = float(rest[7:]) / 1000
            return underlying, strike, side
        except Exception:
            return None

    def _normalize_underlying(self, raw: str) -> str:
        if raw.startswith("SPX"):
            return "I:SPX"
        if raw.startswith("NDX"):
            return "I:NDX"
        return raw

    # -------------------------
    # Update helpers
    # -------------------------

    @staticmethod
    def _update_field(contract: Dict[str, Any], field: str, value) -> bool:
        old = contract.get(field)
        changed = old is None or old != value
        contract[field] = value
        return changed

    # -------------------------
    # WS processing
    # -------------------------

    async def _process_message(self, fields, pipe, touched_symbols):
        payload = fields.get("payload")
        if not payload:
            return

        try:
            events = json.loads(payload)
            if not isinstance(events, list):
                events = [events]
        except Exception:
            pipe.incr("massive:ws:hydrate:parse_fail")
            return

        for e in events:
            pipe.incr("massive:ws:hydrate:seen")

            ts = e.get("t")
            sym_raw = e.get("sym")
            if ts is None or not sym_raw:
                continue

            parsed = self._parse_contract(sym_raw)
            if not parsed:
                pipe.incr("massive:ws:hydrate:parse_fail")
                continue

            raw_underlying, strike, option_side = parsed
            norm_sym = self._normalize_underlying(raw_underlying)
            strike_int = int(strike)

            if norm_sym not in self.chain_states:
                self.chain_states[norm_sym] = {}
                self.dirty[norm_sym] = set()
                self.ws_paused[norm_sym] = False

            # Only track strike activity for configured symbols (I:SPX, I:NDX by default)
            track_strikes = norm_sym in self.tracked_symbols
            strike_stats = None

            if track_strikes:
                if norm_sym not in self.strike_activity:
                    self.strike_activity[norm_sym] = {}
                # Initialize strike activity tracking
                if strike_int not in self.strike_activity[norm_sym]:
                    self.strike_activity[norm_sym][strike_int] = {
                        "ticks": 0, "bids": 0, "asks": 0, "calls": 0, "puts": 0
                    }
                strike_stats = self.strike_activity[norm_sym][strike_int]

            ticker = sym_raw
            is_new = ticker not in self.chain_states[norm_sym]

            if is_new:
                self.chain_states[norm_sym][ticker] = {
                    "id": ticker,
                    "underlying": norm_sym,
                    "strike": strike,
                    "side": option_side,
                }
                # Track new ticker additions in analytics (no log spam)
                pipe.hincrby("massive:ws:hydrate:analytics", f"new_tickers_{norm_sym}", 1)

            contract = self.chain_states[norm_sym][ticker]
            updated = False
            saw_price_field = False

            # Last price
            if e.get("p") is not None:
                saw_price_field = True
                if self._update_field(contract, "last", float(e["p"])):
                    updated = True

            # Bid / ask (track separately for directional pressure)
            if e.get("b") is not None:
                saw_price_field = True
                if self._update_field(contract, "bid", float(e["b"])):
                    updated = True
                    if strike_stats:
                        strike_stats["bids"] += 1

            if e.get("a") is not None:
                saw_price_field = True
                if self._update_field(contract, "ask", float(e["a"])):
                    updated = True
                    if strike_stats:
                        strike_stats["asks"] += 1

            # Size
            if e.get("s") is not None:
                saw_price_field = True
                if self._update_field(contract, "size", int(e["s"])):
                    updated = True

            contract["ts"] = ts

            # Track per-strike activity (only for tracked symbols)
            if updated and strike_stats:
                strike_stats["ticks"] += 1
                if option_side == "C":
                    strike_stats["calls"] += 1
                else:
                    strike_stats["puts"] += 1

            # -------------------------
            # DIRTY POLICY
            # -------------------------

            should_dirty = (
                (is_new and saw_price_field) or
                (updated and not self.ws_paused.get(norm_sym, False))
            )

            if should_dirty:
                was_dirty = ticker in self.dirty[norm_sym]
                self.dirty[norm_sym].add(ticker)

                if not was_dirty:
                    pipe.hincrby(
                        "massive:snapshot:analytics",
                        f"dirty_flips_{norm_sym}",
                        1,
                    )

            pipe.incr("massive:ws:hydrate:hydrated")
            touched_symbols.add(norm_sym)

    # -------------------------
    # Batch hydration
    # -------------------------

    async def hydrate_batch(self, messages: List[Dict[str, str]]) -> Set[str]:
        redis = await self._redis_conn()
        pipe = redis.pipeline(transaction=False)

        touched: Set[str] = set()
        start = time.monotonic()

        for msg in messages:
            await self._process_message(msg, pipe, touched)

        # -------------------------
        # Snapshot gating
        # -------------------------

        dirty_symbols = {s for s in touched if self.dirty.get(s)}

        for sym in dirty_symbols:
            pipe.hset(
                "massive:snapshot:analytics",
                f"dirty_count_{sym}",
                len(self.dirty[sym]),
            )
            pipe.hset(
                "massive:snapshot:analytics",
                f"state_size_{sym}",
                len(self.chain_states.get(sym, {})),
            )

        pipe.hset(
            "massive:snapshot:analytics",
            "dirty_count_total",
            sum(len(self.dirty[s]) for s in dirty_symbols),
        )

        # Add performance metrics
        duration_ms = (time.monotonic() - start) * 1000
        pipe.hset("massive:ws:hydrate:analytics", "last_duration_ms", f"{duration_ms:.2f}")
        pipe.hset("massive:ws:hydrate:analytics", "last_batch_size", len(messages))
        pipe.hset("massive:ws:hydrate:analytics", "dirty_symbols", len(dirty_symbols))
        pipe.hset("massive:ws:hydrate:analytics", "touched_symbols", len(touched))
        pipe.hset("massive:ws:hydrate:analytics", "last_ts", time.time())
        pipe.hincrby("massive:ws:hydrate:analytics", "batches_processed", 1)

        await pipe.execute()

        return dirty_symbols

    # -------------------------
    # Merged snapshot for Builder
    # -------------------------

    async def get_merged_snapshots(self) -> Dict[str, Dict[str, Any]]:
        """
        Merge chain baseline with WS price updates.
        Returns snapshot dict keyed by symbol, ready for Builder.

        Uses cached chain baseline if Redis fetch fails or returns empty,
        ensuring WS data continues to flow even when chain worker is delayed.
        """
        redis = await self._redis_conn()

        # Try to load fresh chain baseline
        raw = await redis.get("massive:chain:latest")

        if raw:
            # Fresh chain data available - update cache
            chain = json.loads(raw)
            self._cached_chain = chain
            self._cached_chain_ts = time.time()
        elif self._cached_chain:
            # No fresh data, but we have cache - use it
            chain = self._cached_chain
            cache_age = time.time() - self._cached_chain_ts
            if cache_age > 60:  # Log warning if cache is stale
                self.logger.warning(
                    f"[WS HYDRATOR] Using cached chain baseline (age={cache_age:.0f}s)",
                    emoji="⚠️",
                )
        else:
            # No chain data at all - can't proceed
            self.logger.warning(
                "[WS HYDRATOR] No chain baseline available (waiting for chain worker)",
                emoji="⏳",
            )
            return {}

        contracts = chain.get("contracts", {})

        # Bucket by symbol and merge WS updates
        result: Dict[str, Dict[str, Any]] = {}

        for ticker, payload in contracts.items():
            # Determine symbol from ticker
            symbol = None
            if ticker.startswith("O:SPX") or ticker.startswith("O:SPXW"):
                symbol = "I:SPX"
            elif ticker.startswith("O:NDX") or ticker.startswith("O:NDXP"):
                symbol = "I:NDX"

            if not symbol:
                continue

            if symbol not in result:
                result[symbol] = {}

            # Start with chain baseline
            merged = dict(payload)

            # Overlay WS price updates if available
            ws_state = self.chain_states.get(symbol, {}).get(ticker)
            if ws_state:
                # Update last_quote with WS prices
                last_quote = merged.get("last_quote", {})
                if isinstance(last_quote, dict):
                    last_quote = dict(last_quote)
                else:
                    last_quote = {}

                if "bid" in ws_state:
                    last_quote["bid"] = ws_state["bid"]
                if "ask" in ws_state:
                    last_quote["ask"] = ws_state["ask"]
                if "last" in ws_state:
                    last_quote["last"] = ws_state["last"]

                # Recalculate midpoint (set both "mid" and "midpoint" for normalizer compatibility)
                bid = last_quote.get("bid")
                ask = last_quote.get("ask")
                if bid is not None and ask is not None:
                    midpoint = (bid + ask) / 2
                    last_quote["midpoint"] = midpoint
                    last_quote["mid"] = midpoint  # normalizer checks "mid" first

                merged["last_quote"] = last_quote

            result[symbol][ticker] = merged

        # Track diffs before clearing (for rate optimization)
        diffs_this_emit = sum(len(d) for d in self.dirty.values())
        now = time.time()

        pipe = redis.pipeline(transaction=False)
        pipe.hincrby("massive:ws:hydrate:analytics", "diffs_total", diffs_this_emit)
        pipe.hincrby("massive:ws:hydrate:analytics", "emits_total", 1)
        pipe.hset("massive:ws:hydrate:analytics", "diffs_last_emit", diffs_this_emit)

        # Time-series stream for window analysis (keep ~1 hour of data)
        pipe.xadd(
            "massive:ws:emit:stream",
            {"ts": now, "diffs": diffs_this_emit, "contracts": sum(len(r) for r in result.values())},
            maxlen=15000,
            approximate=True,
        )

        # Emit per-strike activity to time-series stream (for reversal signal analysis)
        for sym, strikes in self.strike_activity.items():
            active_strikes = {k: v for k, v in strikes.items() if v["ticks"] > 0}
            if active_strikes:
                # Emit strike activity snapshot
                pipe.xadd(
                    f"massive:ws:strike:stream:{sym}",
                    {
                        "ts": now,
                        "data": json.dumps(active_strikes),
                    },
                    maxlen=15000,
                    approximate=True,
                )

                # Also track hot strikes (most active) for quick lookup
                sorted_by_ticks = sorted(active_strikes.items(), key=lambda x: x[1]["ticks"], reverse=True)
                top_strikes = sorted_by_ticks[:10]

                hot_key = f"massive:ws:strike:hot:{sym}"
                for strike, stats in top_strikes:
                    # Directional pressure: positive = more bids (bullish), negative = more asks (bearish)
                    pressure = stats["bids"] - stats["asks"]
                    pipe.hset(
                        hot_key,
                        str(strike),
                        json.dumps({
                            "ticks": stats["ticks"],
                            "bids": stats["bids"],
                            "asks": stats["asks"],
                            "calls": stats["calls"],
                            "puts": stats["puts"],
                            "pressure": pressure,
                            "ts": now,
                        })
                    )
                # Set TTL on keys to prevent unbounded growth (24 hours)
                pipe.expire(hot_key, 86400)
                pipe.expire(f"massive:ws:strike:stream:{sym}", 86400)

        await pipe.execute()

        # Clear dirty flags and strike activity after snapshot
        for sym in self.dirty:
            self.dirty[sym].clear()

        for sym in self.strike_activity:
            for strike in self.strike_activity[sym]:
                self.strike_activity[sym][strike] = {
                    "ticks": 0, "bids": 0, "asks": 0, "calls": 0, "puts": 0
                }

        return result