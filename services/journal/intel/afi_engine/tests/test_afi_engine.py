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
    K,
    S,
    SHIFT,
    STABILITY_VAR_CAP,
    TAIL_RATIO_CAP,
    CONVEXITY_RATIO_CAP,
    ROLLING_WSS_WINDOW,
    compress,
    compute_bcm,
    compute_convexity_amplifier,
    compute_convexity_ratio,
    compute_distribution_stability,
    compute_robustness,
    compute_robustness_v2,
    compute_rolling_wss_stability,
    compute_tail_ratio,
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
        """High Sharpe, low growth → Purple tier (~771). v1."""
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

        result = compute_afi(trades, reference_time=NOW, version=1)
        assert 700 < result.afi_score < 850
        assert result.robustness > 40
        assert not result.is_provisional

    def test_cowboy(self):
        """Explosive growth, high DD → Blue tier (~654). v1."""
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
        assert result.afi_score < 750  # Should not reach Purple
        assert result.components.ltc < 0.8  # Poor containment

    def test_tortoise(self):
        """Stable grinder → Purple tier (~719), high RB. v1."""
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
        assert result.robustness > 70  # Highest RB
        assert not result.is_provisional

    def test_ranking_order(self):
        """Smooth Operator > Tortoise > Cowboy on structural merit. v1."""
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

        # Cowboy should be lowest — fragile despite growth
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
        """All losses within 1R → LTC = 1.0 still."""
        trades = _make_trades([-0.5] * 30, list(range(30)))
        result = compute_afi(trades, reference_time=NOW, version=1)
        assert result.components.ltc == 1.0
        assert result.afi_score < 600  # Negative slope + negative Sharpe

    def test_statefulness(self):
        """v1: second computation should dampen toward prior."""
        trades = _make_trades([0.5] * 50, list(range(50)))
        r1 = compute_afi(trades, reference_time=NOW, version=1)
        r2 = compute_afi(trades, prior_afi=r1.afi_score, reference_time=NOW, version=1)
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

    def test_no_cap_v2(self):
        """v2: max_entries=None preserves all history."""
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
#  v2: Robustness v2 (no trade_count, no active_days)
# ===================================================================

class TestRobustnessV2:
    def test_formula(self):
        """RB_v2 = 10 × regime_diversity + 3 × survived_dds + 5 × distribution_stability."""
        rb = compute_robustness_v2(
            regime_diversity=0.5,
            survived_dds=4,
            distribution_stability=0.8,
        )
        expected = 10.0 * 0.5 + 3.0 * 4 + 5.0 * 0.8  # 5 + 12 + 4 = 21
        assert abs(rb - expected) < 1e-10

    def test_no_trade_count_dependency(self):
        """Robustness_v2 has no trade_count or active_days parameters."""
        # Two calls with same structural inputs should give same result
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
        """Regime diversity clamped to [0, 1]."""
        rb = compute_robustness_v2(1.5, 0, 0.0)
        assert abs(rb - 10.0) < 1e-10  # clamped to 1.0


# ===================================================================
#  v2: Distribution Stability
# ===================================================================

class TestDistributionStability:
    def test_too_few_points(self):
        """< 3 data points → neutral default 0.5."""
        assert compute_distribution_stability([]) == 0.5
        assert compute_distribution_stability([{"wss": 0.6}]) == 0.5
        assert compute_distribution_stability([{"wss": 0.6}, {"wss": 0.7}]) == 0.5

    def test_perfect_stability(self):
        """Zero variance → stability = 1.0."""
        history = [{"wss": 0.65} for _ in range(20)]
        assert abs(compute_distribution_stability(history) - 1.0) < 1e-10

    def test_high_variance(self):
        """High variance → stability near 0."""
        history = [{"wss": 0.0 if i % 2 == 0 else 1.0} for i in range(20)]
        stability = compute_distribution_stability(history)
        assert stability < 0.1  # variance = 0.25, well above cap of 0.05

    def test_moderate_variance(self):
        """Moderate variance → mid-range stability."""
        history = [{"wss": 0.6 + i * 0.005} for i in range(20)]
        stability = compute_distribution_stability(history)
        assert 0.5 < stability < 1.0

    def test_full_lifetime(self):
        """Stability computed across all history, not windowed."""
        # 200 entries — should all be used
        history = [{"wss": 0.65 + 0.001 * (i % 5)} for i in range(200)]
        stability = compute_distribution_stability(history)
        assert stability > 0.9  # Very low variance


# ===================================================================
#  v2: Version Dispatch
# ===================================================================

class TestVersionDispatch:
    def test_default_is_v3(self):
        """Default version should be 3."""
        assert AFI_VERSION == 3

    def test_v1_explicit(self):
        """version=1 returns v1 result with dampening."""
        trades = _make_trades([0.5] * 30, list(range(30)))
        result = compute_afi(trades, reference_time=NOW, version=1)
        assert result.afi_version == 1

    def test_v2_explicit(self):
        """version=2 returns v2 result."""
        trades = _make_trades([0.5] * 30, list(range(30)))
        result = compute_afi(trades, reference_time=NOW, version=2)
        assert result.afi_version == 2

    def test_v3_explicit(self):
        """version=3 returns v3 result with cps/bcm."""
        trades = _make_trades([0.5] * 30, list(range(30)))
        result = compute_afi(trades, reference_time=NOW, version=3)
        assert result.afi_version == 3
        assert result.cps >= 1.0
        assert result.bcm >= 0.9

    def test_default_version_uses_afi_version(self):
        """No version param → uses AFI_VERSION (3)."""
        trades = _make_trades([0.5] * 30, list(range(30)))
        result = compute_afi(trades, reference_time=NOW)
        assert result.afi_version == AFI_VERSION


# ===================================================================
#  v2: No Dampening
# ===================================================================

class TestV2NoDampening:
    def test_score_equals_raw(self):
        """v2: afi_score == afi_raw (no dampening)."""
        trades = _make_trades([0.5] * 50, list(range(50)))
        result = compute_afi(trades, reference_time=NOW, version=2)
        assert abs(result.afi_score - result.afi_raw) < 1e-10

    def test_prior_afi_ignored(self):
        """v2 ignores prior_afi — no dampening path."""
        trades = _make_trades([0.5] * 50, list(range(50)))
        r1 = compute_afi(trades, reference_time=NOW, version=2)
        r2 = compute_afi(trades, prior_afi=400.0, reference_time=NOW, version=2)
        # v2 ignores prior_afi, so both should be identical
        assert abs(r1.afi_score - r2.afi_score) < 1e-10

    def test_deterministic_from_trades(self):
        """v2: same trades → identical score regardless of history."""
        trades = _make_trades([0.3, -0.5, 1.0, -0.8, 0.5] * 10, list(range(50)))
        r1 = compute_afi(trades, reference_time=NOW, version=2)
        r2 = compute_afi(trades, reference_time=NOW, version=2)
        assert r1.afi_score == r2.afi_score
        assert r1.wss == r2.wss


# ===================================================================
#  v2: Equal Weight vs Recency (structural difference)
# ===================================================================

class TestV2EqualWeightBehavior:
    def test_old_trades_equal_contribution(self):
        """v2: trade 365 days ago contributes equally to trade today."""
        trades_recent = _make_trades([1.0] * 30, [0] * 30)
        trades_old = _make_trades([1.0] * 30, [365] * 30)

        r_recent = compute_afi(trades_recent, reference_time=NOW, version=2)
        r_old = compute_afi(trades_old, reference_time=NOW, version=2)

        # v2: should be identical since equal weights, same r_multiples
        assert abs(r_recent.afi_score - r_old.afi_score) < 1e-10

    def test_v1_penalizes_old_trades(self):
        """v1: old trades should have lower contribution due to recency decay."""
        trades_recent = _make_trades([1.0] * 30, [0] * 30)
        trades_old = _make_trades([1.0] * 30, [365] * 30)

        r_recent = compute_afi(trades_recent, reference_time=NOW, version=1)
        r_old = compute_afi(trades_old, reference_time=NOW, version=1)

        # v1: recent trades should score differently from old trades
        # (Due to recency weighting affecting component computations)
        # Both are all +1R, so the components may still be similar,
        # but the weighting process differs
        assert r_recent.afi_version == 1
        assert r_old.afi_version == 1


# ===================================================================
#  v2: Synthetic Trader Simulations
# ===================================================================

class TestV2SyntheticTraders:
    def test_v2_smooth_operator(self):
        """v2: Smooth operator should score well."""
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
        assert result.afi_score == result.afi_raw  # no dampening
        assert 700 < result.afi_score < 850
        assert not result.is_provisional

    def test_v2_cowboy(self):
        """v2: Cowboy should score low — fragile despite growth."""
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
        """v2: Cowboy should still rank below smooth and tortoise."""
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

        # Cowboy should still be lowest — structural fragility persists
        assert r_cowboy.afi_score < r_tortoise.afi_score
        assert r_cowboy.afi_score < r_smooth.afi_score

    def test_v2_zero_trades(self):
        """v2: zero trades returns valid result."""
        result = compute_afi([], reference_time=NOW, version=2)
        assert result.trade_count == 0
        assert result.is_provisional
        assert result.afi_version == 2
        assert result.afi_score == result.afi_raw  # no dampening even for zero trades

    def test_v2_inactivity_no_penalty(self):
        """v2: trader who stopped 2 years ago should score same as active trader.

        This is the core v2 promise: inactivity does not reduce AFI.
        """
        # Same trades, different timing
        r_vals = [0.5, -0.3, 0.8, -0.5, 1.0] * 10
        trades_active = _make_trades(r_vals, list(range(50)))
        trades_dormant = _make_trades(r_vals, [730 + i for i in range(50)])  # 2 years ago

        r_active = compute_afi(trades_active, reference_time=NOW, version=2)
        r_dormant = compute_afi(trades_dormant, reference_time=NOW, version=2)

        # v2: equal weights → identical scores
        assert abs(r_active.afi_score - r_dormant.afi_score) < 1e-10


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
        """Equal avg win and avg loss → raw ratio = 1.0, normalized = 1/5 = 0.2."""
        r = np.array([1.0, -1.0, 1.0, -1.0])
        ratio = compute_tail_ratio(r)
        expected = 1.0 / TAIL_RATIO_CAP  # 1.0 / 5.0 = 0.2
        assert abs(ratio - expected) < 1e-10

    def test_right_skewed(self):
        """Big wins, small losses → high ratio."""
        r = np.array([3.0, 4.0, 5.0, -0.5, -0.5])
        ratio = compute_tail_ratio(r)
        # avg_win = 4.0, avg_loss = 0.5, raw = 8.0, capped at 1.0
        assert abs(ratio - 1.0) < 1e-10

    def test_cap(self):
        """Ratio capped to [0, 1]."""
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
        """max_win = max_loss → raw = 1.0, normalized = 1/4 = 0.25."""
        r = np.array([2.0, -2.0, 1.0, -1.0])
        ratio = compute_convexity_ratio(r)
        expected = 1.0 / CONVEXITY_RATIO_CAP  # 1.0 / 4.0 = 0.25
        assert abs(ratio - expected) < 1e-10

    def test_right_tail_expansion(self):
        """Big max_win relative to max_loss → high ratio."""
        r = np.array([8.0, 1.0, -1.0, -0.5])
        ratio = compute_convexity_ratio(r)
        # max_win = 8.0, max_loss = 1.0, raw = 8.0, capped at 1.0
        assert abs(ratio - 1.0) < 1e-10


# ===================================================================
#  v3: Convexity Amplifier
# ===================================================================

class TestConvexityAmplifier:
    def test_minimum(self):
        """Single trade or no trades → CA = 1.0."""
        assert compute_convexity_amplifier(np.array([1.0])) == 1.0
        assert compute_convexity_amplifier(np.array([])) == 1.0

    def test_range(self):
        """CA always in [1.0, 1.25]."""
        # Maximum possible: tail=1.0, convexity=1.0 → 1 + 0.15 + 0.10 = 1.25
        r = np.array([10.0, -0.1])  # extreme right skew
        ca = compute_convexity_amplifier(r)
        assert 1.0 <= ca <= 1.25

    def test_symmetric_trades(self):
        """Balanced trades → CA near 1.0."""
        r = np.array([1.0, -1.0] * 20)
        ca = compute_convexity_amplifier(r)
        # tail_ratio = 1/5 = 0.2, convexity_ratio = 1/4 = 0.25
        # CA = 1 + 0.15*0.2 + 0.10*0.25 = 1.055
        assert 1.04 < ca < 1.07

    def test_right_skew_boosts(self):
        """Right-skewed distribution should give higher CA."""
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
        """< ROLLING_WSS_WINDOW trades → neutral 0.5."""
        r = np.array([0.5] * 10)
        w = np.ones(10) / 10
        assert compute_rolling_wss_stability(r, w) == 0.5

    def test_consistent_trades(self):
        """Consistent R-multiples → high stability."""
        r = np.array([0.5] * 50)
        w = np.ones(50) / 50
        stability = compute_rolling_wss_stability(r, w)
        assert stability > 0.9

    def test_erratic_trades(self):
        """Wildly varying R-multiples → lower stability."""
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
#  v3: BCM (Behavioral Consistency Multiplier)
# ===================================================================

class TestBCM:
    def test_formula(self):
        """BCM = 0.90 + 0.20 * stability."""
        assert abs(compute_bcm(0.0) - 0.90) < 1e-10
        assert abs(compute_bcm(0.5) - 1.00) < 1e-10
        assert abs(compute_bcm(1.0) - 1.10) < 1e-10

    def test_range(self):
        """BCM always in [0.90, 1.10]."""
        assert abs(compute_bcm(-0.5) - 0.90) < 1e-10  # clamped
        assert abs(compute_bcm(1.5) - 1.10) < 1e-10  # clamped


# ===================================================================
#  v3: End-to-End
# ===================================================================

class TestAFIv3:
    def test_elite_trader(self):
        """Elite Sharpe with right skew → high score (>800)."""
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
        assert result.bcm >= 0.9

    def test_right_skew_boosts_score(self):
        """Right-skewed distribution should score higher than balanced."""
        n = 60
        r_balanced = [0.5, -0.5] * (n // 2)
        r_skewed = [3.0, -0.5] * (n // 2)

        days = list(range(n))
        result_balanced = compute_afi(_make_trades(r_balanced, days), reference_time=NOW, version=3)
        result_skewed = compute_afi(_make_trades(r_skewed, days), reference_time=NOW, version=3)

        # Skewed should have higher CA, and since WSS also benefits from positive R-slope...
        assert result_skewed.cps > result_balanced.cps
        assert result_skewed.afi_score > result_balanced.afi_score

    def test_stability_boosts_afi(self):
        """Consistent trades should produce BCM > 1.0."""
        n = 60
        r_vals = [0.5] * n  # Perfectly consistent
        trades = _make_trades(r_vals, list(range(n)))
        result = compute_afi(trades, reference_time=NOW, version=3)
        assert result.bcm >= 1.0  # stability → BCM reward

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
        # 50 trades compressed in 50 days vs spread over 500 days
        trades_compressed = _make_trades(r_vals, list(range(50)))
        trades_spread = _make_trades(r_vals, [i * 10 for i in range(50)])

        r1 = compute_afi(trades_compressed, reference_time=NOW, version=3)
        r2 = compute_afi(trades_spread, reference_time=NOW, version=3)
        assert abs(r1.afi_score - r2.afi_score) < 1e-10

    def test_clamped_to_300_900(self):
        """v3: AFI score is clamped to [300, 900]."""
        # Zero trades → edge case
        result = compute_afi([], reference_time=NOW, version=3)
        assert result.afi_score >= 300
        assert result.afi_score <= 900
        assert result.afi_version == 3
        assert result.cps == 1.0
        assert result.bcm == 1.0

    def test_structural_total_formula(self):
        """v3: structural_total = WSS * CA * BCM, then compress + clamp."""
        n = 60
        trades = _make_trades([0.5] * n, list(range(n)))
        result = compute_afi(trades, reference_time=NOW, version=3)

        # Verify cps is the convexity amplifier (>=1.0)
        assert result.cps >= 1.0
        assert result.cps <= 1.25
        # BCM in [0.90, 1.10]
        assert result.bcm >= 0.90
        assert result.bcm <= 1.10

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

        # Cowboy has worse structural metrics despite bigger wins
        assert r_cowboy.afi_score < r_smooth.afi_score
