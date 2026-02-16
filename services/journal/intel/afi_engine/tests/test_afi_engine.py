"""
AFI Engine — Unit Tests

Deterministic data, no IO. Validates all formulas from the plan.
"""
import math
from datetime import datetime, timedelta

import numpy as np
import pytest

from services.journal.intel.afi_engine import compute_afi, trim_wss_history
from services.journal.intel.afi_engine.recency import (
    HALF_LIFE_DAYS,
    LAMBDA,
    compute_weights,
    weighted_mean,
    weighted_std,
)
from services.journal.intel.afi_engine.component_engine import (
    DD_CAP,
    RECOVERY_CAP,
    _identify_drawdown_periods,
    compute_dd_containment,
    compute_ltc,
    compute_r_slope,
    compute_sharpe,
)
from services.journal.intel.afi_engine.scoring_engine import (
    CENTER,
    K,
    S,
    SHIFT,
    compress,
    compute_robustness,
    compute_trend,
    compute_wss,
    dampen,
    is_provisional,
    normalize_components,
    normalize_r_slope,
    normalize_sharpe,
)
from services.journal.intel.afi_engine.models import AFIComponents, TrendSignal

NOW = datetime(2026, 2, 15, 12, 0, 0)


# ===================================================================
#  Recency Weights
# ===================================================================

class TestRecencyWeights:
    def test_empty(self):
        w = compute_weights([], NOW)
        assert len(w) == 0

    def test_single_trade(self):
        w = compute_weights([NOW], NOW)
        assert len(w) == 1
        assert abs(w[0] - 1.0) < 1e-10

    def test_half_life(self):
        """Trade 180 days old should have half the raw weight of today's trade."""
        t_today = NOW
        t_old = NOW - timedelta(days=180)
        w = compute_weights([t_old, t_today], NOW)
        # Raw weights: exp(0) = 1.0, exp(-λ*180) = 0.5
        # Normalized: 0.5/1.5 ≈ 0.333, 1.0/1.5 ≈ 0.667
        assert abs(w[0] - 1.0 / 3.0) < 0.01
        assert abs(w[1] - 2.0 / 3.0) < 0.01

    def test_weights_sum_to_one(self):
        times = [NOW - timedelta(days=i * 30) for i in range(10)]
        w = compute_weights(times, NOW)
        assert abs(w.sum() - 1.0) < 1e-10

    def test_lambda_value(self):
        assert abs(LAMBDA - math.log(2) / 180) < 1e-10

    def test_weighted_mean_uniform(self):
        vals = np.array([1.0, 2.0, 3.0])
        w = np.array([1 / 3, 1 / 3, 1 / 3])
        assert abs(weighted_mean(vals, w) - 2.0) < 1e-10

    def test_weighted_std_zero_variance(self):
        vals = np.array([5.0, 5.0, 5.0])
        w = np.array([1 / 3, 1 / 3, 1 / 3])
        assert abs(weighted_std(vals, w)) < 1e-10

    def test_weighted_std_single(self):
        assert weighted_std(np.array([5.0]), np.array([1.0])) == 0.0


# ===================================================================
#  R-Slope
# ===================================================================

class TestRSlope:
    def test_flat_series(self):
        """All zeros → slope 0."""
        r = np.array([0.0] * 20)
        w = np.ones(20) / 20
        assert abs(compute_r_slope(r, w)) < 1e-10

    def test_positive_slope(self):
        """Consistent +1R trades → positive cumulative slope."""
        r = np.array([1.0] * 20)
        w = np.ones(20) / 20
        slope = compute_r_slope(r, w)
        assert slope > 0.5  # Cumulative goes 1, 2, 3... slope ≈ 1.0

    def test_negative_slope(self):
        """Consistent -0.5R trades → negative slope."""
        r = np.array([-0.5] * 20)
        w = np.ones(20) / 20
        assert compute_r_slope(r, w) < -0.2

    def test_single_trade(self):
        r = np.array([1.0])
        w = np.array([1.0])
        assert compute_r_slope(r, w) == 0.0

    def test_empty(self):
        assert compute_r_slope(np.array([]), np.array([])) == 0.0


# ===================================================================
#  Sharpe
# ===================================================================

class TestSharpe:
    def test_positive(self):
        r = np.array([0.5, 0.3, 0.4, 0.6, 0.2])
        w = np.ones(5) / 5
        s = compute_sharpe(r, w)
        assert s > 0

    def test_zero_variance(self):
        r = np.array([1.0, 1.0, 1.0])
        w = np.ones(3) / 3
        assert compute_sharpe(r, w) == 0.0

    def test_negative(self):
        r = np.array([-0.5, -0.3, -0.4])
        w = np.ones(3) / 3
        assert compute_sharpe(r, w) < 0

    def test_empty(self):
        assert compute_sharpe(np.array([]), np.array([])) == 0.0


# ===================================================================
#  LTC
# ===================================================================

class TestLTC:
    def test_all_contained(self):
        """All losses within 1R → LTC = 1.0."""
        r = np.array([-0.5, -0.8, -1.0, 0.5, 1.0])
        w = np.ones(5) / 5
        assert abs(compute_ltc(r, w) - 1.0) < 1e-10

    def test_none_contained(self):
        """All losses exceed 1R → LTC = 0.0."""
        r = np.array([-1.5, -2.0, -3.0])
        w = np.ones(3) / 3
        assert abs(compute_ltc(r, w)) < 1e-10

    def test_mixed(self):
        """Mix of contained and uncontained."""
        r = np.array([-0.5, -1.5, -0.8, -2.0])
        w = np.ones(4) / 4
        # 2 contained, 2 not → 0.5
        assert abs(compute_ltc(r, w) - 0.5) < 1e-10

    def test_no_losses(self):
        r = np.array([0.5, 1.0, 2.0])
        w = np.ones(3) / 3
        assert compute_ltc(r, w) == 1.0

    def test_recency_weighted(self):
        """Recent contained loss should weigh more than old uncontained."""
        r = np.array([-1.5, -0.5])  # old breach, recent contained
        w = np.array([0.2, 0.8])  # recency favours second
        ltc = compute_ltc(r, w)
        assert ltc > 0.5  # Should be closer to 0.8

    def test_empty(self):
        assert compute_ltc(np.array([]), np.array([])) == 1.0


# ===================================================================
#  DD Containment
# ===================================================================

class TestDDContainment:
    def test_no_drawdowns(self):
        """Always winning → DD = 1.0."""
        r = np.array([1.0, 0.5, 1.0, 0.5])
        assert abs(compute_dd_containment(r) - 1.0) < 1e-10

    def test_shallow_quick_recovery(self):
        """Shallow DD with fast recovery → high score."""
        r = np.array([1.0, 1.0, -0.5, -0.5, 1.0, 1.0])
        score = compute_dd_containment(r)
        assert score > 0.7

    def test_deep_unrecovered(self):
        """Deep unrecovered DD → low score."""
        r = np.array([1.0, -3.0, -2.0])
        score = compute_dd_containment(r)
        assert score < 0.3

    def test_identify_periods(self):
        """Verify period identification."""
        r = np.array([1.0, -0.5, 1.0, -2.0, 3.0])
        periods = _identify_drawdown_periods(r)
        assert len(periods) >= 1
        # All should be recovered since equity finishes at 2.5
        for _, _, recovered in periods:
            assert recovered

    def test_empty(self):
        assert compute_dd_containment(np.array([])) == 1.0

    def test_dd_cap(self):
        """5R+ drawdown → depth_score = 0."""
        r = np.array([2.0, -7.0])  # Equity: 2, -5. DD = 7R > DD_CAP
        score = compute_dd_containment(r)
        assert score < 0.05  # depth=0, recovery=0 (unrecovered)


# ===================================================================
#  Normalization
# ===================================================================

class TestNormalization:
    def test_r_slope_flat(self):
        assert abs(normalize_r_slope(0.0) - 0.5) < 1e-10

    def test_r_slope_positive(self):
        assert normalize_r_slope(0.08) > 0.7

    def test_r_slope_negative(self):
        assert normalize_r_slope(-0.08) < 0.3

    def test_sharpe_clamp_low(self):
        assert normalize_sharpe(-2.0) == 0.0

    def test_sharpe_clamp_high(self):
        assert normalize_sharpe(5.0) == 1.0

    def test_sharpe_midpoint(self):
        assert abs(normalize_sharpe(1.0) - 0.5) < 1e-10


# ===================================================================
#  Compression
# ===================================================================

class TestCompression:
    def test_center(self):
        """WSS = SHIFT → AFI = CENTER."""
        assert abs(compress(SHIFT) - CENTER) < 1e-10

    def test_monotonic(self):
        """Higher WSS → higher AFI."""
        vals = [compress(w / 10) for w in range(11)]
        for i in range(len(vals) - 1):
            assert vals[i + 1] > vals[i]

    def test_floor(self):
        assert compress(0.0) > 300

    def test_ceiling(self):
        assert compress(1.0) < 900

    def test_elite_threshold(self):
        """WSS 0.88 → AFI ~822 (Black tier)."""
        afi = compress(0.88)
        assert 815 < afi < 830

    def test_mapping_table_samples(self):
        """Verify key mapping table values from the plan."""
        assert abs(compress(0.50) - 600) < 2
        assert 730 < compress(0.70) < 745
        assert 760 < compress(0.75) < 780


# ===================================================================
#  Robustness
# ===================================================================

class TestRobustness:
    def test_beginner(self):
        rb = compute_robustness(15, 20, 0.25, 0)
        assert 15 < rb < 20

    def test_intermediate(self):
        rb = compute_robustness(100, 180, 0.5, 4)
        assert 50 < rb < 60

    def test_veteran(self):
        rb = compute_robustness(400, 365, 0.8, 8)
        assert 95 < rb < 110


# ===================================================================
#  Dampening
# ===================================================================

class TestDampening:
    def test_first_computation(self):
        """No prior → returns raw."""
        assert dampen(750.0, None, 50.0) == 750.0

    def test_high_rb_slow(self):
        """High RB → small movement."""
        result = dampen(800.0, 700.0, 90.0)
        # factor = 1/(1+90/30) = 0.25, delta = 100 → move 25
        expected = 700.0 + 100.0 * 0.25
        assert abs(result - expected) < 0.01

    def test_zero_rb_full(self):
        """RB=0 → full movement."""
        assert abs(dampen(800.0, 700.0, 0.0) - 800.0) < 1e-10

    def test_same_value(self):
        """Prior == raw → no movement regardless of RB."""
        assert abs(dampen(700.0, 700.0, 50.0) - 700.0) < 1e-10


# ===================================================================
#  Trend
# ===================================================================

class TestTrend:
    def test_improving(self):
        history = [{"date": f"2026-01-{i:02d}", "wss": 0.5 + i * 0.01} for i in range(1, 20)]
        assert compute_trend(history) == TrendSignal.IMPROVING

    def test_decaying(self):
        history = [{"date": f"2026-01-{i:02d}", "wss": 0.8 - i * 0.01} for i in range(1, 20)]
        assert compute_trend(history) == TrendSignal.DECAYING

    def test_stable(self):
        history = [{"date": f"2026-01-{i:02d}", "wss": 0.65} for i in range(1, 20)]
        assert compute_trend(history) == TrendSignal.STABLE

    def test_too_few(self):
        assert compute_trend([]) == TrendSignal.STABLE
        assert compute_trend([{"date": "2026-01-01", "wss": 0.5}]) == TrendSignal.STABLE


# ===================================================================
#  Provisional
# ===================================================================

class TestProvisional:
    def test_low_trades(self):
        assert is_provisional(10, 60) is True

    def test_low_days(self):
        assert is_provisional(50, 15) is True

    def test_both_low(self):
        assert is_provisional(5, 5) is True

    def test_not_provisional(self):
        assert is_provisional(30, 45) is False


# ===================================================================
#  End-to-End: Synthetic Trader Simulations
# ===================================================================

def _make_trades(r_multiples_list, days_ago_list):
    """Helper to build trade dicts for compute_afi."""
    trades = []
    for r, days_ago in zip(r_multiples_list, days_ago_list):
        t = NOW - timedelta(days=days_ago)
        trades.append({
            "r_multiple": r,
            "exit_time": t,
            "planned_risk": 100,
            "pnl": int(r * 100),
            "quantity": 1,
        })
    return trades


class TestSyntheticTraders:
    def test_smooth_operator(self):
        """High Sharpe, low growth → Purple tier (~771)."""
        np.random.seed(42)
        n = 150
        # Mostly +0.3 to +0.5, occasional -0.5
        r_vals = np.concatenate([
            np.random.uniform(0.3, 0.5, int(n * 0.85)),
            np.random.uniform(-0.5, -0.3, int(n * 0.15)),
        ])
        np.random.shuffle(r_vals)
        days = np.linspace(200, 0, n)  # spread over 200 days
        trades = _make_trades(r_vals.tolist(), days.tolist())

        result = compute_afi(trades, reference_time=NOW)
        assert 700 < result.afi_score < 850
        assert result.robustness > 40
        assert not result.is_provisional

    def test_cowboy(self):
        """Explosive growth, high DD → Blue tier (~654)."""
        np.random.seed(123)
        n = 80
        r_vals = np.concatenate([
            np.random.uniform(1.0, 5.0, int(n * 0.4)),
            np.random.uniform(-3.0, -1.5, int(n * 0.3)),
            np.random.uniform(-0.5, 0.5, int(n * 0.3)),
        ])
        np.random.shuffle(r_vals)
        days = np.linspace(120, 0, n)
        trades = _make_trades(r_vals.tolist(), days.tolist())

        result = compute_afi(trades, reference_time=NOW)
        assert result.afi_score < 750  # Should not reach Purple
        assert result.components.ltc < 0.8  # Poor containment

    def test_tortoise(self):
        """Stable grinder → Purple tier (~719), high RB."""
        np.random.seed(99)
        n = 300
        r_vals = np.concatenate([
            np.random.uniform(0.2, 1.0, int(n * 0.6)),
            np.random.uniform(-0.8, -0.3, int(n * 0.4)),
        ])
        np.random.shuffle(r_vals)
        days = np.linspace(365, 0, n)
        trades = _make_trades(r_vals.tolist(), days.tolist())

        result = compute_afi(trades, reference_time=NOW)
        assert 650 < result.afi_score < 800
        assert result.robustness > 70  # Highest RB
        assert not result.is_provisional

    def test_ranking_order(self):
        """Smooth Operator > Tortoise > Cowboy on structural merit."""
        # Use deterministic seeds so results are reproducible
        np.random.seed(42)
        smooth = np.concatenate([
            np.random.uniform(0.3, 0.5, 128),
            np.random.uniform(-0.5, -0.3, 22),
        ])
        np.random.shuffle(smooth)

        np.random.seed(123)
        cowboy = np.concatenate([
            np.random.uniform(1.0, 5.0, 32),
            np.random.uniform(-3.0, -1.5, 24),
            np.random.uniform(-0.5, 0.5, 24),
        ])
        np.random.shuffle(cowboy)

        np.random.seed(99)
        tortoise = np.concatenate([
            np.random.uniform(0.2, 1.0, 180),
            np.random.uniform(-0.8, -0.3, 120),
        ])
        np.random.shuffle(tortoise)

        r_smooth = compute_afi(
            _make_trades(smooth.tolist(), np.linspace(200, 0, len(smooth)).tolist()),
            reference_time=NOW,
        )
        r_cowboy = compute_afi(
            _make_trades(cowboy.tolist(), np.linspace(120, 0, len(cowboy)).tolist()),
            reference_time=NOW,
        )
        r_tortoise = compute_afi(
            _make_trades(tortoise.tolist(), np.linspace(365, 0, len(tortoise)).tolist()),
            reference_time=NOW,
        )

        # Cowboy should be lowest — fragile despite growth
        assert r_cowboy.afi_score < r_tortoise.afi_score
        assert r_cowboy.afi_score < r_smooth.afi_score


# ===================================================================
#  Edge Cases
# ===================================================================

class TestEdgeCases:
    def test_zero_trades(self):
        result = compute_afi([], reference_time=NOW)
        assert result.trade_count == 0
        assert result.is_provisional
        assert result.afi_score > 300

    def test_single_trade(self):
        trades = _make_trades([1.5], [0])
        result = compute_afi(trades, reference_time=NOW)
        assert result.trade_count == 1
        assert result.is_provisional

    def test_all_winners(self):
        trades = _make_trades([0.5] * 30, list(range(30)))
        result = compute_afi(trades, reference_time=NOW)
        assert result.components.ltc == 1.0
        assert result.components.dd_containment == 1.0

    def test_all_losers_contained(self):
        """All losses within 1R → LTC = 1.0 still."""
        trades = _make_trades([-0.5] * 30, list(range(30)))
        result = compute_afi(trades, reference_time=NOW)
        assert result.components.ltc == 1.0
        assert result.afi_score < 600  # Negative slope + negative Sharpe

    def test_statefulness(self):
        """Second computation should dampen toward prior."""
        trades = _make_trades([0.5] * 50, list(range(50)))
        r1 = compute_afi(trades, reference_time=NOW)
        r2 = compute_afi(trades, prior_afi=r1.afi_score, reference_time=NOW)
        # Same trades, same raw → dampened should equal prior (no delta)
        assert abs(r2.afi_score - r1.afi_score) < 1.0


# ===================================================================
#  WSS History Trimming
# ===================================================================

class TestWSSHistory:
    def test_under_limit(self):
        h = [{"date": "2026-01-01", "wss": 0.5}] * 50
        assert len(trim_wss_history(h)) == 50

    def test_over_limit(self):
        h = [{"date": f"2026-01-{i:02d}", "wss": 0.5 + i * 0.001} for i in range(200)]
        trimmed = trim_wss_history(h)
        assert len(trimmed) == 90
        # Should keep most recent
        assert trimmed[-1] == h[-1]
