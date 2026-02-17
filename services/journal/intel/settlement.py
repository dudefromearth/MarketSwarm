# services/journal/intel/settlement.py
"""Deterministic settlement for expired options trades.

Fetches underlying close prices from Polygon and computes intrinsic value
at expiration. Pure computation + price fetch — no DB access, no HTTP server.

Daily close is used as proxy for option expiration settlement. For index options
(SPX), official settlement price may differ (SOQ, early settlement, holiday-adjusted
dates). Acceptable for simulator realism; not authoritative for real brokerage
reconciliation.
"""

import json
import logging
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

POLYGON_BASE = "https://api.polygon.io"


def fetch_underlying_close(ticker: str, date_str: str, api_key: str) -> Optional[float]:
    """Fetch daily close price from Polygon as settlement proxy.

    Args:
        ticker: Polygon ticker symbol (e.g. "I:SPX", "SPY")
        date_str: Date string "YYYY-MM-DD"
        api_key: Polygon API key

    Returns:
        Close price in dollars, or None if unavailable.
    """
    # Polygon uses URL-encoded tickers for indices
    encoded_ticker = urllib.request.quote(ticker, safe='')
    url = (
        f"{POLYGON_BASE}/v2/aggs/ticker/{encoded_ticker}/range/1/day/"
        f"{date_str}/{date_str}?apiKey={api_key}&limit=1"
    )
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'MarketSwarm/1.0')
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode())
            if data.get("resultsCount", 0) > 0:
                return data["results"][0]["c"]  # close price
    except (urllib.error.URLError, json.JSONDecodeError, KeyError, IndexError) as e:
        logger.warning(f"Polygon fetch failed for {ticker} on {date_str}: {e}")
    return None


def compute_intrinsic(strategy: str, side: str, strike: float,
                      width: Optional[int], spot: float) -> float:
    """Compute option intrinsic value at expiration.

    Args:
        strategy: 'butterfly', 'vertical', or 'single'
        side: 'call' or 'put'
        strike: Strike price (center for butterfly, long strike for vertical)
        width: Wing distance for butterfly, spread width for vertical
        spot: Underlying price at expiration

    Returns:
        Intrinsic value in dollars (points).
    """
    if strategy in ('butterfly', 'iron_butterfly') and not width:
        return 0.0

    if strategy in ('butterfly', 'iron_butterfly'):
        # Symmetric butterfly: strike=center, width=wing distance
        # Max payoff = width, at strike. Zero beyond wings.
        # Reused from trade_selector.py:1542-1561
        distance = abs(spot - strike)
        if distance >= width:
            return 0.0
        return width - distance

    elif strategy in ('vertical', 'iron_condor'):
        if not width:
            return 0.0
        if side == 'call':
            # Bull call spread: long lower, short higher
            return max(0.0, min(width, spot - strike))
        else:
            # Bear put spread: long higher, short lower
            return max(0.0, min(width, strike - spot))

    else:
        # Single-leg option
        if side == 'call':
            return max(0.0, spot - strike)
        else:
            return max(0.0, strike - spot)


@dataclass
class SettlementResult:
    """Result of a settlement computation."""
    available: bool
    exit_price_cents: Optional[int] = None  # cents, compatible with close_trade()
    exit_spot: Optional[float] = None       # underlying close in dollars
    source: str = 'expiration_intrinsic'
    error: Optional[str] = None


def compute_settlement(trade, api_key: str, price_cache: dict = None) -> SettlementResult:
    """Compute deterministic settlement for an expired trade.

    Args:
        trade: Trade object with expiration_date, underlying, strategy, side, strike, width
        api_key: Polygon API key
        price_cache: Optional dict for caching {ticker:date -> price} across calls

    Returns:
        SettlementResult with exit_price_cents if settlement data available.
    """
    if not trade.expiration_date or not trade.underlying:
        return SettlementResult(
            available=False,
            error='missing expiration_date or underlying'
        )

    # Extract date — handle both ISO string and datetime object
    if isinstance(trade.expiration_date, str):
        exp_date = trade.expiration_date[:10]  # "2025-01-17"
    else:
        exp_date = trade.expiration_date.strftime("%Y-%m-%d")

    # Check cache first (multiple trades may share same underlying+date)
    cache_key = f"{trade.underlying}:{exp_date}"
    if price_cache is not None and cache_key in price_cache:
        spot = price_cache[cache_key]
    else:
        spot = fetch_underlying_close(trade.underlying, exp_date, api_key)
        if price_cache is not None:
            price_cache[cache_key] = spot

    if spot is None:
        return SettlementResult(
            available=False,
            error=f'no price data for {trade.underlying} on {exp_date}'
        )

    # Compute intrinsic value (dollars/points)
    intrinsic = compute_intrinsic(
        strategy=trade.strategy,
        side=trade.side,
        strike=trade.strike,
        width=trade.width,
        spot=spot
    )

    # Convert to cents (entry_price is stored in cents)
    exit_price_cents = round(intrinsic * 100)

    return SettlementResult(
        available=True,
        exit_price_cents=exit_price_cents,
        exit_spot=spot,
        source='expiration_intrinsic'
    )
