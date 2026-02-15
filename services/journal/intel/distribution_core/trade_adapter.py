"""
Distribution Core v1.0.0 — Trade Adapter

Bridges journal Trade objects → Distribution Core TradeRecord objects.

Handles:
    - Cents → dollars conversion (planned_risk, pnl)
    - Null field skipping (trades without risk data are excluded)
    - Strategy mapping (journal strategy string → StrategyCategory enum)
    - Session bucket inference from entry time hour
    - Sensible defaults for fields not yet captured in journal schema

Phase 1 defaults (safe — these fields don't affect CII computation):
    - regime_bucket: GOLDILOCKS_1 (Phase 2 adds VIX lookup at entry time)
    - price_zone: INSIDE_CONVEX_BAND (Phase 0 capture only)
    - outcome_type: Derived from r_multiple sign
    - structure_signature: Derived from strategy + side + width
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from .models import (
    TradeRecord,
    StrategyCategory,
    RegimeBucket,
    SessionBucket,
    PriceZone,
    OutcomeType,
)

if TYPE_CHECKING:
    from services.journal.intel.models_v2 import Trade


# Strategy string → StrategyCategory mapping
# Journal uses: single, vertical, butterfly, iron_condor, iron_butterfly,
#               straddle, strangle, ratio_spread, custom
_STRATEGY_MAP: dict[str, StrategyCategory] = {
    "butterfly": StrategyCategory.CONVEX_EXPANSION,
    "iron_butterfly": StrategyCategory.EVENT_COMPRESSION,
    "single": StrategyCategory.CONVEX_EXPANSION,
    "vertical": StrategyCategory.PREMIUM_COLLECTION,
    "iron_condor": StrategyCategory.PREMIUM_COLLECTION,
    "straddle": StrategyCategory.PREMIUM_COLLECTION,
    "strangle": StrategyCategory.PREMIUM_COLLECTION,
    "ratio_spread": StrategyCategory.PREMIUM_COLLECTION,
    "custom": StrategyCategory.CONVEX_EXPANSION,
}

_DEFAULT_STRATEGY = StrategyCategory.CONVEX_EXPANSION


def _parse_timestamp(iso_str: str) -> datetime:
    """Parse ISO 8601 string to timezone-aware UTC datetime."""
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _infer_session_bucket(entry_time_str: str) -> SessionBucket:
    """Infer session bucket from entry time hour (ET approximation).

    < 12:00 UTC (roughly morning ET) → MORNING
    < 19:00 UTC (roughly afternoon ET) → AFTERNOON
    else → CLOSING

    Note: This is approximate. Phase 2 adds proper ET conversion.
    """
    try:
        dt = _parse_timestamp(entry_time_str)
        hour = dt.hour
        if hour < 16:  # Before noon ET (assuming ~4hr offset)
            return SessionBucket.MORNING
        elif hour < 19:  # Before 3pm ET
            return SessionBucket.AFTERNOON
        else:
            return SessionBucket.CLOSING
    except (ValueError, AttributeError):
        return SessionBucket.MORNING


def _map_strategy(strategy_str: str) -> StrategyCategory:
    """Map journal strategy string to StrategyCategory enum."""
    return _STRATEGY_MAP.get(strategy_str.lower(), _DEFAULT_STRATEGY)


def _build_signature(trade: "Trade") -> str:
    """Build structure signature from trade geometry."""
    width = trade.width if trade.width else "w0"
    return f"{trade.strategy}_{trade.side}_{width}"


def adapt_trade(trade: "Trade") -> TradeRecord | None:
    """Convert a single journal Trade to a TradeRecord.

    Returns None if the trade is missing required fields:
        - exit_time (must be closed)
        - planned_risk (must have defined risk > 0)
        - pnl (must have realized P&L)
        - r_multiple (must have computed R)
    """
    # Skip incomplete trades
    if not trade.exit_time:
        return None
    if not trade.planned_risk or trade.planned_risk <= 0:
        return None
    if trade.pnl is None:
        return None
    if trade.r_multiple is None:
        return None

    # Cents → dollars
    risk_unit = trade.planned_risk / 100.0
    pnl_realized = trade.pnl / 100.0
    r_multiple = trade.r_multiple

    # Outcome from R sign
    outcome = (
        OutcomeType.STRUCTURAL_WIN if r_multiple >= 0
        else OutcomeType.STRUCTURAL_LOSS
    )

    try:
        return TradeRecord(
            trade_id=trade.id,
            strategy_category=_map_strategy(trade.strategy),
            structure_signature=_build_signature(trade),
            entry_timestamp=_parse_timestamp(trade.entry_time),
            exit_timestamp=_parse_timestamp(trade.exit_time),
            risk_unit=risk_unit,
            pnl_realized=pnl_realized,
            r_multiple=r_multiple,
            regime_bucket=RegimeBucket.GOLDILOCKS_1,  # Phase 2: VIX lookup
            session_bucket=_infer_session_bucket(trade.entry_time),
            price_zone=PriceZone.INSIDE_CONVEX_BAND,  # Phase 0 capture only
            outcome_type=outcome,
        )
    except (ValueError, TypeError):
        # TradeRecord validation failure (e.g., r_multiple mismatch)
        return None


def adapt_trades(trades: list["Trade"]) -> list[TradeRecord]:
    """Convert a list of journal Trades to TradeRecords.

    Skips trades missing required fields. Returns only valid records.
    """
    records = []
    for trade in trades:
        record = adapt_trade(trade)
        if record is not None:
            records.append(record)
    return records
