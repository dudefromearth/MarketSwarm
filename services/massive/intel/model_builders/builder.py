import json
import asyncio
import time
import re
from datetime import datetime, date
from math import log, sqrt, exp, erf
from typing import Dict, Any, Tuple, Set

from redis.asyncio import Redis


# ============================================================
# Black-Scholes pricing (for theoretical tile values)
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

        try:
            for symbol, contracts in snapshots.items():
                if symbol not in self.symbols:
                    continue

                new_surface = self._build_surface(symbol, contracts)
                delta = self._diff_surfaces(
                    self.previous_surfaces[symbol], new_surface
                )

                # Always publish to ModelPublisher, even if delta is empty
                # This ensures timestamps are updated and SSE clients see activity
                if self._model_publisher:
                    # Use empty delta if None to signal "data processed, no tile changes"
                    publish_delta = delta if delta else {"changed": {}, "removed": []}
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

    def _parse_ticker(self, ticker: str) -> Tuple[int, float, str] | None:
        """
        Returns (dte, strike, option_type) or None if invalid/filtered.
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

        return dte, strike, option_type

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

    def _theo_price(self, contract: Dict[str, Any], spot: float, T: float) -> float | None:
        """
        Compute BS theoretical price using per-contract implied volatility.
        Falls back to midpoint if IV is unavailable.
        """
        iv = contract.get("implied_volatility")
        details = contract.get("details", {})
        strike = details.get("strike_price")
        contract_type = details.get("contract_type")

        if iv is None or iv <= 0 or strike is None or spot <= 0:
            return self._price(contract)

        r = 0.05  # risk-free rate
        try:
            if contract_type == "call":
                return _bs_call(spot, strike, T, r, iv)
            elif contract_type == "put":
                return _bs_put(spot, strike, T, r, iv)
        except (ValueError, ZeroDivisionError):
            pass

        return self._price(contract)

    def _build_surface(
        self, symbol: str, contracts: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build full surface for a symbol across all DTEs.
        Surface key = f"{strategy}:{dte}:{width}:{strike}"

        Strategies:
        - butterfly: long lower + short 2x middle + long higher
        - vertical: debit spread (long strike, short strike+width for calls; long strike, short strike-width for puts)
        - single: individual option mid price
        """
        widths = self.widths_map.get(symbol, [])

        # Index contracts by (dte, strike, type)
        # Structure: by_dte_strike[dte][strike][type] = payload
        by_dte_strike: Dict[int, Dict[float, Dict[str, Dict[str, Any]]]] = {}

        for ticker, payload in contracts.items():
            parsed = self._parse_ticker(ticker)
            if parsed is None:
                continue

            dte, strike, opt_type = parsed
            by_dte_strike.setdefault(dte, {}).setdefault(strike, {})[opt_type] = payload

        surface: Dict[str, Any] = {}

        # Extract spot price from any contract's underlying_asset
        spot = 0.0
        for payload in contracts.values():
            ua = payload.get("underlying_asset", {})
            v = ua.get("value")
            if v and v > 0:
                spot = v
                break

        # Build tiles for each DTE
        for dte in sorted(by_dte_strike.keys()):
            by_strike = by_dte_strike[dte]

            # Time to expiry in years (floor at ~1 trading hour for 0-DTE)
            T = max(dte / 365.0, 1.0 / (365 * 24))

            # Pricing helper: use BS+IV when spot available, else midpoint
            def price(contract):
                if spot > 0:
                    return self._theo_price(contract, spot, T)
                return self._price(contract)

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
                        call_mid = price(call_contract)
                        if call_mid is not None:
                            tile["call"] = {"mid": call_mid}
                    if put_contract:
                        put_mid = price(put_contract)
                        if put_mid is not None:
                            tile["put"] = {"mid": put_mid}

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
                            price(lc)
                            - 2 * price(cc)
                            + price(hc)
                        )
                        put_debit = (
                            price(lp)
                            - 2 * price(cp)
                            + price(hp)
                        )

                        if call_debit is not None and put_debit is not None:
                            tile_key = f"butterfly:{dte}:{width}:{int(center)}"
                            surface[tile_key] = {
                                "symbol": symbol,
                                "strategy": "butterfly",
                                "dte": dte,
                                "strike": center,
                                "width": width,
                                "call": {
                                    "debit": call_debit,
                                    "max_profit": width - call_debit,
                                    "max_loss": call_debit,
                                },
                                "put": {
                                    "debit": put_debit,
                                    "max_profit": width - put_debit,
                                    "max_loss": put_debit,
                                },
                            }

                    # ========== VERTICAL (Call) ==========
                    # Long call at center, short call at center + width
                    if cc and hc:
                        long_mid = price(cc)
                        short_mid = price(hc)
                        if long_mid is not None and short_mid is not None:
                            debit = long_mid - short_mid
                            tile_key = f"vertical:{dte}:{width}:{int(center)}"

                            if tile_key not in surface:
                                surface[tile_key] = {
                                    "symbol": symbol,
                                    "strategy": "vertical",
                                    "dte": dte,
                                    "strike": center,
                                    "width": width,
                                }

                            surface[tile_key]["call"] = {
                                "debit": debit,
                                "max_profit": width - debit,
                                "max_loss": debit,
                            }

                    # ========== VERTICAL (Put) ==========
                    # Long put at center, short put at center - width
                    if cp and lp:
                        long_mid = price(cp)
                        short_mid = price(lp)
                        if long_mid is not None and short_mid is not None:
                            debit = long_mid - short_mid
                            tile_key = f"vertical:{dte}:{width}:{int(center)}"

                            if tile_key not in surface:
                                surface[tile_key] = {
                                    "symbol": symbol,
                                    "strategy": "vertical",
                                    "dte": dte,
                                    "strike": center,
                                    "width": width,
                                }

                            surface[tile_key]["put"] = {
                                "debit": debit,
                                "max_profit": width - debit,
                                "max_loss": debit,
                            }

        return surface

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