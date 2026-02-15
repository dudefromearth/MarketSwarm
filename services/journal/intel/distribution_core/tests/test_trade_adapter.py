"""Trade adapter unit tests — Journal Trade → TradeRecord conversion."""

import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List

import pytest

# Minimal Trade stub matching journal models_v2.Trade fields
@dataclass
class TradeFake:
    id: str = "test-001"
    log_id: str = "log-001"
    symbol: str = "SPX"
    underlying: str = "I:SPX"
    strategy: str = "butterfly"
    side: str = "call"
    strike: float = 5800.0
    width: Optional[int] = 25
    dte: Optional[int] = 7
    quantity: int = 1
    entry_time: str = "2026-02-10T14:30:00"
    entry_price: int = 350  # cents
    entry_spot: Optional[float] = 5800.0
    entry_iv: Optional[float] = None
    exit_time: Optional[str] = "2026-02-12T15:00:00"
    exit_price: Optional[int] = 500  # cents
    exit_spot: Optional[float] = 5810.0
    planned_risk: Optional[int] = 350  # cents
    max_profit: Optional[int] = None
    max_loss: Optional[int] = None
    pnl: Optional[int] = 150  # cents
    r_multiple: Optional[float] = None
    status: str = "closed"
    entry_mode: str = "instant"
    immutable_at: Optional[str] = None
    notes: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    source: str = "manual"
    playbook_id: Optional[str] = None
    created_at: str = "2026-02-10T14:30:00"
    updated_at: str = "2026-02-12T15:00:00"

    def __post_init__(self):
        # Auto-compute r_multiple like journal does
        if self.r_multiple is None and self.pnl is not None and self.planned_risk and self.planned_risk > 0:
            self.r_multiple = self.pnl / self.planned_risk


from ..trade_adapter import adapt_trade, adapt_trades, _map_strategy, _infer_session_bucket
from ..models import StrategyCategory, SessionBucket, OutcomeType


class TestAdaptTrade:
    def test_valid_trade(self):
        t = TradeFake()
        record = adapt_trade(t)
        assert record is not None
        assert record.trade_id == "test-001"
        assert record.risk_unit == pytest.approx(3.50)  # 350 cents → $3.50
        assert record.pnl_realized == pytest.approx(1.50)  # 150 cents → $1.50
        assert record.r_multiple == pytest.approx(150 / 350)

    def test_skip_no_exit(self):
        t = TradeFake(exit_time=None)
        assert adapt_trade(t) is None

    def test_skip_no_planned_risk(self):
        t = TradeFake(planned_risk=None)
        assert adapt_trade(t) is None

    def test_skip_zero_planned_risk(self):
        t = TradeFake(planned_risk=0)
        assert adapt_trade(t) is None

    def test_skip_no_pnl(self):
        t = TradeFake(pnl=None, r_multiple=0.5)
        assert adapt_trade(t) is None

    def test_skip_no_r_multiple(self):
        t = TradeFake(pnl=100, r_multiple=None, planned_risk=None)
        assert adapt_trade(t) is None

    def test_winner_outcome(self):
        t = TradeFake(pnl=100, planned_risk=200)
        record = adapt_trade(t)
        assert record.outcome_type == OutcomeType.STRUCTURAL_WIN

    def test_loser_outcome(self):
        t = TradeFake(pnl=-200, planned_risk=200)
        record = adapt_trade(t)
        assert record.outcome_type == OutcomeType.STRUCTURAL_LOSS

    def test_zero_pnl_is_win(self):
        t = TradeFake(pnl=0, planned_risk=200)
        record = adapt_trade(t)
        assert record.outcome_type == OutcomeType.STRUCTURAL_WIN

    def test_structure_signature(self):
        t = TradeFake(strategy="butterfly", side="call", width=25)
        record = adapt_trade(t)
        assert record.structure_signature == "butterfly_call_25"

    def test_structure_signature_no_width(self):
        t = TradeFake(strategy="single", side="call", width=None)
        record = adapt_trade(t)
        assert record.structure_signature == "single_call_w0"

    def test_cents_to_dollars(self):
        t = TradeFake(planned_risk=10000, pnl=5000)  # $100 risk, $50 pnl
        record = adapt_trade(t)
        assert record.risk_unit == pytest.approx(100.0)
        assert record.pnl_realized == pytest.approx(50.0)


class TestStrategyMapping:
    def test_butterfly(self):
        assert _map_strategy("butterfly") == StrategyCategory.CONVEX_EXPANSION

    def test_iron_butterfly(self):
        assert _map_strategy("iron_butterfly") == StrategyCategory.EVENT_COMPRESSION

    def test_vertical(self):
        assert _map_strategy("vertical") == StrategyCategory.PREMIUM_COLLECTION

    def test_iron_condor(self):
        assert _map_strategy("iron_condor") == StrategyCategory.PREMIUM_COLLECTION

    def test_unknown_defaults(self):
        assert _map_strategy("exotic_thing") == StrategyCategory.CONVEX_EXPANSION


class TestSessionBucket:
    def test_morning(self):
        assert _infer_session_bucket("2026-02-10T14:30:00") == SessionBucket.MORNING

    def test_afternoon(self):
        assert _infer_session_bucket("2026-02-10T17:00:00") == SessionBucket.AFTERNOON

    def test_closing(self):
        assert _infer_session_bucket("2026-02-10T20:00:00") == SessionBucket.CLOSING


class TestAdaptTrades:
    def test_filters_invalid(self):
        trades = [
            TradeFake(id="good", pnl=100, planned_risk=200),
            TradeFake(id="no_exit", exit_time=None, pnl=100, planned_risk=200),
            TradeFake(id="no_risk", pnl=100, planned_risk=None),
            TradeFake(id="also_good", pnl=-50, planned_risk=100),
        ]
        records = adapt_trades(trades)
        assert len(records) == 2
        assert records[0].trade_id == "good"
        assert records[1].trade_id == "also_good"
