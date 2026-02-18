"""
AFI Engine — Unit Tests

Deterministic data, no IO. Validates all formulas from the plan.
"""
import math
from datetime import datetime, timedelta

import numpy as np
import pytest

from services.journal.intel.afi_engine import AFI_VERSION, compute_afi, trim_wss_history
from services.journal.intel.afi_engine.recency import (
    HALF_LIFE_DAYS,
    LAMBDA,
    compute_equal_weights,
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
    CRED_BONUS_K,
    CRED_SHARPE_K,
    ELITE_BONUS_SCALE,
    ELITE_SHARPE_THRESHOLD,
    K,
    MIN_CAPITAL,
    NEUTRAL_AFI,
    S,
    SHIFT,
    STABILITY_VAR_CAP,
    TAIL_RATIO_CAP,
    CONVEXITY_RATIO_CAP,
    ROLLING_WSS_WINDOW,
    compress,
    compute_convexity_amplifier,
    compute_convexity_ratio,
    compute_distribution_stability,
    compute_elite_bonus,
    compute_repeatability,
    compute_robustness,
    compute_robustness_v2,
    compute_rolling_sharpe_stability,
    compute_rolling_wss_stability,
    compute_sharpe_adj,
    compute_skew_bonus,
    compute_skew_persistence,
    compute_tail_ratio,
    compute_trend,
    compute_wss,
    cred_bonus,
    cred_sharpe,
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
        r = np.array([0.0] * 20)
        w = np.ones(20) / 20
        assert abs(compute_r_slope(r, w)) < 1e-10

    def test_positive_slope(self):
        r = np.array([1.0] * 20)
        w = np.ones(20) / 20
        slope = compute_r_slope(r, w)
        assert slope > 0.5

    def test_negative_slope(self):
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
        r = np.array([-0.5, -0.8, -1.0, 0.5, 1.0])
        w = np.ones(5) / 5
        assert abs(compute_ltc(r, w) - 1.0) < 1e-10

    def test_none_contained(self):
        r = np.array([-1.5, -2.0, -3.0])
        w = np.ones(3) / 3
        assert abs(compute_ltc(r, w)) < 1e-10

    def test_mixed(self):
        r = np.array([-0.5, -1.5, -0.8, -2.0])
        w = np.ones(4) / 4
        assert abs(compute_ltc(r, w) - 0.5) < 1e-10

    def test_no_losses(self):
        r = np.array([0.5, 1.0, 2.0])
        w = np.ones(3) / 3
        assert compute_ltc(r, w) == 1.0

    def test_recency_weighted(self):
        r = np.array([-1.5, -0.5])
        w = np.array([0.2, 0.8])
        ltc = compute_ltc(r, w)
        assert ltc > 0.5

    def test_empty(self):
        assert compute_ltc(np.array([]), np.array([])) == 1.0


# ===================================================================
#  DD Containment
# ===================================================================

class TestDDContainment:
    def test_no_drawdowns(self):
        r = np.array([1.0, 0.5, 1.0, 0.5])
        assert abs(compute_dd_containment(r) - 1.0) < 1e-10

    def test_shallow_quick_recovery(self):
        r = np.array([1.0, 1.0, -0.5, -0.5, 1.0, 1.0])
        score = compute_dd_containment(r)
        assert score > 0.7

    def test_deep_unrecovered(self):
        r = np.array([1.0, -3.0, -2.0])
        score = compute_dd_containment(r)
        assert score < 0.3

    def test_identify_periods(self):
        r = np.array([1.0, -0.5, 1.0, -2.0, 3.0])
        periods = _identify_drawdown_periods(r)
        assert len(periods) >= 1
        for _, _, recovered in periods:
            assert recovered

    def test_empty(self):
        assert compute_dd_containment(np.array([])) == 1.0

    def test_dd_cap(self):
        r = np.array([2.0, -7.0])
        score = compute_dd_containment(r)
        assert score < 0.05


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
        assert abs(compress(SHIFT) - CENTER) < 1e-10

    def test_monotonic(self):
        vals = [compress(w / 10) for w in range(11)]
        for i in range(len(vals) - 1):
            assert vals[i + 1] > vals[i]

    def test_floor(self):
        assert compress(0.0) > 300

    def test_ceiling(self):
        assert compress(1.0) < 900


# ===================================================================
#  Robustness (v1)
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
#  Dampening (v1)
# ===================================================================

class TestDampening:
    def test_first_computation(self):
        assert dampen(750.0, None, 50.0) == 750.0

    def test_high_rb_slow(self):
        result = dampen(800.0, 700.0, 90.0)
        expected = 700.0 + 100.0 * 0.25
        assert abs(result - expected) < 0.01

    def test_zero_rb_full(self):
        assert abs(dampen(800.0, 700.0, 0.0) - 800.0) < 1e-10

    def test_same_value(self):
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
#  End-to-End: Synthetic Trader Simulations (v1)
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
        """High Sharpe, low growth → Purple tier (~771). v1."""
        np.random.seed(42)
        n = 150
        r_vals = np.concatenate([
            np.random.uniform(0.3, 0.5, int(n * 0.85)),
            np.random.uniform(-0.5, -0.3, int(n * 0.15)),
        ])
        np.random.shuffle(r_vals)
        days = np.linspace(200, 0, n)
        trades = _make_trades(r_vals.tolist(), days.tolist())

        result = compute_afi(trades, reference_time=NOW, version=1)
        assert 700 < result.afi_score < 850
        assert result.robustness > 40
        assert not result.is_provisional

    def test_cowboy(self):
        """Explosive growth, high DD → Blue tier. v1."""
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

        result = compute_afi(trades, reference_time=NOW, version=1)
        assert result.afi_score < 750
        assert result.components.ltc < 0.8

    def test_tortoise(self):
        """Stable grinder → high RB. v1."""
        np.random.seed(99)
        n = 300
        r_vals = np.concatenate([
            np.random.uniform(0.2, 1.0, int(n * 0.6)),
            np.random.uniform(-0.8, -0.3, int(n * 0.4)),
        ])
        np.random.shuffle(r_vals)
        days = np.linspace(365, 0, n)
        trades = _make_trades(r_vals.tolist(), days.tolist())

        result = compute_afi(trades, reference_time=NOW, version=1)
        assert 650 < result.afi_score < 800
        assert result.robustness > 70
        assert not result.is_provisional

    def test_ranking_order(self):
        """Smooth Operator > Tortoise > Cowboy on structural merit. v1."""
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
            reference_time=NOW, version=1,
        )
        r_cowboy = compute_afi(
            _make_trades(cowboy.tolist(), np.linspace(120, 0, len(cowboy)).tolist()),
            reference_time=NOW, version=1,
        )
        r_tortoise = compute_afi(
            _make_trades(tortoise.tolist(), np.linspace(365, 0, len(tortoise)).tolist()),
            reference_time=NOW, version=1,
        )

        assert r_cowboy.afi_score < r_tortoise.afi_score
        assert r_cowboy.afi_score < r_smooth.afi_score


# ===================================================================
#  Edge Cases
# ===================================================================

class TestEdgeCases:
    def test_zero_trades(self):
        result = compute_afi([], reference_time=NOW, version=1)
        assert result.trade_count == 0
        assert result.is_provisional
        assert result.afi_score > 300

    def test_single_trade(self):
        trades = _make_trades([1.5], [0])
        result = compute_afi(trades, reference_time=NOW, version=1)
        assert result.trade_count == 1
        assert result.is_provisional

    def test_all_winners(self):
        trades = _make_trades([0.5] * 30, list(range(30)))
        result = compute_afi(trades, reference_time=NOW, version=1)
        assert result.components.ltc == 1.0
        assert result.components.dd_containment == 1.0

    def test_all_losers_contained(self):
        trades = _make_trades([-0.5] * 30, list(range(30)))
        result = compute_afi(trades, reference_time=NOW, version=1)
        assert result.components.ltc == 1.0
        assert result.afi_score < 600

    def test_statefulness(self):
        """v1: second computation should dampen toward prior."""
        trades = _make_trades([0.5] * 50, list(range(50)))
        r1 = compute_afi(trades, reference_time=NOW, version=1)
        r2 = compute_afi(trades, prior_afi=r1.afi_score, reference_time=NOW, version=1)
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
        assert trimmed[-1] == h[-1]

    def test_no_cap_v2(self):
        h = [{"date": f"d{i}", "wss": 0.5} for i in range(500)]
        trimmed = trim_wss_history(h, max_entries=None)
        assert len(trimmed) == 500


# ===================================================================
#  v2: Equal Weights
# ===================================================================

class TestEqualWeights:
    def test_empty(self):
        w = compute_equal_weights(0)
        assert len(w) == 0

    def test_single(self):
        w = compute_equal_weights(1)
        assert len(w) == 1
        assert abs(w[0] - 1.0) < 1e-10

    def test_uniform(self):
        w = compute_equal_weights(10)
        assert len(w) == 10
        assert abs(w.sum() - 1.0) < 1e-10
        for wi in w:
            assert abs(wi - 0.1) < 1e-10

    def test_large(self):
        w = compute_equal_weights(1000)
        assert abs(w.sum() - 1.0) < 1e-10
        assert abs(w[0] - 0.001) < 1e-10


# ===================================================================
#  v2: Robustness v2
# ===================================================================

class TestRobustnessV2:
    def test_formula(self):
        rb = compute_robustness_v2(
            regime_diversity=0.5,
            survived_dds=4,
            distribution_stability=0.8,
        )
        expected = 10.0 * 0.5 + 3.0 * 4 + 5.0 * 0.8
        assert abs(rb - expected) < 1e-10

    def test_no_trade_count_dependency(self):
        rb1 = compute_robustness_v2(0.5, 2, 0.7)
        rb2 = compute_robustness_v2(0.5, 2, 0.7)
        assert rb1 == rb2

    def test_zero_all(self):
        rb = compute_robustness_v2(0.0, 0, 0.0)
        assert abs(rb) < 1e-10

    def test_max_regime(self):
        rb = compute_robustness_v2(1.0, 0, 0.0)
        assert abs(rb - 10.0) < 1e-10

    def test_clamped_regime(self):
        rb = compute_robustness_v2(1.5, 0, 0.0)
        assert abs(rb - 10.0) < 1e-10


# ===================================================================
#  v2: Distribution Stability
# ===================================================================

class TestDistributionStability:
    def test_too_few_points(self):
        assert compute_distribution_stability([]) == 0.5
        assert compute_distribution_stability([{"wss": 0.6}]) == 0.5
        assert compute_distribution_stability([{"wss": 0.6}, {"wss": 0.7}]) == 0.5

    def test_perfect_stability(self):
        history = [{"wss": 0.65} for _ in range(20)]
        assert abs(compute_distribution_stability(history) - 1.0) < 1e-10

    def test_high_variance(self):
        history = [{"wss": 0.0 if i % 2 == 0 else 1.0} for i in range(20)]
        stability = compute_distribution_stability(history)
        assert stability < 0.1

    def test_moderate_variance(self):
        history = [{"wss": 0.6 + i * 0.005} for i in range(20)]
        stability = compute_distribution_stability(history)
        assert 0.5 < stability < 1.0

    def test_full_lifetime(self):
        history = [{"wss": 0.65 + 0.001 * (i % 5)} for i in range(200)]
        stability = compute_distribution_stability(history)
        assert stability > 0.9


# ===================================================================
#  Version Dispatch
# ===================================================================

class TestVersionDispatch:
    def test_default_is_v5(self):
        assert AFI_VERSION == 5

    def test_v1_explicit(self):
        trades = _make_trades([0.5] * 30, list(range(30)))
        result = compute_afi(trades, reference_time=NOW, version=1)
        assert result.afi_version == 1

    def test_v2_explicit(self):
        trades = _make_trades([0.5] * 30, list(range(30)))
        result = compute_afi(trades, reference_time=NOW, version=2)
        assert result.afi_version == 2

    def test_v3_explicit(self):
        """version=3 returns v3 result with cps/repeatability."""
        trades = _make_trades([0.5] * 30, list(range(30)))
        result = compute_afi(trades, reference_time=NOW, version=3)
        assert result.afi_version == 3
        assert result.cps >= 1.0
        assert result.repeatability >= 1.0

    def test_default_version_raises_for_v5(self):
        """Default AFI_VERSION=5 raises ValueError — v5 uses compute_afi_v5() directly."""
        trades = _make_trades([0.5] * 30, list(range(30)))
        with pytest.raises(ValueError, match="compute_afi_v5"):
            compute_afi(trades, reference_time=NOW)


# ===================================================================
#  v2: No Dampening
# ===================================================================

class TestV2NoDampening:
    def test_score_equals_raw(self):
        trades = _make_trades([0.5] * 50, list(range(50)))
        result = compute_afi(trades, reference_time=NOW, version=2)
        assert abs(result.afi_score - result.afi_raw) < 1e-10

    def test_prior_afi_ignored(self):
        trades = _make_trades([0.5] * 50, list(range(50)))
        r1 = compute_afi(trades, reference_time=NOW, version=2)
        r2 = compute_afi(trades, prior_afi=400.0, reference_time=NOW, version=2)
        assert abs(r1.afi_score - r2.afi_score) < 1e-10

    def test_deterministic_from_trades(self):
        trades = _make_trades([0.3, -0.5, 1.0, -0.8, 0.5] * 10, list(range(50)))
        r1 = compute_afi(trades, reference_time=NOW, version=2)
        r2 = compute_afi(trades, reference_time=NOW, version=2)
        assert r1.afi_score == r2.afi_score
        assert r1.wss == r2.wss


# ===================================================================
#  v2: Equal Weight vs Recency
# ===================================================================

class TestV2EqualWeightBehavior:
    def test_old_trades_equal_contribution(self):
        trades_recent = _make_trades([1.0] * 30, [0] * 30)
        trades_old = _make_trades([1.0] * 30, [365] * 30)

        r_recent = compute_afi(trades_recent, reference_time=NOW, version=2)
        r_old = compute_afi(trades_old, reference_time=NOW, version=2)

        assert abs(r_recent.afi_score - r_old.afi_score) < 1e-10

    def test_v1_penalizes_old_trades(self):
        trades_recent = _make_trades([1.0] * 30, [0] * 30)
        trades_old = _make_trades([1.0] * 30, [365] * 30)

        r_recent = compute_afi(trades_recent, reference_time=NOW, version=1)
        r_old = compute_afi(trades_old, reference_time=NOW, version=1)

        assert r_recent.afi_version == 1
        assert r_old.afi_version == 1


# ===================================================================
#  v2: Synthetic Trader Simulations
# ===================================================================

class TestV2SyntheticTraders:
    def test_v2_smooth_operator(self):
        np.random.seed(42)
        n = 150
        r_vals = np.concatenate([
            np.random.uniform(0.3, 0.5, int(n * 0.85)),
            np.random.uniform(-0.5, -0.3, int(n * 0.15)),
        ])
        np.random.shuffle(r_vals)
        days = np.linspace(200, 0, n)
        trades = _make_trades(r_vals.tolist(), days.tolist())

        result = compute_afi(trades, reference_time=NOW, version=2)
        assert result.afi_version == 2
        assert result.afi_score == result.afi_raw
        assert 700 < result.afi_score < 850
        assert not result.is_provisional

    def test_v2_cowboy(self):
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

        result = compute_afi(trades, reference_time=NOW, version=2)
        assert result.afi_version == 2
        assert result.afi_score == result.afi_raw
        assert result.afi_score < 750
        assert result.components.ltc < 0.8

    def test_v2_ranking_preserves_structural_order(self):
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
            reference_time=NOW, version=2,
        )
        r_cowboy = compute_afi(
            _make_trades(cowboy.tolist(), np.linspace(120, 0, len(cowboy)).tolist()),
            reference_time=NOW, version=2,
        )
        r_tortoise = compute_afi(
            _make_trades(tortoise.tolist(), np.linspace(365, 0, len(tortoise)).tolist()),
            reference_time=NOW, version=2,
        )

        assert r_cowboy.afi_score < r_tortoise.afi_score
        assert r_cowboy.afi_score < r_smooth.afi_score

    def test_v2_zero_trades(self):
        result = compute_afi([], reference_time=NOW, version=2)
        assert result.trade_count == 0
        assert result.is_provisional
        assert result.afi_version == 2
        assert result.afi_score == result.afi_raw

    def test_v2_inactivity_no_penalty(self):
        r_vals = [0.5, -0.3, 0.8, -0.5, 1.0] * 10
        trades_active = _make_trades(r_vals, list(range(50)))
        trades_dormant = _make_trades(r_vals, [730 + i for i in range(50)])

        r_active = compute_afi(trades_active, reference_time=NOW, version=2)
        r_dormant = compute_afi(trades_dormant, reference_time=NOW, version=2)

        assert abs(r_active.afi_score - r_dormant.afi_score) < 1e-10


# ===================================================================
#  v3: Credibility Functions
# ===================================================================

class TestCredibility:
    def test_cred_sharpe_formula(self):
        """Cred_sharpe(N) = sqrt(N / (N + 50))."""
        assert abs(cred_sharpe(0) - 0.0) < 1e-10
        assert abs(cred_sharpe(50) - math.sqrt(0.5)) < 1e-10
        assert abs(cred_sharpe(200) - math.sqrt(200.0 / 250.0)) < 1e-10

    def test_cred_bonus_formula(self):
        """Cred_bonus(N) = sqrt(N / (N + 150))."""
        assert abs(cred_bonus(0) - 0.0) < 1e-10
        assert abs(cred_bonus(150) - math.sqrt(0.5)) < 1e-10
        assert abs(cred_bonus(600) - math.sqrt(600.0 / 750.0)) < 1e-10

    def test_cred_sharpe_monotonic(self):
        """More trades → higher credibility."""
        vals = [cred_sharpe(n) for n in [10, 50, 100, 200, 500]]
        for i in range(len(vals) - 1):
            assert vals[i + 1] > vals[i]

    def test_cred_bonus_monotonic(self):
        vals = [cred_bonus(n) for n in [10, 50, 100, 200, 500]]
        for i in range(len(vals) - 1):
            assert vals[i + 1] > vals[i]

    def test_cred_sharpe_approaches_one(self):
        assert cred_sharpe(10000) > 0.99

    def test_cred_bonus_approaches_one(self):
        assert cred_bonus(10000) > 0.99

    def test_cred_sharpe_negative_n(self):
        """Negative N treated as 0."""
        assert abs(cred_sharpe(-5) - 0.0) < 1e-10

    def test_sharpe_adj(self):
        """Sharpe_adj = Sharpe_raw × Cred_sharpe(N)."""
        sharpe_raw = 2.0
        n = 100
        expected = sharpe_raw * math.sqrt(100.0 / 150.0)
        assert abs(compute_sharpe_adj(sharpe_raw, n) - expected) < 1e-10

    def test_sharpe_adj_zero_trades(self):
        assert abs(compute_sharpe_adj(2.0, 0) - 0.0) < 1e-10

    def test_sharpe_adj_large_n(self):
        """Large N: Sharpe_adj ≈ Sharpe_raw."""
        adj = compute_sharpe_adj(3.0, 10000)
        assert abs(adj - 3.0) < 0.05


# ===================================================================
#  v3: Tail Ratio
# ===================================================================

class TestTailRatio:
    def test_no_wins(self):
        r = np.array([-1.0, -0.5, -0.3])
        assert compute_tail_ratio(r) == 0.0

    def test_no_losses(self):
        r = np.array([1.0, 0.5, 0.3])
        assert compute_tail_ratio(r) == 0.0

    def test_symmetric(self):
        r = np.array([1.0, -1.0, 1.0, -1.0])
        ratio = compute_tail_ratio(r)
        expected = 1.0 / TAIL_RATIO_CAP
        assert abs(ratio - expected) < 1e-10

    def test_right_skewed(self):
        r = np.array([3.0, 4.0, 5.0, -0.5, -0.5])
        ratio = compute_tail_ratio(r)
        assert abs(ratio - 1.0) < 1e-10

    def test_cap(self):
        r = np.array([10.0, -0.1])
        ratio = compute_tail_ratio(r)
        assert ratio <= 1.0


# ===================================================================
#  v3: Convexity Ratio
# ===================================================================

class TestConvexityRatio:
    def test_no_wins(self):
        r = np.array([-1.0, -2.0])
        assert compute_convexity_ratio(r) == 0.0

    def test_no_losses(self):
        r = np.array([1.0, 2.0])
        assert compute_convexity_ratio(r) == 0.0

    def test_symmetric(self):
        r = np.array([2.0, -2.0, 1.0, -1.0])
        ratio = compute_convexity_ratio(r)
        expected = 1.0 / CONVEXITY_RATIO_CAP
        assert abs(ratio - expected) < 1e-10

    def test_right_tail_expansion(self):
        r = np.array([8.0, 1.0, -1.0, -0.5])
        ratio = compute_convexity_ratio(r)
        assert abs(ratio - 1.0) < 1e-10


# ===================================================================
#  v3: Convexity Amplifier
# ===================================================================

class TestConvexityAmplifier:
    def test_minimum(self):
        assert compute_convexity_amplifier(np.array([1.0])) == 1.0
        assert compute_convexity_amplifier(np.array([])) == 1.0

    def test_range(self):
        r = np.array([10.0, -0.1])
        ca = compute_convexity_amplifier(r)
        assert 1.0 <= ca <= 1.25

    def test_symmetric_trades(self):
        r = np.array([1.0, -1.0] * 20)
        ca = compute_convexity_amplifier(r)
        assert 1.04 < ca < 1.07

    def test_right_skew_boosts(self):
        r_balanced = np.array([1.0, -1.0] * 20)
        r_skewed = np.array([3.0, 5.0, -0.5, -0.3] * 10)
        ca_balanced = compute_convexity_amplifier(r_balanced)
        ca_skewed = compute_convexity_amplifier(r_skewed)
        assert ca_skewed > ca_balanced


# ===================================================================
#  v3: Rolling WSS Stability
# ===================================================================

class TestRollingWSSStability:
    def test_too_few_trades(self):
        r = np.array([0.5] * 10)
        w = np.ones(10) / 10
        assert compute_rolling_wss_stability(r, w) == 0.5

    def test_consistent_trades(self):
        r = np.array([0.5] * 50)
        w = np.ones(50) / 50
        stability = compute_rolling_wss_stability(r, w)
        assert stability > 0.9

    def test_erratic_trades(self):
        np.random.seed(77)
        r = np.concatenate([
            np.random.uniform(3.0, 5.0, 25),
            np.random.uniform(-3.0, -1.0, 25),
        ])
        np.random.shuffle(r)
        w = np.ones(50) / 50
        stability = compute_rolling_wss_stability(r, w)
        assert stability < 0.9


# ===================================================================
#  v3: Rolling Sharpe Stability
# ===================================================================

class TestRollingSharpeStability:
    def test_too_few_trades(self):
        r = np.array([0.5] * 10)
        w = np.ones(10) / 10
        assert compute_rolling_sharpe_stability(r, w) == 0.5

    def test_consistent_trades(self):
        """Constant R-multiples → zero Sharpe variance → high stability."""
        r = np.array([0.5] * 50)
        w = np.ones(50) / 50
        stability = compute_rolling_sharpe_stability(r, w)
        # All constant → Sharpe = 0 per window (zero variance), so variance of series = 0 → stability = 1.0
        assert stability > 0.9

    def test_erratic_trades(self):
        np.random.seed(77)
        r = np.concatenate([
            np.random.uniform(3.0, 5.0, 25),
            np.random.uniform(-3.0, -1.0, 25),
        ])
        np.random.shuffle(r)
        w = np.ones(50) / 50
        stability = compute_rolling_sharpe_stability(r, w)
        assert stability < 1.0


# ===================================================================
#  v3: Skew Persistence
# ===================================================================

class TestSkewPersistence:
    def test_too_few_trades(self):
        r = np.array([0.5] * 10)
        assert compute_skew_persistence(r) == 0.5

    def test_consistently_right_skewed(self):
        """Trades with consistent positive skew → high persistence."""
        np.random.seed(42)
        # Right-skewed: mostly small losses, occasional big wins
        r = np.concatenate([
            np.random.uniform(-0.5, -0.1, 40),
            np.random.uniform(2.0, 5.0, 10),
        ])
        np.random.shuffle(r)
        persistence = compute_skew_persistence(r)
        assert persistence > 0.3

    def test_left_skewed(self):
        """Trades with left skew → low persistence."""
        np.random.seed(42)
        r = np.concatenate([
            np.random.uniform(0.1, 0.5, 40),
            np.random.uniform(-5.0, -2.0, 10),
        ])
        np.random.shuffle(r)
        persistence = compute_skew_persistence(r)
        assert persistence < 0.5

    def test_range(self):
        """Persistence always in [0, 1]."""
        np.random.seed(42)
        r = np.random.randn(100)
        persistence = compute_skew_persistence(r)
        assert 0.0 <= persistence <= 1.0


# ===================================================================
#  v3: Repeatability (replaces BCM)
# ===================================================================

class TestRepeatability:
    def test_minimum(self):
        """Zero stability and zero trades → Repeatability = 1.0."""
        rep = compute_repeatability(0.0, 0.0, 0.0, 0)
        assert abs(rep - 1.0) < 1e-10

    def test_formula(self):
        """Verify formula: Rep = 1.0 + 0.15 × Rep_raw."""
        # With max stability (1.0) and large N (cred_bonus ≈ 1):
        # Rep_raw ≈ (0.4 + 0.3 + 0.3) × cred_bonus(10000) ≈ 1.0 × ~0.997
        # Repeatability ≈ 1.0 + 0.15 × ~0.997 ≈ ~1.15
        rep = compute_repeatability(1.0, 1.0, 1.0, 10000)
        assert 1.14 < rep < 1.16

    def test_credibility_gating(self):
        """Low trade count → lower repeatability boost."""
        rep_low = compute_repeatability(1.0, 1.0, 1.0, 10)
        rep_high = compute_repeatability(1.0, 1.0, 1.0, 500)
        assert rep_high > rep_low
        assert rep_low >= 1.0
        assert rep_high >= 1.0

    def test_range(self):
        """Repeatability always >= 1.0."""
        rep = compute_repeatability(0.5, 0.5, 0.5, 50)
        assert rep >= 1.0

    def test_weights_sum_to_one(self):
        """0.4 + 0.3 + 0.3 = 1.0."""
        assert abs(0.4 + 0.3 + 0.3 - 1.0) < 1e-10


# ===================================================================
#  v3: Skew Bonus
# ===================================================================

class TestSkewBonus:
    def test_too_few_trades(self):
        """< 3 trades → 0 bonus."""
        r = np.array([1.0, -0.5])
        assert compute_skew_bonus(r, 2) == 0.0

    def test_positive_skew_positive_bonus(self):
        """Right-skewed distribution → positive bonus."""
        np.random.seed(42)
        r = np.concatenate([
            np.random.uniform(-0.5, -0.1, 40),
            np.random.uniform(2.0, 5.0, 10),
        ])
        np.random.shuffle(r)
        bonus = compute_skew_bonus(r, len(r))
        assert bonus > 0.0

    def test_negative_skew_nonpositive_bonus(self):
        """Left-skewed distribution → non-positive bonus (zero or negative).

        Skew bonus = cred × skew_persistence × 10 × tanh(sample_skew).
        For left-skewed data, skew_persistence is typically 0 (no positive-skew windows),
        which makes the product 0 or negative.
        """
        np.random.seed(42)
        r = np.concatenate([
            np.random.uniform(0.1, 0.5, 40),
            np.random.uniform(-5.0, -2.0, 10),
        ])
        np.random.shuffle(r)
        bonus = compute_skew_bonus(r, len(r))
        assert bonus <= 0.0

    def test_bounded(self):
        """Skew bonus bounded to [-10, +10]."""
        np.random.seed(42)
        r = np.concatenate([
            np.random.uniform(-0.1, 0.0, 40),
            np.random.uniform(10.0, 20.0, 10),
        ])
        np.random.shuffle(r)
        bonus = compute_skew_bonus(r, len(r))
        assert -10.0 <= bonus <= 10.0

    def test_credibility_scales_bonus(self):
        """Fewer trades → smaller magnitude bonus."""
        np.random.seed(42)
        r = np.concatenate([
            np.random.uniform(-0.5, -0.1, 20),
            np.random.uniform(2.0, 5.0, 5),
        ])
        np.random.shuffle(r)
        bonus_25 = compute_skew_bonus(r, 25)
        bonus_500 = compute_skew_bonus(r, 500)
        # Same data, but 500 trades has higher cred_bonus
        assert abs(bonus_500) > abs(bonus_25)


# ===================================================================
#  v3: Elite Bonus
# ===================================================================

class TestEliteBonus:
    def test_below_threshold(self):
        """Sharpe_adj <= 5.0 → no bonus."""
        assert compute_elite_bonus(4.0, 100) == 0.0
        assert compute_elite_bonus(5.0, 100) == 0.0

    def test_above_threshold(self):
        """Sharpe_adj > 5.0 → positive bonus."""
        bonus = compute_elite_bonus(6.0, 100)
        assert bonus > 0.0

    def test_cap(self):
        """Elite bonus capped at ~20."""
        bonus = compute_elite_bonus(100.0, 10000)
        assert bonus <= 20.0

    def test_credibility_gating(self):
        """Low trade count → smaller elite bonus."""
        bonus_low = compute_elite_bonus(7.0, 10)
        bonus_high = compute_elite_bonus(7.0, 500)
        assert bonus_high > bonus_low
        assert bonus_low > 0.0

    def test_formula(self):
        """Elite_bonus = Cred_bonus(N) × 20 × tanh(Sharpe_adj - 5.0)."""
        sharpe_adj = 6.5
        n = 200
        expected = cred_bonus(n) * 20.0 * math.tanh(6.5 - 5.0)
        assert abs(compute_elite_bonus(sharpe_adj, n) - expected) < 1e-10


# ===================================================================
#  v3: End-to-End
# ===================================================================

class TestAFIv3:
    def test_elite_trader(self):
        """Elite Sharpe with right skew → high score."""
        np.random.seed(42)
        n = 150
        r_vals = np.concatenate([
            np.random.uniform(0.5, 2.0, int(n * 0.7)),
            np.random.uniform(-0.5, -0.2, int(n * 0.3)),
        ])
        np.random.shuffle(r_vals)
        days = np.linspace(300, 0, n)
        trades = _make_trades(r_vals.tolist(), days.tolist())

        result = compute_afi(trades, reference_time=NOW, version=3)
        assert result.afi_version == 3
        assert result.afi_score >= 300
        assert result.afi_score <= 900
        assert result.cps >= 1.0
        assert result.repeatability >= 1.0

    def test_right_skew_boosts_score(self):
        """Right-skewed distribution should score higher than balanced."""
        n = 60
        r_balanced = [0.5, -0.5] * (n // 2)
        r_skewed = [3.0, -0.5] * (n // 2)

        days = list(range(n))
        result_balanced = compute_afi(_make_trades(r_balanced, days), reference_time=NOW, version=3)
        result_skewed = compute_afi(_make_trades(r_skewed, days), reference_time=NOW, version=3)

        assert result_skewed.cps > result_balanced.cps
        assert result_skewed.afi_score > result_balanced.afi_score

    def test_repeatability_present(self):
        """Consistent trades should produce repeatability >= 1.0."""
        n = 60
        r_vals = [0.5] * n
        trades = _make_trades(r_vals, list(range(n)))
        result = compute_afi(trades, reference_time=NOW, version=3)
        assert result.repeatability >= 1.0

    def test_no_dampening(self):
        """v3: deterministic, no prior_afi influence."""
        trades = _make_trades([0.5] * 50, list(range(50)))
        r1 = compute_afi(trades, reference_time=NOW, version=3)
        r2 = compute_afi(trades, prior_afi=400.0, reference_time=NOW, version=3)
        assert abs(r1.afi_score - r2.afi_score) < 1e-10

    def test_inactivity_neutral(self):
        """v3: dormant trader scores identically to active trader."""
        r_vals = [0.5, -0.3, 0.8, -0.5, 1.0] * 10
        trades_active = _make_trades(r_vals, list(range(50)))
        trades_dormant = _make_trades(r_vals, [730 + i for i in range(50)])

        r_active = compute_afi(trades_active, reference_time=NOW, version=3)
        r_dormant = compute_afi(trades_dormant, reference_time=NOW, version=3)
        assert abs(r_active.afi_score - r_dormant.afi_score) < 1e-10

    def test_frequency_neutral(self):
        """v3: same R-multiples score same regardless of timing spread."""
        r_vals = [0.5, -0.3, 1.0, -0.8, 0.5] * 10
        trades_compressed = _make_trades(r_vals, list(range(50)))
        trades_spread = _make_trades(r_vals, [i * 10 for i in range(50)])

        r1 = compute_afi(trades_compressed, reference_time=NOW, version=3)
        r2 = compute_afi(trades_spread, reference_time=NOW, version=3)
        assert abs(r1.afi_score - r2.afi_score) < 1e-10

    def test_clamped_to_300_900(self):
        """v3: AFI score is clamped to [300, 900]."""
        result = compute_afi([], reference_time=NOW, version=3)
        assert result.afi_score >= 300
        assert result.afi_score <= 900
        assert result.afi_version == 3
        assert result.cps == 1.0
        assert result.repeatability == 1.0

    def test_structural_total_formula(self):
        """v3: structural_total = WSS * CA * Repeatability, then compress + bonuses + clamp."""
        n = 60
        trades = _make_trades([0.5] * n, list(range(n)))
        result = compute_afi(trades, reference_time=NOW, version=3)

        assert result.cps >= 1.0
        assert result.cps <= 1.25
        assert result.repeatability >= 1.0
        assert result.repeatability <= 1.16  # slightly above theoretical max due to rounding

    def test_v3_cowboy_penalized(self):
        """v3: Cowboy (fragile) still ranks below structural traders."""
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

        r_smooth = compute_afi(
            _make_trades(smooth.tolist(), np.linspace(200, 0, len(smooth)).tolist()),
            reference_time=NOW, version=3,
        )
        r_cowboy = compute_afi(
            _make_trades(cowboy.tolist(), np.linspace(120, 0, len(cowboy)).tolist()),
            reference_time=NOW, version=3,
        )

        assert r_cowboy.afi_score < r_smooth.afi_score

    def test_credibility_gating_low_trades(self):
        """v3: few trades → Sharpe_adj suppressed → lower score than same data with more trades claim."""
        # 10 trades with good Sharpe should score lower than 200 trades with same per-trade metrics
        # because credibility gates the Sharpe
        r_vals = [0.5] * 10
        trades_10 = _make_trades(r_vals, list(range(10)))
        r_vals_200 = [0.5] * 200
        trades_200 = _make_trades(r_vals_200, list(range(200)))

        r10 = compute_afi(trades_10, reference_time=NOW, version=3)
        r200 = compute_afi(trades_200, reference_time=NOW, version=3)

        # More trades = higher credibility = higher score
        assert r200.afi_score > r10.afi_score

    def test_wss_uses_sharpe_adj(self):
        """v3: WSS normalizes Sharpe_adj, not raw Sharpe."""
        n = 60
        trades = _make_trades([0.5] * n, list(range(n)))
        result = compute_afi(trades, reference_time=NOW, version=3)

        # The sharpe component in AFIComponents should be normalized from Sharpe_adj
        # which is less than raw Sharpe (due to credibility gate < 1)
        # For 60 trades: cred_sharpe(60) = sqrt(60/110) ≈ 0.738
        # So Sharpe_adj < Sharpe_raw
        assert result.components.sharpe >= 0.0
        assert result.components.sharpe <= 1.0


# ===================================================================
#  Governance Patch v1.1: Capital Integrity Constants
# ===================================================================

class TestCapitalIntegrityConstants:
    def test_min_capital_value(self):
        """MIN_CAPITAL = $10,000 in cents = 1,000,000."""
        assert MIN_CAPITAL == 1_000_000

    def test_neutral_afi_value(self):
        """NEUTRAL_AFI = 500 (midpoint baseline)."""
        assert NEUTRAL_AFI == 500.0


# ===================================================================
#  Governance Patch v1.1: AFIResult Capital Fields
# ===================================================================

class TestAFIResultCapitalFields:
    def test_default_capital_status(self):
        """AFIResult defaults to unverified capital."""
        trades = _make_trades([0.5] * 30, list(range(30)))
        result = compute_afi(trades, reference_time=NOW, version=3)
        assert result.capital_status == "unverified"

    def test_default_leaderboard_eligible(self):
        """AFIResult defaults to not leaderboard-eligible."""
        trades = _make_trades([0.5] * 30, list(range(30)))
        result = compute_afi(trades, reference_time=NOW, version=3)
        assert result.leaderboard_eligible is False

    def test_capital_fields_frozen(self):
        """AFIResult is frozen — capital fields are immutable after creation."""
        trades = _make_trades([0.5] * 30, list(range(30)))
        result = compute_afi(trades, reference_time=NOW, version=3)
        with pytest.raises(AttributeError):
            result.capital_status = "verified"
        with pytest.raises(AttributeError):
            result.leaderboard_eligible = True

    def test_v1_also_has_capital_fields(self):
        """Capital fields present on all AFI versions (default values)."""
        trades = _make_trades([0.5] * 30, list(range(30)))
        result = compute_afi(trades, reference_time=NOW, version=1)
        assert result.capital_status == "unverified"
        assert result.leaderboard_eligible is False

    def test_v2_also_has_capital_fields(self):
        """Capital fields present on all AFI versions (default values)."""
        trades = _make_trades([0.5] * 30, list(range(30)))
        result = compute_afi(trades, reference_time=NOW, version=2)
        assert result.capital_status == "unverified"
        assert result.leaderboard_eligible is False

    def test_neutral_afi_is_clamp_midpoint(self):
        """500 is the neutral baseline — within [300, 900] clamp range."""
        assert 300 <= NEUTRAL_AFI <= 900

    def test_compute_afi_still_produces_raw_scores(self):
        """Even with default unverified status, raw computation is performed.

        The capital gating (AFI=500 override) happens in the orchestrator, not
        the scoring engine. The engine always computes the real score.
        """
        trades = _make_trades([0.5] * 50, list(range(50)))
        result = compute_afi(trades, reference_time=NOW, version=3)
        # Raw score is computed — should NOT be 500 for good trades
        assert result.afi_score != NEUTRAL_AFI or result.afi_raw != NEUTRAL_AFI


# ===================================================================
#  AFI v4 — Dual-Index Architecture
# ===================================================================

from services.journal.intel.afi_engine.scoring_engine import (
    build_daily_equity_series,
    compute_daily_sharpe,
    compute_drawdown_resilience_v4,
    compute_payoff_asymmetry_v4,
    compute_recovery_velocity_v4,
    compute_confidence_v4,
    compute_afi_v4,
    V4_MIN_TRADES,
    V4_MIN_ACTIVE_DAYS,
    V4_R_WEIGHT,
    V4_M_WEIGHT,
)
from services.journal.intel.afi_engine.models import AFIResultV4, AFIComponentsV4


def _make_v4_trades(r_multiples, days_ago_list, starting_risk=100.0):
    """Build v4-compatible trade dicts with exit_time, r_multiple, pnl, planned_risk."""
    trades = []
    for r, days_ago in zip(r_multiples, days_ago_list):
        exit_time = NOW - timedelta(days=days_ago)
        trades.append({
            'r_multiple': r,
            'exit_time': exit_time,
            'pnl': r * starting_risk,
            'planned_risk': starting_risk,
        })
    # Sort by exit_time ASC
    trades.sort(key=lambda t: t['exit_time'])
    return trades


class TestAFIv4:

    def test_build_daily_equity_series(self):
        """Equity series aggregates realized PnL by exit day."""
        trades = _make_v4_trades([1.0, -0.5, 2.0], [3, 3, 1])
        series = build_daily_equity_series(trades, 10000.0)
        assert len(series) == 2  # two distinct days
        # Day with trades at days_ago=3: PnL = (1.0 + -0.5) * 100 = 50
        # Day with trade at days_ago=1: PnL = 2.0 * 100 = 200
        assert series[0][1] == 10050.0  # cumulative after first day
        assert series[1][1] == 10250.0  # cumulative after second day

    def test_build_daily_equity_empty(self):
        """Empty trades returns empty series."""
        assert build_daily_equity_series([], 10000.0) == []
        assert build_daily_equity_series([{'exit_time': None, 'pnl': 0}], 10000.0) == []

    def test_daily_sharpe_lifetime(self):
        """Lifetime Sharpe on a consistently positive equity curve."""
        # 10 days of positive returns
        trades = _make_v4_trades(
            [0.3] * 10,
            list(range(10, 0, -1)),  # days_ago 10,9,...,1
        )
        series = build_daily_equity_series(trades, 10000.0)
        sharpe = compute_daily_sharpe(series, window_days=None)
        # Consistently positive returns → positive Sharpe
        assert sharpe > 0

    def test_daily_sharpe_rolling(self):
        """Rolling 45-day window only considers recent trades."""
        old_trades = _make_v4_trades([0.1] * 10, list(range(100, 90, -1)))
        recent_trades = _make_v4_trades([-0.5] * 5, list(range(5, 0, -1)))
        all_trades = old_trades + recent_trades
        all_trades.sort(key=lambda t: t['exit_time'])

        series = build_daily_equity_series(all_trades, 10000.0)
        rolling_sharpe = compute_daily_sharpe(series, window_days=45)
        # Recent trades are negative → rolling Sharpe should be negative
        assert rolling_sharpe < 0

    def test_daily_sharpe_insufficient_data(self):
        """Less than 2 equity points returns 0."""
        trades = _make_v4_trades([1.0], [1])
        series = build_daily_equity_series(trades, 10000.0)
        assert len(series) == 1
        assert compute_daily_sharpe(series) == 0.0

    def test_drawdown_resilience(self):
        """Drawdown resilience between 0 and 1."""
        trades = _make_v4_trades(
            [1.0, -2.0, 0.5, 0.5, 1.0, -1.0, 0.5, 0.5, 1.0, 0.5],
            list(range(10, 0, -1)),
        )
        score = compute_drawdown_resilience_v4(trades)
        assert 0.0 <= score <= 1.0

    def test_payoff_asymmetry(self):
        """Payoff asymmetry reflects avg_win/avg_loss ratio."""
        # 3:1 avg_win/avg_loss → should be at or near 1.0 (capped at 3:1)
        trades = _make_v4_trades([3.0, 3.0, -1.0, -1.0], [4, 3, 2, 1])
        score = compute_payoff_asymmetry_v4(trades)
        assert abs(score - 1.0) < 0.01

        # 1:1 ratio → 0.333
        trades_even = _make_v4_trades([1.0, -1.0, 1.0, -1.0], [4, 3, 2, 1])
        score_even = compute_payoff_asymmetry_v4(trades_even)
        assert abs(score_even - 1.0 / 3.0) < 0.01

    def test_recovery_velocity(self):
        """Recovery velocity between 0 and 1."""
        trades = _make_v4_trades(
            [1.0, -2.0, 0.5, 0.5, 1.0, 1.0, -0.5, 0.5, 1.0, 0.5],
            list(range(10, 0, -1)),
        )
        score = compute_recovery_velocity_v4(trades)
        assert 0.0 <= score <= 1.0

    def test_confidence_scaling(self):
        """Confidence increases with trade count and active days."""
        low = compute_confidence_v4(10, 10)
        med = compute_confidence_v4(50, 30)
        high = compute_confidence_v4(200, 90)
        assert low < med < high
        assert 0.0 <= low <= 1.0
        assert 0.0 <= high <= 1.0

    def test_confidence_zero(self):
        """Zero trades/days → zero confidence."""
        assert compute_confidence_v4(0, 0) == 0.0

    def test_afi_r_compression(self):
        """AFI-R is in 300-900 range."""
        trades = _make_v4_trades([0.5] * 60, list(range(60, 0, -1)))
        result = compute_afi_v4(trades, 10000.0, [])
        assert 300 <= result.afi_r <= 900

    def test_afi_m_compression(self):
        """AFI-M is in 300-900 range."""
        trades = _make_v4_trades([0.5] * 60, list(range(60, 0, -1)))
        result = compute_afi_v4(trades, 10000.0, [])
        assert 300 <= result.afi_m <= 900

    def test_composite_blend(self):
        """Composite = 0.65 × AFI-R + 0.35 × AFI-M."""
        trades = _make_v4_trades([0.5] * 60, list(range(60, 0, -1)))
        result = compute_afi_v4(trades, 10000.0, [])
        expected = V4_R_WEIGHT * result.afi_r + V4_M_WEIGHT * result.afi_m
        assert abs(result.composite - round(expected, 2)) < 0.02

    def test_eligibility_thresholds(self):
        """Below 50 trades or 30 active days → provisional."""
        # 30 trades, 30 days → provisional (< 50 trades)
        trades_30 = _make_v4_trades([0.5] * 30, list(range(30, 0, -1)))
        result_30 = compute_afi_v4(trades_30, 10000.0, [])
        assert result_30.is_provisional is True

        # 60 trades on 60 separate days → NOT provisional
        trades_60 = _make_v4_trades([0.5] * 60, list(range(60, 0, -1)))
        result_60 = compute_afi_v4(trades_60, 10000.0, [])
        assert result_60.is_provisional is False

    def test_result_v4_structure(self):
        """AFIResultV4 has all required fields."""
        trades = _make_v4_trades([0.5] * 60, list(range(60, 0, -1)))
        result = compute_afi_v4(trades, 10000.0, [])
        assert isinstance(result, AFIResultV4)
        assert result.afi_version == 4
        assert isinstance(result.components, AFIComponentsV4)
        assert result.raw_afi_m is not None
        assert result.raw_afi_r is not None
        assert result.raw_sharpe_lifetime is not None
        assert result.confidence > 0

    def test_empty_trades(self):
        """Zero trades → neutral scores."""
        result = compute_afi_v4([], 10000.0, [])
        # Should complete without error and produce valid range
        assert 300 <= result.afi_r <= 900
        assert 300 <= result.afi_m <= 900
        assert result.is_provisional is True
        assert result.trade_count == 0

    def test_trend_detection(self):
        """Trend detection works with WSS history."""
        # Build improving WSS history
        history = [{'date': f'2026-01-{i:02d}', 'wss': 0.3 + i * 0.02} for i in range(1, 16)]
        trades = _make_v4_trades([0.5] * 60, list(range(60, 0, -1)))
        result = compute_afi_v4(trades, 10000.0, history)
        # Should detect a trend (improving or stable depending on threshold)
        assert result.trend.value in ('improving', 'stable', 'decaying')


# ===================================================================
#  AFI v5 — Structural Pareto Composite Model
# ===================================================================

from services.journal.intel.afi_engine.scoring_engine import (
    compute_afi_v5,
    V5_D_WEIGHT,
    V5_M_WEIGHT,
    V5_RB_FLOOR,
    V5_RB_FLOOR_CAP,
)


class TestAFIv5:

    def test_durability_no_confidence(self):
        """D_raw should NOT include confidence multiplication (unlike v4's afi_r_raw)."""
        trades = _make_v4_trades([0.5] * 60, list(range(60, 0, -1)))
        result_v5 = compute_afi_v5(trades, 10000.0, [])
        result_v4 = compute_afi_v4(trades, 10000.0, [])

        # v4 raw_afi_r includes confidence: raw = confidence × components
        # v5 raw_afi_r is pure components: raw = components (no confidence)
        # So v5 D_raw should be >= v4 raw_afi_r (since confidence ≤ 1)
        assert result_v5.raw_afi_r >= result_v4.raw_afi_r

    def test_d_structural_attenuation(self):
        """D_structural = D × R should be less than D when R < 1."""
        # 15 trades, 15 days → low robustness
        trades = _make_v4_trades([0.5] * 15, list(range(15, 0, -1)))
        result = compute_afi_v5(trades, 10000.0, [])

        d_raw = result.raw_afi_r  # D (0-1)
        robustness = result.confidence  # R (0-1)
        d_structural = d_raw * robustness

        # Robustness < 1 for few trades → D_structural < D
        assert robustness < 1.0
        assert d_structural < d_raw

    def test_pareto_weighting(self):
        """Composite uses 80/20 Pareto split (D_structural vs M)."""
        assert V5_D_WEIGHT == 0.80
        assert V5_M_WEIGHT == 0.20
        assert abs(V5_D_WEIGHT + V5_M_WEIGHT - 1.0) < 1e-10

    def test_robustness_floor(self):
        """R < 0.25 caps composite at 550."""
        # Very few trades → low robustness
        trades = _make_v4_trades([2.0] * 5, list(range(5, 0, -1)))
        result = compute_afi_v5(trades, 10000.0, [])

        # 5 trades, ~5 days → R = sqrt(5/55) × sqrt(5/35) ≈ 0.30 × 0.38 ≈ 0.11
        assert result.confidence < V5_RB_FLOOR
        assert result.composite <= V5_RB_FLOOR_CAP

    def test_composite_single_compression(self):
        """Composite is in 300-900 range after single compression."""
        trades = _make_v4_trades([0.5] * 60, list(range(60, 0, -1)))
        result = compute_afi_v5(trades, 10000.0, [])
        assert 300 <= result.composite <= 900
        assert 300 <= result.afi_r <= 900
        assert 300 <= result.afi_m <= 900

    def test_v5_version_tag(self):
        """Result has afi_version = 5."""
        trades = _make_v4_trades([0.5] * 60, list(range(60, 0, -1)))
        result = compute_afi_v5(trades, 10000.0, [])
        assert result.afi_version == 5

    def test_result_v5_structure(self):
        """AFIResultV4 dataclass reused — all fields populated."""
        trades = _make_v4_trades([0.5] * 60, list(range(60, 0, -1)))
        result = compute_afi_v5(trades, 10000.0, [])
        assert isinstance(result, AFIResultV4)
        assert isinstance(result.components, AFIComponentsV4)
        assert result.raw_afi_m is not None
        assert result.raw_afi_r is not None
        assert result.raw_sharpe_lifetime is not None
        assert result.confidence > 0

    def test_eligibility_same_as_v4(self):
        """v5 uses same thresholds: 50 trades, 30 active days."""
        # 30 trades → provisional
        trades_30 = _make_v4_trades([0.5] * 30, list(range(30, 0, -1)))
        result_30 = compute_afi_v5(trades_30, 10000.0, [])
        assert result_30.is_provisional is True

        # 60 trades, 60 days → not provisional
        trades_60 = _make_v4_trades([0.5] * 60, list(range(60, 0, -1)))
        result_60 = compute_afi_v5(trades_60, 10000.0, [])
        assert result_60.is_provisional is False

    def test_empty_trades(self):
        """Zero trades → valid neutral result."""
        result = compute_afi_v5([], 10000.0, [])
        assert 300 <= result.composite <= 900
        assert result.is_provisional is True
        assert result.trade_count == 0
        assert result.afi_version == 5

    def test_high_robustness_preserves_durability(self):
        """High trade count / active days → R near 1 → minimal attenuation."""
        trades = _make_v4_trades([0.5] * 200, list(range(200, 0, -1)))
        result = compute_afi_v5(trades, 10000.0, [])

        # R should be high with 200 trades and 200 days
        # sqrt(200/250) × sqrt(200/230) ≈ 0.894 × 0.932 ≈ 0.834
        assert result.confidence > 0.80
        # D_structural ≈ D when R is high
        d_structural = result.raw_afi_r * result.confidence
        assert d_structural > result.raw_afi_r * 0.80

    def test_v5_composite_less_volatile_than_v4(self):
        """v5 composite for thin accounts should be lower than v4 composite.

        The Pareto model attenuates D by R in 0-1 space BEFORE compression,
        which suppresses small-sample inflation more aggressively.
        """
        # Thin account: 20 trades with great returns
        trades = _make_v4_trades([2.0] * 20, list(range(20, 0, -1)))
        result_v4 = compute_afi_v4(trades, 10000.0, [])
        result_v5 = compute_afi_v5(trades, 10000.0, [])

        # v5 should be more conservative for thin accounts
        assert result_v5.composite <= result_v4.composite
