"""
Distribution Core v1.0.0 — Unit Tests

≥10 test cases covering:
    - Model validation
    - Metric computations (skew, LTC, ROCPR, kurtosis, tails)
    - Regime classification
    - Window filtering
    - Normalization + CII
    - Drawdown (UCSP)
    - Versioning
    - Deterministic replay
    - Edge cases (empty, single trade, all winners, all losers)
    - End-to-end integration

All tests use deterministic data. No randomness. No IO.
"""

import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from .. import (
    compute_distribution_metrics,
    compute_regime_segmented_metrics,
    compute_strategy_mix,
)
from ..models import (
    StrategyCategory,
    RegimeBucket,
    SessionBucket,
    PriceZone,
    OutcomeType,
    RollingWindow,
    TradeRecord,
    DrawdownProfile,
    NormalizationBounds,
)
from ..metric_engine import MetricEngine
from ..regime_engine import RegimeEngine, VIX_ZOMBIELAND_CEILING
from ..window_engine import WindowEngine
from ..normalization_engine import NormalizationEngine
from ..drawdown_engine import DrawdownEngine
from ..versioning import MetricVersion, VersionedBundle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_TIME = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_trade(
    idx: int,
    r_multiple: float,
    risk_unit: float = 100.0,
    days_offset: int = 0,
    regime: RegimeBucket = RegimeBucket.GOLDILOCKS_1,
    strategy: StrategyCategory = StrategyCategory.CONVEX_EXPANSION,
) -> TradeRecord:
    """Factory for deterministic test trades."""
    pnl = r_multiple * risk_unit
    entry = BASE_TIME + timedelta(days=days_offset, hours=-1)
    exit_ts = BASE_TIME + timedelta(days=days_offset)
    outcome = (
        OutcomeType.STRUCTURAL_WIN if r_multiple >= 0
        else OutcomeType.STRUCTURAL_LOSS
    )
    return TradeRecord(
        trade_id=f"test_{idx}",
        strategy_category=strategy,
        structure_signature="test_sig",
        entry_timestamp=entry,
        exit_timestamp=exit_ts,
        risk_unit=risk_unit,
        pnl_realized=pnl,
        r_multiple=r_multiple,
        regime_bucket=regime,
        session_bucket=SessionBucket.MORNING,
        price_zone=PriceZone.INSIDE_CONVEX_BAND,
        outcome_type=outcome,
    )


def _make_trade_set(r_multiples: list[float], **kwargs) -> list[TradeRecord]:
    """Create a list of trades from R-multiples."""
    return [_make_trade(i, r, days_offset=i, **kwargs) for i, r in enumerate(r_multiples)]


def _make_recent_trade_set(r_multiples: list[float], **kwargs) -> list[TradeRecord]:
    """Create trades with recent timestamps (for integration tests using live WindowEngine)."""
    now = datetime.now(timezone.utc)
    base = now - timedelta(days=len(r_multiples))
    trades = []
    for i, r in enumerate(r_multiples):
        pnl = r * kwargs.get("risk_unit", 100.0)
        entry = base + timedelta(days=i, hours=-1)
        exit_ts = base + timedelta(days=i)
        outcome = (
            OutcomeType.STRUCTURAL_WIN if r >= 0
            else OutcomeType.STRUCTURAL_LOSS
        )
        trades.append(TradeRecord(
            trade_id=f"recent_{i}",
            strategy_category=kwargs.get("strategy", StrategyCategory.CONVEX_EXPANSION),
            structure_signature="test_sig",
            entry_timestamp=entry,
            exit_timestamp=exit_ts,
            risk_unit=kwargs.get("risk_unit", 100.0),
            pnl_realized=pnl,
            r_multiple=r,
            regime_bucket=kwargs.get("regime", RegimeBucket.GOLDILOCKS_1),
            session_bucket=SessionBucket.MORNING,
            price_zone=PriceZone.INSIDE_CONVEX_BAND,
            outcome_type=outcome,
        ))
    return trades


# ---------------------------------------------------------------------------
# 1. Model Validation
# ---------------------------------------------------------------------------

class TestModels:
    def test_trade_record_valid(self):
        """Valid trade creates without error."""
        t = _make_trade(0, 1.5)
        assert t.r_multiple == 1.5
        assert t.risk_unit == 100.0
        assert t.pnl_realized == 150.0

    def test_trade_record_negative_risk(self):
        """risk_unit <= 0 must raise ValueError."""
        with pytest.raises(ValueError, match="risk_unit must be > 0"):
            TradeRecord(
                trade_id="bad",
                strategy_category=StrategyCategory.CONVEX_EXPANSION,
                structure_signature="sig",
                entry_timestamp=BASE_TIME,
                exit_timestamp=BASE_TIME,
                risk_unit=-1.0,
                pnl_realized=100.0,
                r_multiple=-100.0,
                regime_bucket=RegimeBucket.ZOMBIELAND,
                session_bucket=SessionBucket.MORNING,
                price_zone=PriceZone.INSIDE_CONVEX_BAND,
                outcome_type=OutcomeType.STRUCTURAL_WIN,
            )

    def test_trade_record_r_multiple_mismatch(self):
        """r_multiple inconsistent with pnl/risk must raise ValueError."""
        with pytest.raises(ValueError, match="r_multiple mismatch"):
            TradeRecord(
                trade_id="bad",
                strategy_category=StrategyCategory.CONVEX_EXPANSION,
                structure_signature="sig",
                entry_timestamp=BASE_TIME,
                exit_timestamp=BASE_TIME,
                risk_unit=100.0,
                pnl_realized=150.0,
                r_multiple=2.0,  # should be 1.5
                regime_bucket=RegimeBucket.ZOMBIELAND,
                session_bucket=SessionBucket.MORNING,
                price_zone=PriceZone.INSIDE_CONVEX_BAND,
                outcome_type=OutcomeType.STRUCTURAL_WIN,
            )


# ---------------------------------------------------------------------------
# 2. Metric Engine
# ---------------------------------------------------------------------------

class TestMetricEngine:
    def setup_method(self):
        self.eng = MetricEngine()

    def test_empty_trades_returns_none(self):
        """All metric methods return None for empty input."""
        assert self.eng.compute_skew([]) is None
        assert self.eng.compute_excess_kurtosis([]) is None
        assert self.eng.compute_ltc([]) is None
        assert self.eng.compute_rocpr([]) is None
        assert self.eng.compute_tail_contribution([]) is None
        assert self.eng.compute_tail_ratio([]) is None
        w, l, r = self.eng.compute_avg_winner_loser([])
        assert (w, l, r) == (None, None, None)

    def test_skew_symmetric(self):
        """Symmetric distribution has ~0 skew."""
        trades = _make_trade_set([1.0, -1.0, 0.5, -0.5, 0.25, -0.25])
        skew = self.eng.compute_skew(trades)
        assert abs(skew) < 0.01

    def test_skew_positive(self):
        """Right-skewed distribution has positive skew."""
        # Many small losses, one big win
        trades = _make_trade_set([-0.5, -0.5, -0.5, -0.5, -0.5, 5.0])
        skew = self.eng.compute_skew(trades)
        assert skew > 0

    def test_ltc_all_contained(self):
        """All losses within 1R → LTC = 1.0."""
        trades = _make_trade_set([1.0, -0.5, -0.8, -1.0, 2.0])
        ltc = self.eng.compute_ltc(trades)
        assert ltc == 1.0

    def test_ltc_some_uncontained(self):
        """Some losses > 1R → LTC < 1.0."""
        trades = _make_trade_set([1.0, -0.5, -1.5, -2.0, 2.0])
        ltc = self.eng.compute_ltc(trades)
        # 1 contained (-0.5), 2 uncontained (-1.5, -2.0)
        assert ltc == pytest.approx(1.0 / 3.0)

    def test_ltc_no_losses(self):
        """No losses → LTC = 1.0 (perfect containment)."""
        trades = _make_trade_set([1.0, 0.5, 2.0])
        ltc = self.eng.compute_ltc(trades)
        assert ltc == 1.0

    def test_rocpr(self):
        """ROCPR = sum(pnl) / sum(risk)."""
        trades = _make_trade_set([1.0, -0.5, 0.3], risk_unit=100.0)
        rocpr = self.eng.compute_rocpr(trades)
        expected = (100.0 - 50.0 + 30.0) / 300.0
        assert rocpr == pytest.approx(expected)

    def test_profit_factor(self):
        """Profit factor = gross_win / gross_loss."""
        trades = _make_trade_set([2.0, 1.0, -0.5, -1.0])
        pf = self.eng.compute_profit_factor(trades)
        assert pf == pytest.approx(3.0 / 1.5)

    def test_profit_factor_no_losers(self):
        """No losers → profit factor undefined (None)."""
        trades = _make_trade_set([1.0, 2.0, 0.5])
        pf = self.eng.compute_profit_factor(trades)
        assert pf is None

    def test_tail_contribution(self):
        """Tail contribution computed correctly."""
        trades = _make_trade_set([2.0, 0.5, -0.3, -1.5])
        tc = self.eng.compute_tail_contribution(trades)
        assert tc is not None
        # RTC: sum(R > 1.5) / sum(R) = 2.0 / (2.0 + 0.5 - 0.3 - 1.5) = 2.0 / 0.7
        assert tc.right_tail_contribution == pytest.approx(2.0 / 0.7)
        # LTC: sum(|R| where R < -1) / sum(|R|) = 1.5 / (2.0 + 0.5 + 0.3 + 1.5) = 1.5 / 4.3
        assert tc.left_tail_contribution == pytest.approx(1.5 / 4.3)

    def test_strategy_mix_sums_to_one(self):
        """Strategy mix weights must sum to 1."""
        trades = [
            _make_trade(0, 1.0, strategy=StrategyCategory.CONVEX_EXPANSION),
            _make_trade(1, -0.5, days_offset=1, strategy=StrategyCategory.EVENT_COMPRESSION),
            _make_trade(2, 0.3, days_offset=2, strategy=StrategyCategory.PREMIUM_COLLECTION),
        ]
        mix = self.eng.compute_strategy_mix(trades)
        total = mix.convex_expansion + mix.event_compression + mix.premium_collection
        assert total == pytest.approx(1.0)

    def test_excess_kurtosis_normal_like(self):
        """Large symmetric set has near-zero excess kurtosis."""
        # Use deterministic "normal-like" R values
        np.random.seed(42)
        r_vals = list(np.random.normal(0, 1, 200))
        trades = _make_trade_set(r_vals)
        k = self.eng.compute_excess_kurtosis(trades)
        # Should be near 0 for normal, allow tolerance
        assert abs(k) < 1.0

    def test_tail_ratio(self):
        """Tail ratio computed from deciles."""
        # 10 trades, decile_size = 1
        r_vals = [-2.0, -1.0, -0.5, 0.0, 0.1, 0.2, 0.5, 1.0, 1.5, 3.0]
        trades = _make_trade_set(r_vals)
        tr = self.eng.compute_tail_ratio(trades)
        # top decile = [3.0], bottom decile = [-2.0]
        assert tr == pytest.approx(3.0 / 2.0)


# ---------------------------------------------------------------------------
# 3. Regime Engine
# ---------------------------------------------------------------------------

class TestRegimeEngine:
    def test_vix_zombieland(self):
        assert RegimeEngine.classify_vix(12.0) == RegimeBucket.ZOMBIELAND
        assert RegimeEngine.classify_vix(17.0) == RegimeBucket.ZOMBIELAND

    def test_vix_goldilocks_1(self):
        assert RegimeEngine.classify_vix(17.1) == RegimeBucket.GOLDILOCKS_1
        assert RegimeEngine.classify_vix(24.0) == RegimeBucket.GOLDILOCKS_1

    def test_vix_goldilocks_2(self):
        assert RegimeEngine.classify_vix(24.1) == RegimeBucket.GOLDILOCKS_2
        assert RegimeEngine.classify_vix(32.0) == RegimeBucket.GOLDILOCKS_2

    def test_vix_chaos(self):
        assert RegimeEngine.classify_vix(32.1) == RegimeBucket.CHAOS
        assert RegimeEngine.classify_vix(80.0) == RegimeBucket.CHAOS

    def test_segment_groups_correctly(self):
        trades = [
            _make_trade(0, 1.0, regime=RegimeBucket.ZOMBIELAND),
            _make_trade(1, -0.5, days_offset=1, regime=RegimeBucket.CHAOS),
            _make_trade(2, 0.3, days_offset=2, regime=RegimeBucket.ZOMBIELAND),
        ]
        buckets = RegimeEngine.segment(trades)
        assert len(buckets[RegimeBucket.ZOMBIELAND]) == 2
        assert len(buckets[RegimeBucket.CHAOS]) == 1
        assert len(buckets[RegimeBucket.GOLDILOCKS_1]) == 0

    def test_is_goldilocks(self):
        assert RegimeEngine.is_goldilocks(RegimeBucket.GOLDILOCKS_1)
        assert RegimeEngine.is_goldilocks(RegimeBucket.GOLDILOCKS_2)
        assert not RegimeEngine.is_goldilocks(RegimeBucket.ZOMBIELAND)
        assert not RegimeEngine.is_goldilocks(RegimeBucket.CHAOS)


# ---------------------------------------------------------------------------
# 4. Window Engine
# ---------------------------------------------------------------------------

class TestWindowEngine:
    def test_7d_window(self):
        """Only trades within 7 days are included."""
        ref = BASE_TIME + timedelta(days=30)
        eng = WindowEngine(reference_time=ref)
        trades = _make_trade_set(
            [float(i) for i in range(31)],  # trades on days 0..30
        )
        filtered = eng.apply(trades, RollingWindow.D7)
        # Days 23-30 inclusive = 8 trades
        assert all(t.exit_timestamp >= ref - timedelta(days=7) for t in filtered)
        assert all(t.exit_timestamp <= ref for t in filtered)

    def test_sorted_by_exit_timestamp(self):
        """Results are deterministically sorted."""
        ref = BASE_TIME + timedelta(days=10)
        eng = WindowEngine(reference_time=ref)
        trades = _make_trade_set([1.0] * 10)
        filtered = eng.apply(trades, RollingWindow.D30)
        timestamps = [t.exit_timestamp for t in filtered]
        assert timestamps == sorted(timestamps)

    def test_minimum_sample(self):
        """MIN_SAMPLE enforcement works."""
        eng = WindowEngine()
        assert eng.meets_minimum_sample([_make_trade(i, 1.0) for i in range(10)])
        assert not eng.meets_minimum_sample([_make_trade(i, 1.0) for i in range(9)])


# ---------------------------------------------------------------------------
# 5. Normalization Engine + CII
# ---------------------------------------------------------------------------

class TestNormalizationEngine:
    def setup_method(self):
        self.eng = NormalizationEngine()

    def test_normalize_skew_midpoint(self):
        """Skew 0 maps to 0.5 (midpoint of [-1, 1] → [0, 1])."""
        assert self.eng.normalize_skew(0.0) == pytest.approx(0.5)

    def test_normalize_skew_bounds(self):
        """Skew at bounds maps to 0 and 1."""
        assert self.eng.normalize_skew(-1.0) == pytest.approx(0.0)
        assert self.eng.normalize_skew(1.0) == pytest.approx(1.0)

    def test_normalize_skew_clamp(self):
        """Skew outside bounds is clamped."""
        assert self.eng.normalize_skew(-5.0) == 0.0
        assert self.eng.normalize_skew(5.0) == 1.0

    def test_normalize_ltc(self):
        """LTC clamped to [0, 1]."""
        assert self.eng.normalize_ltc(0.5) == pytest.approx(0.5)
        assert self.eng.normalize_ltc(-0.1) == 0.0
        assert self.eng.normalize_ltc(1.5) == 1.0

    def test_normalize_rocpr(self):
        """ROCPR 1.0 → 0.5 (cap = 2.0)."""
        assert self.eng.normalize_rocpr(1.0) == pytest.approx(0.5)
        assert self.eng.normalize_rocpr(0.0) == 0.0
        assert self.eng.normalize_rocpr(3.0) == 1.0  # clamped

    def test_normalize_dd_vol(self):
        """DD vol 0.5 → 0.5 (cap = 1.0)."""
        assert self.eng.normalize_drawdown_volatility(0.5) == pytest.approx(0.5)

    def test_cii_all_perfect(self):
        """Perfect inputs: skew=1, ltc=1, rocpr=2.0, dd_vol=0."""
        cii = self.eng.compute_cii(
            skew=1.0, ltc=1.0, rocpr=2.0, drawdown_volatility=0.0,
        )
        # 0.35*1 + 0.30*1 + 0.20*1 - 0.15*0 = 0.85
        assert cii == pytest.approx(0.85)

    def test_cii_all_worst(self):
        """Worst inputs: skew=-1, ltc=0, rocpr=0, dd_vol=1.0."""
        cii = self.eng.compute_cii(
            skew=-1.0, ltc=0.0, rocpr=0.0, drawdown_volatility=1.0,
        )
        # 0.35*0 + 0.30*0 + 0.20*0 - 0.15*1 = -0.15 → clamped to 0
        assert cii == 0.0

    def test_cii_none_propagation(self):
        """Any None input → CII returns None."""
        assert self.eng.compute_cii(None, 1.0, 1.0, 0.0) is None
        assert self.eng.compute_cii(1.0, None, 1.0, 0.0) is None
        assert self.eng.compute_cii(1.0, 1.0, None, 0.0) is None
        assert self.eng.compute_cii(1.0, 1.0, 1.0, None) is None

    def test_cii_never_includes_sharpe(self):
        """CII formula has exactly 4 components — no Sharpe."""
        # Verify by checking the formula produces expected result
        # with known inputs (Sharpe would change the result)
        cii = self.eng.compute_cii(
            skew=0.0, ltc=0.5, rocpr=1.0, drawdown_volatility=0.5,
        )
        expected = (0.35 * 0.5) + (0.30 * 0.5) + (0.20 * 0.5) - (0.15 * 0.5)
        assert cii == pytest.approx(expected)


# ---------------------------------------------------------------------------
# 6. Drawdown Engine (UCSP)
# ---------------------------------------------------------------------------

class TestDrawdownEngine:
    def setup_method(self):
        self.eng = DrawdownEngine()

    def test_empty_trades(self):
        """Empty input returns zero-filled profile."""
        dd = self.eng.compute([])
        assert dd.max_drawdown_depth == 0.0
        assert dd.average_drawdown_depth == 0.0
        assert dd.drawdown_depths == ()
        assert dd.peak_equity_series == ()
        assert dd.average_recovery_trades == 0.0
        assert dd.average_recovery_days == 0.0

    def test_all_winners_no_drawdown(self):
        """All positive trades → no drawdown periods."""
        trades = _make_trade_set([1.0, 0.5, 2.0, 1.0])
        dd = self.eng.compute(trades)
        assert dd.max_drawdown_depth == 0.0
        assert dd.drawdown_depths == ()
        # Peak equity should still be tracked
        assert len(dd.peak_equity_series) == 4

    def test_single_drawdown(self):
        """One drawdown period followed by recovery."""
        # Equity: 1.0, 1.5, 0.5 (dd=1.0), 1.5 (recovery)
        trades = _make_trade_set([1.0, 0.5, -1.0, 1.0])
        dd = self.eng.compute(trades)
        assert dd.max_drawdown_depth == pytest.approx(1.0)
        assert len(dd.drawdown_depths) == 1
        assert dd.drawdown_depths[0] == pytest.approx(1.0)

    def test_multiple_drawdowns(self):
        """Multiple drawdown periods are tracked separately."""
        # Equity: 2, 3, 1 (dd=2), 3.5 (recovery), 2.5 (dd=1)
        trades = _make_trade_set([2.0, 1.0, -2.0, 2.5, -1.0])
        dd = self.eng.compute(trades)
        assert dd.max_drawdown_depth == pytest.approx(2.0)
        assert len(dd.drawdown_depths) >= 1

    def test_peak_equity_series_monotonic(self):
        """Peak equity series is non-decreasing."""
        trades = _make_trade_set([1.0, -0.5, 2.0, -0.3, 1.0])
        dd = self.eng.compute(trades)
        peaks = dd.peak_equity_series
        for i in range(1, len(peaks)):
            assert peaks[i] >= peaks[i - 1]

    def test_drawdown_volatility(self):
        """Drawdown volatility is std of drawdown depths (ddof=0)."""
        # Create known drawdown depths
        trades = _make_trade_set([2.0, -1.0, 2.0, -0.5, 1.0])
        dd = self.eng.compute(trades)
        if len(dd.drawdown_depths) > 1:
            expected_vol = float(np.std(dd.drawdown_depths, ddof=0))
            assert dd.drawdown_volatility == pytest.approx(expected_vol)

    def test_ucsp_recovery_metrics(self):
        """Recovery trades and days are computed."""
        trades = _make_trade_set([2.0, -1.0, -0.5, 1.0, 1.0])
        dd = self.eng.compute(trades)
        # Should have recovery metrics for any drawdown period
        assert dd.average_recovery_trades >= 0
        assert dd.average_recovery_days >= 0


# ---------------------------------------------------------------------------
# 7. Versioning
# ---------------------------------------------------------------------------

class TestVersioning:
    def test_current_version(self):
        mv = MetricVersion()
        assert mv.current_version() == "1.0.0"

    def test_compatible(self):
        assert VersionedBundle.is_compatible("1.0.0")
        assert VersionedBundle.is_compatible("1.5.3")
        assert not VersionedBundle.is_compatible("2.0.0")

    def test_parse(self):
        assert VersionedBundle.parse("1.2.3") == (1, 2, 3)

    def test_parse_invalid(self):
        with pytest.raises(ValueError):
            VersionedBundle.parse("bad")


# ---------------------------------------------------------------------------
# 8. Deterministic Replay
# ---------------------------------------------------------------------------

class TestDeterministicReplay:
    """Same inputs must produce identical outputs. No randomness anywhere."""

    def test_full_replay(self):
        """Running the same trade set twice gives identical results."""
        r_vals = [1.5, -0.5, 2.0, -1.0, 0.3, -0.8, 1.2, -0.3, 0.5, -0.2,
                  1.0, 0.7]
        trades = _make_trade_set(r_vals)

        ref_time = BASE_TIME + timedelta(days=30)

        # Run 1
        win1 = WindowEngine(reference_time=ref_time)
        filtered1 = win1.apply(trades, RollingWindow.D30)
        me1 = MetricEngine()
        skew1 = me1.compute_skew(filtered1)
        ltc1 = me1.compute_ltc(filtered1)

        ne1 = NormalizationEngine()
        dd1 = DrawdownEngine().compute(filtered1)
        cii1 = ne1.compute_cii(
            skew=skew1, ltc=ltc1,
            rocpr=me1.compute_rocpr(filtered1),
            drawdown_volatility=dd1.drawdown_volatility,
        )

        # Run 2
        win2 = WindowEngine(reference_time=ref_time)
        filtered2 = win2.apply(trades, RollingWindow.D30)
        me2 = MetricEngine()
        skew2 = me2.compute_skew(filtered2)
        ltc2 = me2.compute_ltc(filtered2)

        ne2 = NormalizationEngine()
        dd2 = DrawdownEngine().compute(filtered2)
        cii2 = ne2.compute_cii(
            skew=skew2, ltc=ltc2,
            rocpr=me2.compute_rocpr(filtered2),
            drawdown_volatility=dd2.drawdown_volatility,
        )

        assert skew1 == skew2
        assert ltc1 == ltc2
        assert cii1 == cii2
        assert dd1 == dd2


# ---------------------------------------------------------------------------
# 9. Integration — End-to-End
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_compute_distribution_metrics(self):
        """Full pipeline produces valid DistributionResult."""
        r_vals = [1.5, -0.5, 2.0, -1.0, 0.3, -0.8, 1.2, -0.3, 0.5, -0.2,
                  1.0, 0.7]
        trades = _make_recent_trade_set(r_vals)

        result = compute_distribution_metrics(trades, RollingWindow.D30)
        assert result.version == "1.0.0"
        assert result.trade_count == 12
        assert result.skew is not None
        assert result.ltc is not None
        assert result.cii is not None
        assert 0.0 <= result.cii <= 1.0
        assert result.drawdown is not None
        assert result.drawdown.peak_equity_series  # not empty

    def test_below_min_sample_returns_none_metrics(self):
        """Below MIN_SAMPLE, all metrics are None."""
        trades = _make_recent_trade_set([1.0, -0.5])
        result = compute_distribution_metrics(trades, RollingWindow.D7)
        assert result.trade_count == 2
        assert result.skew is None
        assert result.cii is None

    def test_compute_regime_segmented(self):
        """Regime segmented metrics produce RegimeDistributionResult."""
        trades = _make_recent_trade_set(
            [1.0, -0.5, 0.3, -0.2] * 3,
            regime=RegimeBucket.ZOMBIELAND,
        )
        result = compute_regime_segmented_metrics(trades, RollingWindow.D30)
        assert result.zombieland is not None
        assert result.zombieland.trade_count == 12

    def test_compute_strategy_mix_integration(self):
        """Strategy mix entry point works."""
        trades = _make_recent_trade_set([1.0] * 5)
        mix = compute_strategy_mix(trades, RollingWindow.D30)
        assert mix.convex_expansion == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 10. Performance Benchmark
# ---------------------------------------------------------------------------

class TestBenchmark:
    def test_10k_trades_under_200ms(self):
        """Full pipeline on 10K trades completes in <200ms."""
        np.random.seed(42)
        r_vals = list(np.random.normal(0.1, 0.8, 10_000))
        trades = _make_recent_trade_set(r_vals)

        start = time.perf_counter()
        result = compute_distribution_metrics(trades, RollingWindow.D180)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert result.trade_count > 0
        assert elapsed_ms < 200, f"Pipeline took {elapsed_ms:.1f}ms (limit: 200ms)"
