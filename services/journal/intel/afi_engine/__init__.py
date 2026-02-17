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
    compute_bcm,
    compute_convexity_amplifier,
    compute_distribution_stability,
    compute_robustness,
    compute_robustness_v2,
    compute_rolling_wss_stability,
    compute_trend,
    compute_wss,
    dampen,
    is_provisional,
    normalize_components,
)

# Re-export for external consumers
from .models import AFIComponents, AFIResult, TrendSignal  # noqa: F811

# Active AFI version — v3 is convex structural identity
AFI_VERSION: int = 3

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
    """v2: equal-weight, no dampening, lifetime structural identity.

    All trades contribute equally. No recency decay.
    No RB dampening — AFI = AFI_raw directly.
    Robustness_v2 is informational metadata (no trade_count/active_days).
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

    # --- Component computations (same 4 components, same weights 35/25/20/20) ---
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

    # --- Robustness v2 (informational only, no trade_count/active_days) ---
    survived_dds = _count_survived_drawdowns(r_multiples)
    dist_stability = compute_distribution_stability(wss_history)
    rb = compute_robustness_v2(
        regime_diversity=_DEFAULT_REGIME_DIVERSITY,
        survived_dds=survived_dds,
        distribution_stability=dist_stability,
    )

    # --- Trend ---
    trend = compute_trend(wss_history)

    # --- Provisional (v2: trade_count only, no active_days requirement) ---
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
    """v3: convex structural identity.

    All trades. Equal weights. No recency. No dampening. No prior_afi.

    Structural_Total = WSS * Convexity_Amplifier * BCM
    AFI = clamp(compress(Structural_Total), 300, 900)
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
            bcm=1.0,
        )

    # --- Extract arrays ---
    r_multiples = np.array([t["r_multiple"] for t in trades], dtype=np.float64)
    exit_times = [t["exit_time"] for t in trades]

    # --- Equal weights (no recency decay) ---
    weights = compute_equal_weights(trade_count)

    # --- Component computations (frozen 4 components, frozen 35/25/20/20 weights) ---
    r_slope_raw = compute_r_slope(r_multiples, weights)
    sharpe_raw = compute_sharpe(r_multiples, weights)
    ltc_raw = compute_ltc(r_multiples, weights)
    dd_raw = compute_dd_containment(r_multiples)

    # --- Normalize ---
    components = normalize_components(r_slope_raw, sharpe_raw, ltc_raw, dd_raw)

    # --- WSS (frozen formula) ---
    wss = compute_wss(components)

    # --- Convexity Amplifier [1.0, 1.25] ---
    ca = compute_convexity_amplifier(r_multiples)

    # --- Behavioral Consistency Multiplier [0.90, 1.10] ---
    stability = compute_rolling_wss_stability(r_multiples, weights)
    bcm = compute_bcm(stability)

    # --- Structural Total ---
    structural_total = wss * ca * bcm

    # --- Compress (same logistic, no modification) ---
    afi_raw = compress(structural_total)

    # --- Clamp to [300, 900] ---
    afi_score = max(300.0, min(900.0, afi_raw))

    # --- Robustness v2 (informational) ---
    survived_dds = _count_survived_drawdowns(r_multiples)
    rb = compute_robustness_v2(
        regime_diversity=_DEFAULT_REGIME_DIVERSITY,
        survived_dds=survived_dds,
        distribution_stability=stability,
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
        afi_version=3,
        cps=round(ca, 5),
        bcm=round(bcm, 5),
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
    """Trim WSS history to max_entries, keeping most recent.

    v1: capped at 90 entries.
    v2/v3: pass max_entries=None for full lifetime retention.
    """
    if max_entries is None:
        return history
    if len(history) <= max_entries:
        return history
    return history[-max_entries:]
