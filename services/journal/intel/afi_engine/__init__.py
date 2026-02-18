"""
AFI (Antifragile Index) Engine — Public API
v3.0.0

Single entry point: compute_afi()

    from afi_engine import compute_afi
    result = compute_afi(trades, prior_afi, wss_history, version=3)
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Set

import numpy as np

from .models import AFIResult, TrendSignal
from .recency import compute_equal_weights, compute_weights
from .component_engine import (
    compute_dd_containment,
    compute_ltc,
    compute_r_slope,
    compute_sharpe,
    _identify_drawdown_periods,
)
from .scoring_engine import (
    compress,
    compute_afi_v4,
    compute_afi_v5,
    compute_convexity_amplifier,
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
    compute_trend,
    compute_wss,
    dampen,
    is_provisional,
    normalize_components,
    normalize_sharpe,
)

# Re-export for external consumers
from .models import AFIComponents, AFIComponentsV4, AFIResult, AFIResultV4, TrendSignal  # noqa: F811

# Active AFI version — v5 is Structural Pareto Composite (D × R Pareto 80/20)
AFI_VERSION: int = 5

# Phase 1 default — VIX-at-entry lookup deferred to Phase 2
_DEFAULT_REGIME_DIVERSITY: float = 0.5

# WSS history cap — one entry per calendar day, 90 max (v1 only)
_WSS_HISTORY_MAX: int = 90


def compute_afi(
    trades: List[Dict],
    prior_afi: Optional[float] = None,
    wss_history: Optional[List[Dict]] = None,
    reference_time: Optional[datetime] = None,
    version: Optional[int] = None,
) -> AFIResult:
    """Compute AFI score for a single user.

    Parameters
    ----------
    trades : list of dicts, each with keys:
        - r_multiple: float
        - exit_time: datetime
        - planned_risk: float (cents)
        - pnl: float (cents)
        - quantity: int (optional, for future sizing analysis)
    prior_afi : previous AFI score (None on first computation)
    wss_history : list of {"date": "YYYY-MM-DD", "wss": float}
    reference_time : anchor for recency weights (default: utcnow)
    version : AFI version (1, 2, or 3). Defaults to AFI_VERSION.

    Returns
    -------
    AFIResult with all computed values.
    """
    v = version if version is not None else AFI_VERSION

    if v == 5:
        raise ValueError(
            "AFI v5 uses compute_afi_v5() directly (different signature). "
            "Pass version=3 to use legacy compute_afi()."
        )
    if v == 4:
        raise ValueError(
            "AFI v4 uses compute_afi_v4() directly (different signature). "
            "Pass version=3 to use legacy compute_afi()."
        )
    if v == 3:
        return _compute_afi_v3(trades, wss_history, reference_time)
    elif v == 2:
        return _compute_afi_v2(trades, wss_history, reference_time)
    else:
        return _compute_afi_v1(trades, prior_afi, wss_history, reference_time)


def _compute_afi_v1(
    trades: List[Dict],
    prior_afi: Optional[float] = None,
    wss_history: Optional[List[Dict]] = None,
    reference_time: Optional[datetime] = None,
) -> AFIResult:
    """v1: recency-weighted components with RB dampening."""
    if reference_time is None:
        reference_time = datetime.utcnow()
    if wss_history is None:
        wss_history = []

    trade_count = len(trades)
    now = reference_time

    # --- Edge case: no trades ---
    if trade_count == 0:
        components = normalize_components(0.0, 0.0, 1.0, 1.0)
        wss = compute_wss(components)
        afi_raw = compress(wss)
        return AFIResult(
            afi_score=afi_raw if prior_afi is None else prior_afi,
            afi_raw=afi_raw,
            wss=wss,
            components=components,
            robustness=0.0,
            trend=compute_trend(wss_history),
            is_provisional=True,
            trade_count=0,
            active_days=0,
            computed_at=now,
            afi_version=1,
        )

    # --- Extract arrays ---
    r_multiples = np.array([t["r_multiple"] for t in trades], dtype=np.float64)
    exit_times = [t["exit_time"] for t in trades]

    # --- Recency weights ---
    weights = compute_weights(exit_times, now)

    # --- Component computations ---
    r_slope_raw = compute_r_slope(r_multiples, weights)
    sharpe_raw = compute_sharpe(r_multiples, weights)
    ltc_raw = compute_ltc(r_multiples, weights)
    dd_raw = compute_dd_containment(r_multiples)

    # --- Normalize ---
    components = normalize_components(r_slope_raw, sharpe_raw, ltc_raw, dd_raw)

    # --- WSS ---
    wss = compute_wss(components)

    # --- Compress ---
    afi_raw = compress(wss)

    # --- Robustness ---
    active_days = _compute_active_days(exit_times)
    survived_dds = _count_survived_drawdowns(r_multiples)
    rb = compute_robustness(
        trade_count=trade_count,
        active_days=active_days,
        regime_diversity=_DEFAULT_REGIME_DIVERSITY,
        survived_dds=survived_dds,
    )

    # --- Dampen ---
    afi_score = dampen(afi_raw, prior_afi, rb)

    # --- Trend ---
    trend = compute_trend(wss_history)

    # --- Provisional ---
    provisional = is_provisional(trade_count, active_days)

    return AFIResult(
        afi_score=afi_score,
        afi_raw=afi_raw,
        wss=wss,
        components=components,
        robustness=rb,
        trend=trend,
        is_provisional=provisional,
        trade_count=trade_count,
        active_days=active_days,
        computed_at=now,
        afi_version=1,
    )


def _compute_afi_v2(
    trades: List[Dict],
    wss_history: Optional[List[Dict]] = None,
    reference_time: Optional[datetime] = None,
) -> AFIResult:
    """v2: equal-weight, no dampening, lifetime structural identity."""
    if reference_time is None:
        reference_time = datetime.utcnow()
    if wss_history is None:
        wss_history = []

    trade_count = len(trades)
    now = reference_time

    # --- Edge case: no trades ---
    if trade_count == 0:
        components = normalize_components(0.0, 0.0, 1.0, 1.0)
        wss = compute_wss(components)
        afi_raw = compress(wss)
        return AFIResult(
            afi_score=afi_raw,
            afi_raw=afi_raw,
            wss=wss,
            components=components,
            robustness=0.0,
            trend=compute_trend(wss_history),
            is_provisional=trade_count < 20,
            trade_count=0,
            active_days=0,
            computed_at=now,
            afi_version=2,
        )

    # --- Extract arrays ---
    r_multiples = np.array([t["r_multiple"] for t in trades], dtype=np.float64)
    exit_times = [t["exit_time"] for t in trades]

    # --- Equal weights (v2: no recency decay) ---
    weights = compute_equal_weights(trade_count)

    # --- Component computations ---
    r_slope_raw = compute_r_slope(r_multiples, weights)
    sharpe_raw = compute_sharpe(r_multiples, weights)
    ltc_raw = compute_ltc(r_multiples, weights)
    dd_raw = compute_dd_containment(r_multiples)

    # --- Normalize ---
    components = normalize_components(r_slope_raw, sharpe_raw, ltc_raw, dd_raw)

    # --- WSS ---
    wss = compute_wss(components)

    # --- Compress ---
    afi_raw = compress(wss)

    # --- No dampening in v2: AFI = AFI_raw ---
    afi_score = afi_raw

    # --- Robustness v2 (informational only) ---
    survived_dds = _count_survived_drawdowns(r_multiples)
    dist_stability = compute_distribution_stability(wss_history)
    rb = compute_robustness_v2(
        regime_diversity=_DEFAULT_REGIME_DIVERSITY,
        survived_dds=survived_dds,
        distribution_stability=dist_stability,
    )

    # --- Trend ---
    trend = compute_trend(wss_history)

    # --- Provisional ---
    active_days = _compute_active_days(exit_times)
    provisional = trade_count < 20

    return AFIResult(
        afi_score=afi_score,
        afi_raw=afi_raw,
        wss=wss,
        components=components,
        robustness=rb,
        trend=trend,
        is_provisional=provisional,
        trade_count=trade_count,
        active_days=active_days,
        computed_at=now,
        afi_version=2,
    )


def _compute_afi_v3(
    trades: List[Dict],
    wss_history: Optional[List[Dict]] = None,
    reference_time: Optional[datetime] = None,
) -> AFIResult:
    """v3: credibility-gated structural identity.

    All trades. Equal weights. No recency. No dampening. No prior_afi.

    Pipeline:
        Sharpe_adj = Sharpe_raw × Cred_sharpe(N)
        WSS = weighted sum of [norm(R_Slope), norm(Sharpe_adj), norm(LTC), norm(DD)]
        CA = convexity amplifier [1.0, 1.25]
        Repeatability = credibility-gated stability multiplier [1.0, ~1.15]
        Structural_Total = WSS × CA × Repeatability
        AFI_raw = 600 + 300 × tanh(2.5 × (Structural_Total - 0.5))
        Skew_bonus = additive [-10, +10]
        Elite_bonus = additive [0, +20]
        AFI_score = clamp(AFI_raw + Skew_bonus + Elite_bonus, 300, 900)
        Movement cap (±50) applied in orchestrator only.
    """
    if reference_time is None:
        reference_time = datetime.utcnow()
    if wss_history is None:
        wss_history = []

    trade_count = len(trades)
    now = reference_time

    # --- Edge case: no trades ---
    if trade_count == 0:
        components = normalize_components(0.0, 0.0, 1.0, 1.0)
        wss = compute_wss(components)
        afi_raw = compress(wss)
        return AFIResult(
            afi_score=afi_raw,
            afi_raw=afi_raw,
            wss=wss,
            components=components,
            robustness=0.0,
            trend=compute_trend(wss_history),
            is_provisional=True,
            trade_count=0,
            active_days=0,
            computed_at=now,
            afi_version=3,
            cps=1.0,
            repeatability=1.0,
        )

    # --- Extract arrays ---
    r_multiples = np.array([t["r_multiple"] for t in trades], dtype=np.float64)
    exit_times = [t["exit_time"] for t in trades]

    # --- Equal weights (no recency decay) ---
    weights = compute_equal_weights(trade_count)

    # --- Component computations ---
    r_slope_raw = compute_r_slope(r_multiples, weights)
    sharpe_raw = compute_sharpe(r_multiples, weights)
    ltc_raw = compute_ltc(r_multiples, weights)
    dd_raw = compute_dd_containment(r_multiples)

    # --- Sharpe_adj: credibility-gated Sharpe ---
    sharpe_adj = compute_sharpe_adj(sharpe_raw, trade_count)

    # --- Normalize (WSS uses Sharpe_adj, not Sharpe_raw) ---
    components = normalize_components(r_slope_raw, sharpe_adj, ltc_raw, dd_raw)

    # --- WSS (v3 weights: 0.25/0.40/0.15/0.20) ---
    wss = compute_wss(components)

    # --- Convexity Amplifier [1.0, 1.25] ---
    ca = compute_convexity_amplifier(r_multiples)

    # --- Repeatability [1.0, ~1.15] ---
    sharpe_stab = compute_rolling_sharpe_stability(r_multiples, weights)
    wss_stab = compute_rolling_wss_stability(r_multiples, weights)
    skew_persist = compute_skew_persistence(r_multiples)
    rep = compute_repeatability(sharpe_stab, wss_stab, skew_persist, trade_count)

    # --- Structural Total ---
    structural_total = wss * ca * rep

    # --- Compress (logistic) ---
    afi_raw = compress(structural_total)

    # --- Skew Bonus [-10, +10] ---
    skew_bonus = compute_skew_bonus(r_multiples, trade_count)

    # --- Elite Bonus [0, +20] ---
    elite_bonus = compute_elite_bonus(sharpe_adj, trade_count)

    # --- Clamp to [300, 900] ---
    afi_score = max(300.0, min(900.0, afi_raw + skew_bonus + elite_bonus))

    # --- Robustness v2 (informational) ---
    survived_dds = _count_survived_drawdowns(r_multiples)
    rb = compute_robustness_v2(
        regime_diversity=_DEFAULT_REGIME_DIVERSITY,
        survived_dds=survived_dds,
        distribution_stability=wss_stab,
    )

    # --- Trend ---
    trend = compute_trend(wss_history)

    # --- Provisional ---
    active_days = _compute_active_days(exit_times)
    provisional = trade_count < 20

    return AFIResult(
        afi_score=round(afi_score, 2),
        afi_raw=round(afi_raw, 2),
        wss=wss,
        components=components,
        robustness=rb,
        trend=trend,
        is_provisional=provisional,
        trade_count=trade_count,
        active_days=active_days,
        computed_at=now,
        afi_version=3,
        cps=round(ca, 5),
        repeatability=round(rep, 5),
    )


def _compute_active_days(exit_times: List[datetime]) -> int:
    """Count distinct calendar days with at least one trade exit."""
    days: Set[str] = set()
    for t in exit_times:
        days.add(t.strftime("%Y-%m-%d"))
    return len(days)


def _count_survived_drawdowns(r_multiples: np.ndarray) -> int:
    """Count completed (recovered) drawdown periods."""
    periods = _identify_drawdown_periods(r_multiples)
    return sum(1 for _, _, recovered in periods if recovered)


def trim_wss_history(history: List[Dict], max_entries: int = _WSS_HISTORY_MAX) -> List[Dict]:
    """Trim WSS history to max_entries, keeping most recent."""
    if max_entries is None:
        return history
    if len(history) <= max_entries:
        return history
    return history[-max_entries:]
