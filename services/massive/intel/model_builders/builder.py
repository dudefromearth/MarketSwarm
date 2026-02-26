import json
import asyncio
import time
import re
from datetime import datetime, date, timezone, timedelta
from math import log, sqrt, exp, erf
from typing import Dict, Any, Tuple, Set

from redis.asyncio import Redis


# ============================================================
# Black-Scholes pricing with VIX-based volatility skew
# (matches Risk Graph's useRiskGraphCalculations.ts model)
# ============================================================

def _norm_cdf(x: float) -> float:
    """Standard normal CDF using math.erf (exact)."""
    return 0.5 * (1 + erf(x / sqrt(2)))


def _bs_call(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes call price."""
    if T <= 0 or sigma <= 0:
        return max(0.0, S - K)
    sqrtT = sqrt(T)
    d1 = (log(S / K) + (r + sigma * sigma / 2) * T) / (sigma * sqrtT)
    d2 = d1 - sigma * sqrtT
    return S * _norm_cdf(d1) - K * exp(-r * T) * _norm_cdf(d2)


def _bs_put(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes put price."""
    if T <= 0 or sigma <= 0:
        return max(0.0, K - S)
    sqrtT = sqrt(T)
    d1 = (log(S / K) + (r + sigma * sigma / 2) * T) / (sigma * sqrtT)
    d2 = d1 - sigma * sqrtT
    return K * exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


# Regime configs — must match MARKET_REGIMES in useRiskGraphCalculations.ts
_REGIMES = {
    "low_vol":  {"put_skew": 0.10, "call_skew": 0.02, "atm_boost": 0.0},
    "normal":   {"put_skew": 0.15, "call_skew": 0.03, "atm_boost": 0.0},
    "elevated": {"put_skew": 0.30, "call_skew": 0.05, "atm_boost": 0.0},
    "panic":    {"put_skew": 0.50, "call_skew": 0.08, "atm_boost": 0.05},
}


def _get_regime(vix: float) -> dict:
    """Determine regime from VIX level (matches frontend regime auto-detection)."""
    if vix <= 14:
        return _REGIMES["low_vol"]
    elif vix <= 18:
        return _REGIMES["normal"]
    elif vix <= 30:
        return _REGIMES["elevated"]
    else:
        return _REGIMES["panic"]


def _skewed_iv(base_iv: float, strike: float, spot: float, regime: dict) -> float:
    """
    Calculate strike-specific IV with skew — matches calculateSkewedIV() in
    useRiskGraphCalculations.ts exactly.
    """
    moneyness = (strike - spot) / spot  # negative = OTM put, positive = OTM call

    skew_adj = 0.0
    if moneyness < 0:
        # OTM put — higher IV
        skew_adj = regime["put_skew"] * abs(moneyness) * 10  # per 10% OTM
    elif moneyness > 0:
        # OTM call — slightly higher IV
        skew_adj = regime["call_skew"] * moneyness * 10

    # ATM boost — Gaussian centered at ATM
    atm_dist = abs(moneyness)
    atm_factor = exp(-atm_dist * atm_dist * 50)
    atm_adj = regime["atm_boost"] * atm_factor

    return base_iv * (1 + skew_adj + atm_adj)


_TICKER_RE = re.compile(
    r"^O:(?P<root>[A-Z]+)(?P<yymmdd>\d{6,8})(?P<cp>[CP])(?P<strike>\d+)$"
)


def _parse_expiration(yymmdd: str) -> date | None:
    """Parse YYMMDD or YYYYMMDD to date object."""
    try:
        if len(yymmdd) == 6:
            return datetime.strptime(yymmdd, "%y%m%d").date()
        elif len(yymmdd) == 8:
            return datetime.strptime(yymmdd, "%Y%m%d").date()
    except ValueError:
        return None
    return None


def _compute_dte(exp_date: date) -> int:
    """Compute days to expiration from today."""
    today = date.today()
    delta = (exp_date - today).days
    return max(0, delta)


# EST offset (UTC-5) — hardcoded to match frontend 'T16:00:00-05:00'
_EST = timezone(timedelta(hours=-5))
_MIN_T_YEARS = 1.0 / (365 * 24)   # ~1 hour floor


def _fractional_T(exp_date: date) -> float:
    """
    Compute fractional years to 4pm EST on expiration date.
    Matches frontend: new Date(expDateStr + 'T16:00:00-05:00')

    This ensures heatmap tile debits and risk graph theoretical values
    are computed with the same time-to-expiry.
    """
    now = datetime.now(timezone.utc)
    exp_close = datetime(exp_date.year, exp_date.month, exp_date.day,
                         16, 0, 0, tzinfo=_EST)
    seconds_remaining = (exp_close - now).total_seconds()
    T = seconds_remaining / (365.0 * 24 * 3600)
    return max(T, _MIN_T_YEARS)


class Builder:
    """
    Builder Worker — Geometry-driven build stage.

    NEW TRUTH:
    - Snapshot is authoritative
    - No dirty flags
    - Ticker encodes everything
    - Tiles are atomic units
    - Surfaces = (symbol, strategy, DTE)

    Supported strategies:
    - butterfly: long lower + short 2x middle + long higher
    - vertical: debit spread (long near + short far)
    - single: individual option price
    """

    STRATEGIES = ["butterfly", "vertical", "single"]

    def __init__(self, config: Dict[str, Any], logger):
        self.config = config
        self.logger = logger

        self.symbols = [
            s.strip()
            for s in config.get("MASSIVE_CHAIN_SYMBOLS", "I:SPX,I:NDX").split(",")
            if s.strip()
        ]

        # Read widths from config (comma-separated strings)
        spx_widths_str = config.get("MASSIVE_WIDTHS_SPX", "20,25,30,35,40,45,50")
        ndx_widths_str = config.get("MASSIVE_WIDTHS_NDX", "50,100,150,200")

        self.widths_map = {
            "I:SPX": [int(w.strip()) for w in spx_widths_str.split(",") if w.strip()],
            "I:NDX": [int(w.strip()) for w in ndx_widths_str.split(",") if w.strip()],
        }

        # DTEs to include in model (chain snapshot: 0-10, WS: 0-3)
        self.model_dtes: Set[int] = set(
            int(d.strip())
            for d in config.get("MASSIVE_MODEL_DTES", "0,1,2,3,4,5,6,7,8,9,10").split(",")
            if d.strip()
        )

        self.market_redis_url = config["buses"]["market-redis"]["url"]
        self._redis: Redis | None = None

        self.analytics_key = "massive:builder:analytics"

        # Previous surfaces (for diffing)
        self.previous_surfaces: Dict[str, Dict[str, Any]] = {
            sym: {} for sym in self.symbols
        }

        # Direct injection target for model publishing
        self._model_publisher = None

        self.logger.info(
            f"[BUILDER INIT] symbols={self.symbols} dtes={sorted(self.model_dtes)}",
            emoji="🧮",
        )

    def set_model_publisher(self, model_publisher) -> None:
        """Inject ModelPublisher for direct delta handoff."""
        self._model_publisher = model_publisher
        self.logger.info("[BUILDER] ModelPublisher injected", emoji="🔗")

    async def _redis_conn(self) -> Redis:
        if not self._redis:
            self._redis = Redis.from_url(
                self.market_redis_url, decode_responses=True
            )
        return self._redis

    # ============================================================
    # Entry point
    # ============================================================

    async def receive_snapshot(self, snapshots: Dict[str, Dict[str, Any]]) -> None:
        """
        Receive a full geometry snapshot from SnapshotWorker.
        """
        t_start = time.monotonic()
        r = await self._redis_conn()

        error_count = 0
        total_tiles = 0
        deltas_with_changes = 0
        deltas_empty = 0

        # Load VIX for theoretical pricing (matches Risk Graph's VIX-based model)
        vix = 0.0
        try:
            raw_vix = await r.get("massive:model:spot:I:VIX")
            if raw_vix:
                vix = float(json.loads(raw_vix).get("value", 0))
        except Exception:
            pass

        try:
            for symbol, contracts in snapshots.items():
                if symbol not in self.symbols:
                    continue

                new_surface, atm_iv = self._build_surface(symbol, contracts, vix=vix)
                delta = self._diff_surfaces(
                    self.previous_surfaces[symbol], new_surface
                )

                # Always publish to ModelPublisher, even if delta is empty
                # This ensures timestamps are updated and SSE clients see activity
                if self._model_publisher:
                    # Use empty delta if None to signal "data processed, no tile changes"
                    publish_delta = delta if delta else {"changed": {}, "removed": []}
                    # Include ATM IV metadata for risk graph consumption
                    publish_delta["atm_iv"] = atm_iv
                    await self._model_publisher.receive_delta(symbol, publish_delta)

                if delta:
                    deltas_with_changes += 1
                    self.logger.debug(
                        f"[BUILDER] Delta for {symbol} (tiles={len(delta.get('changed', {}))})",
                        emoji="📤",
                    )
                else:
                    deltas_empty += 1

                self.previous_surfaces[symbol] = new_surface
                total_tiles += len(new_surface)

        except Exception as e:
            self.logger.error(f"[BUILDER PROCESS ERROR] {e}", emoji="💥")
            error_count += 1

        latency_ms = int((time.monotonic() - t_start) * 1000)
        await r.hincrby(self.analytics_key, "runs", 1)
        await r.hset(self.analytics_key, "latency_last_ms", latency_ms)
        await r.hset(self.analytics_key, "tiles_total", total_tiles)
        await r.hincrby(self.analytics_key, "errors", error_count)
        await r.hincrby(self.analytics_key, "deltas_with_changes", deltas_with_changes)
        await r.hincrby(self.analytics_key, "deltas_empty", deltas_empty)

    # ============================================================
    # Surface / Tile construction
    # ============================================================

    def _parse_ticker(self, ticker: str) -> Tuple[int, float, str, date] | None:
        """
        Returns (dte, strike, option_type, exp_date) or None if invalid/filtered.
        """
        m = _TICKER_RE.match(ticker)
        if not m:
            return None

        strike = int(m.group("strike")) / 1000.0
        option_type = "call" if m.group("cp") == "C" else "put"

        # Compute actual DTE from expiration date
        exp_date = _parse_expiration(m.group("yymmdd"))
        if exp_date is None:
            return None

        dte = _compute_dte(exp_date)

        # Filter to configured DTEs
        if dte not in self.model_dtes:
            return None

        return dte, strike, option_type, exp_date

    def _price(self, contract: Dict[str, Any]) -> float | None:
        """Get current fair value from bid/ask midpoint, falling back to last trade."""
        lq = contract.get("last_quote", {})
        mid = lq.get("midpoint") or lq.get("mid")
        if mid is not None and mid > 0:
            return mid
        # Fallback to last trade only if no midpoint available
        last = lq.get("last")
        if last is not None and last > 0:
            return last
        return None

    def _theo_price_skew(
        self, strike: float, opt_type: str, spot: float, T: float,
        base_iv: float, regime: dict
    ) -> float:
        """
        Compute BS theoretical price using VIX-based IV with skew.
        Matches the Risk Graph's pricing model exactly.
        """
        iv = _skewed_iv(base_iv, strike, spot, regime)
        r = 0.05  # risk-free rate
        try:
            if opt_type == "call":
                return _bs_call(spot, strike, T, r, iv)
            else:
                return _bs_put(spot, strike, T, r, iv)
        except (ValueError, ZeroDivisionError):
            return max(0.0, (spot - strike) if opt_type == "call" else (strike - spot))

    def _build_surface(
        self, symbol: str, contracts: Dict[str, Any], vix: float = 0.0
    ) -> Dict[str, Any]:
        """
        Build full surface for a symbol across all DTEs.
        Surface key = f"{strategy}:{dte}:{width}:{strike}"

        Uses VIX-based BS pricing with volatility skew to match the
        Risk Graph's theoretical values exactly.
        """
        widths = self.widths_map.get(symbol, [])

        # Index contracts by (dte, strike, type)
        # Structure: by_dte_strike[dte][strike][type] = payload
        by_dte_strike: Dict[int, Dict[float, Dict[str, Dict[str, Any]]]] = {}
        # Map DTE → expiration date for fractional T computation
        dte_exp_date: Dict[int, date] = {}

        for ticker, payload in contracts.items():
            parsed = self._parse_ticker(ticker)
            if parsed is None:
                continue

            dte, strike, opt_type, exp_date = parsed
            by_dte_strike.setdefault(dte, {}).setdefault(strike, {})[opt_type] = payload
            dte_exp_date[dte] = exp_date

        surface: Dict[str, Any] = {}

        # Extract spot price from any contract's underlying_asset
        spot = 0.0
        for payload in contracts.values():
            ua = payload.get("underlying_asset", {})
            v = ua.get("value")
            if v and v > 0:
                spot = v
                break

        # Theoretical pricing using chain ATM IV (per-DTE) with skew
        regime = _get_regime(vix) if vix > 0 else _REGIMES["normal"]
        use_theo = spot > 0

        # Compute ATM IV from chain per-contract IV for each DTE.
        # This replaces VIX as base IV — actual chain IV is more accurate,
        # especially for 0DTE where VIX (30-day measure) diverges significantly.
        atm_iv_by_dte: Dict[int, float] = {}
        fallback_iv = max(5.0, vix) / 100.0 if vix > 0 else 0.20
        for dte_key, by_strike in by_dte_strike.items():
            iv_samples = []
            for strike, types in by_strike.items():
                if spot > 0 and abs(strike - spot) < 30:  # within 30 pts of ATM
                    for opt_type, payload in types.items():
                        iv = payload.get("implied_volatility")
                        if iv and 0.01 < iv < 5.0:  # sanity bounds
                            iv_samples.append(iv)
            if iv_samples:
                atm_iv_by_dte[dte_key] = sum(iv_samples) / len(iv_samples)
            else:
                atm_iv_by_dte[dte_key] = fallback_iv

        # Build tiles for each DTE
        for dte in sorted(by_dte_strike.keys()):
            by_strike = by_dte_strike[dte]

            # Per-DTE base IV from chain ATM (falls back to VIX-based)
            base_iv = atm_iv_by_dte.get(dte, fallback_iv)

            # Fractional time to 4pm EST close (matches frontend Risk Graph)
            # Uses actual expiration date → precise T, not integer-day approximation
            exp_d = dte_exp_date.get(dte)
            T = _fractional_T(exp_d) if exp_d else max(dte / 365.0, _MIN_T_YEARS)

            # Strike-level pricing helper
            def call_price(K: float) -> float:
                if use_theo:
                    return self._theo_price_skew(K, "call", spot, T, base_iv, regime)
                return 0.0

            def put_price(K: float) -> float:
                if use_theo:
                    return self._theo_price_skew(K, "put", spot, T, base_iv, regime)
                return 0.0

            for strike in sorted(by_strike.keys()):
                center = strike

                # ========== SINGLES ==========
                call_contract = by_strike.get(center, {}).get("call")
                put_contract = by_strike.get(center, {}).get("put")

                if call_contract or put_contract:
                    tile_key = f"single:{dte}:0:{int(center)}"
                    tile = {
                        "symbol": symbol,
                        "strategy": "single",
                        "dte": dte,
                        "strike": center,
                        "width": 0,
                    }
                    if call_contract:
                        call_entry: Dict[str, Any] = {}
                        if use_theo:
                            call_entry["mid"] = call_price(center)
                        call_market = self._price(call_contract)
                        if call_market is not None:
                            call_entry["market_mid"] = call_market
                        elif not use_theo:
                            call_entry["mid"] = call_market  # type: ignore[assignment]
                        if call_entry:
                            tile["call"] = call_entry
                    if put_contract:
                        put_entry: Dict[str, Any] = {}
                        if use_theo:
                            put_entry["mid"] = put_price(center)
                        put_market = self._price(put_contract)
                        if put_market is not None:
                            put_entry["market_mid"] = put_market
                        elif not use_theo:
                            put_entry["mid"] = put_market  # type: ignore[assignment]
                        if put_entry:
                            tile["put"] = put_entry

                    if "call" in tile or "put" in tile:
                        surface[tile_key] = tile

                # ========== WIDTH-BASED STRATEGIES ==========
                for width in widths:
                    low = center - width
                    high = center + width

                    lc = by_strike.get(low, {}).get("call")
                    cc = by_strike.get(center, {}).get("call")
                    hc = by_strike.get(high, {}).get("call")

                    lp = by_strike.get(low, {}).get("put")
                    cp = by_strike.get(center, {}).get("put")
                    hp = by_strike.get(high, {}).get("put")

                    # ========== BUTTERFLY ==========
                    if all([lc, cc, hc, lp, cp, hp]):
                        call_debit = (
                            call_price(low)
                            - 2 * call_price(center)
                            + call_price(high)
                        )
                        put_debit = (
                            put_price(high)
                            - 2 * put_price(center)
                            + put_price(low)
                        )

                        # Market midpoint debit from bid/ask
                        lc_m = self._price(lc)
                        cc_m = self._price(cc)
                        hc_m = self._price(hc)
                        lp_m = self._price(lp)
                        cp_m = self._price(cp)
                        hp_m = self._price(hp)

                        call_market_debit = None
                        if lc_m is not None and cc_m is not None and hc_m is not None:
                            call_market_debit = lc_m - 2 * cc_m + hc_m

                        put_market_debit = None
                        if hp_m is not None and cp_m is not None and lp_m is not None:
                            put_market_debit = hp_m - 2 * cp_m + lp_m

                        tile_key = f"butterfly:{dte}:{width}:{int(center)}"
                        call_tile: Dict[str, Any] = {
                            "debit": call_debit,
                            "max_profit": width - call_debit,
                            "max_loss": call_debit,
                        }
                        if call_market_debit is not None:
                            call_tile["market_debit"] = call_market_debit

                        put_tile: Dict[str, Any] = {
                            "debit": put_debit,
                            "max_profit": width - put_debit,
                            "max_loss": put_debit,
                        }
                        if put_market_debit is not None:
                            put_tile["market_debit"] = put_market_debit

                        surface[tile_key] = {
                            "symbol": symbol,
                            "strategy": "butterfly",
                            "dte": dte,
                            "strike": center,
                            "width": width,
                            "call": call_tile,
                            "put": put_tile,
                        }

                    # ========== VERTICAL (Call) ==========
                    # Long call at center, short call at center + width
                    if cc and hc:
                        debit = call_price(center) - call_price(high)
                        tile_key = f"vertical:{dte}:{width}:{int(center)}"

                        if tile_key not in surface:
                            surface[tile_key] = {
                                "symbol": symbol,
                                "strategy": "vertical",
                                "dte": dte,
                                "strike": center,
                                "width": width,
                            }

                        vert_call: Dict[str, Any] = {
                            "debit": debit,
                            "max_profit": width - debit,
                            "max_loss": debit,
                        }
                        cc_m = self._price(cc)
                        hc_m = self._price(hc)
                        if cc_m is not None and hc_m is not None:
                            vert_call["market_debit"] = cc_m - hc_m

                        surface[tile_key]["call"] = vert_call

                    # ========== VERTICAL (Put) ==========
                    # Long put at center, short put at center - width
                    if cp and lp:
                        debit = put_price(center) - put_price(low)
                        tile_key = f"vertical:{dte}:{width}:{int(center)}"

                        if tile_key not in surface:
                            surface[tile_key] = {
                                "symbol": symbol,
                                "strategy": "vertical",
                                "dte": dte,
                                "strike": center,
                                "width": width,
                            }

                        vert_put: Dict[str, Any] = {
                            "debit": debit,
                            "max_profit": width - debit,
                            "max_loss": debit,
                        }
                        cp_m = self._price(cp)
                        lp_m = self._price(lp)
                        if cp_m is not None and lp_m is not None:
                            vert_put["market_debit"] = cp_m - lp_m

                        surface[tile_key]["put"] = vert_put

        return surface, atm_iv_by_dte

    # ============================================================
    # Diffing
    # ============================================================

    def _diff_surfaces(
        self,
        old: Dict[str, Any],
        new: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        """
        Tile-level diff. Returns changed tiles and removed keys.
        Returns None if no changes.
        """
        changed = {}
        removed = []

        # Find changed/added tiles
        for key, tile in new.items():
            if old.get(key) != tile:
                changed[key] = tile

        # Find removed tiles
        for key in old:
            if key not in new:
                removed.append(key)

        if not changed and not removed:
            return None

        return {"changed": changed, "removed": removed}

    # ============================================================
    # Lifecycle
    # ============================================================

    async def run(self, stop_event: asyncio.Event) -> None:
        self.logger.info("[BUILDER START] running", emoji="🧮")
        await stop_event.wait()
        self.logger.info("[BUILDER STOP] halted", emoji="🛑")