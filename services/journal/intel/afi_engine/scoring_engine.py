"""
AFI — Scoring Engine

Normalization, WSS computation, logistic compression,
credibility gating, repeatability, convexity amplifier,
skew bonus, elite bonus, and trend detection.

All constants are internal and not disclosed to users (anti-gaming).
"""
from __future__ import annotations

import math
from typing import List, Optional

import numpy as np

from .models import AFIComponents, AFIComponentsV4, AFIResultV4, TrendSignal

# ---------------------------------------------------------------------------
#  WSS Component Weights (v3 — not disclosed)
# ---------------------------------------------------------------------------
W_R_SLOPE: float = 0.25
W_SHARPE: float = 0.40   # Sharpe_adj (credibility-adjusted) gets dominant weight
W_LTC: float = 0.15
W_DD_CONTAINMENT: float = 0.20

# ---------------------------------------------------------------------------
#  Normalization Constants
# ---------------------------------------------------------------------------
SLOPE_SCALE: float = 0.08  # tanh scaling for R-slope

# ---------------------------------------------------------------------------
#  Logistic Compression Constants
# ---------------------------------------------------------------------------
CENTER: float = 600.0   # midpoint of AFI range
K: float = 300.0         # spread amplitude
S: float = 2.5           # steepness
SHIFT: float = 0.5       # WSS value that maps to CENTER

# ---------------------------------------------------------------------------
#  Robustness Coefficients (v1 only)
# ---------------------------------------------------------------------------
RB_ALPHA: float = 2.0    # √(trade_count) weight
RB_BETA: float = 1.5     # √(active_days) weight
RB_GAMMA: float = 10.0   # regime_diversity weight (input 0-1)
RB_DELTA: float = 3.0    # survived_drawdowns weight

# ---------------------------------------------------------------------------
#  Dampening Constant (v1 only)
# ---------------------------------------------------------------------------
RB_C: float = 30.0

# ---------------------------------------------------------------------------
#  Trend Detection
# ---------------------------------------------------------------------------
TREND_THRESHOLD: float = 0.002
TREND_WINDOW_DAYS: int = 45

# ---------------------------------------------------------------------------
#  Provisional Thresholds
# ---------------------------------------------------------------------------
MIN_TRADES_PROVISIONAL: int = 20
MIN_ACTIVE_DAYS_PROVISIONAL: int = 30

# ---------------------------------------------------------------------------
#  Credibility Constants (v3)
# ---------------------------------------------------------------------------
CRED_SHARPE_K: float = 50.0   # half-saturation for Sharpe credibility
CRED_BONUS_K: float = 150.0   # half-saturation for bonus credibility

# ---------------------------------------------------------------------------
#  Repeatability Constants (v3)
# ---------------------------------------------------------------------------
REP_SHARPE_W: float = 0.4
REP_WSS_W: float = 0.3
REP_SKEW_W: float = 0.3
REPEATABILITY_SCALE: float = 0.15  # max boost from repeatability

# ---------------------------------------------------------------------------
#  Skew Bonus Constants (v3)
# ---------------------------------------------------------------------------
SKEW_BONUS_SCALE: float = 10.0  # max magnitude of skew bonus

# ---------------------------------------------------------------------------
#  Elite Bonus Constants (v3)
# ---------------------------------------------------------------------------
ELITE_SHARPE_THRESHOLD: float = 5.0
ELITE_BONUS_SCALE: float = 20.0  # max elite bonus

# ---------------------------------------------------------------------------
#  Capital Integrity Constants (Governance Patch v1.1)
# ---------------------------------------------------------------------------
MIN_CAPITAL: int = 1_000_000   # $10,000 in cents (trade_logs.starting_capital is BIGINT cents)
NEUTRAL_AFI: float = 500.0     # Unrated baseline — no capital → no score

# ---------------------------------------------------------------------------
#  Convexity Amplifier Constants (v3)
# ---------------------------------------------------------------------------
TAIL_RATIO_CAP: float = 5.0
CONVEXITY_RATIO_CAP: float = 4.0

# ---------------------------------------------------------------------------
#  Stability Constants (shared)
# ---------------------------------------------------------------------------
STABILITY_VAR_CAP: float = 0.05  # WSS variance cap for normalization
ROLLING_WSS_WINDOW: int = 20


def normalize_r_slope(raw: float) -> float:
    """Normalize R-slope to [0, 1] via tanh."""
    return 0.5 + 0.5 * math.tanh(raw / SLOPE_SCALE)


def normalize_sharpe(raw: float) -> float:
    """Normalize Sharpe to [0, 1] via linear clamp."""
    return max(0.0, min(1.0, (raw + 1.0) / 4.0))


def normalize_components(
    r_slope_raw: float,
    sharpe_raw: float,
    ltc_raw: float,
    dd_containment_raw: float,
) -> AFIComponents:
    """Normalize all four raw component values to [0, 1]."""
    return AFIComponents(
        r_slope=normalize_r_slope(r_slope_raw),
        sharpe=normalize_sharpe(sharpe_raw),
        ltc=max(0.0, min(1.0, ltc_raw)),
        dd_containment=max(0.0, min(1.0, dd_containment_raw)),
    )


def compute_wss(components: AFIComponents) -> float:
    """Weighted Structural Score from normalised components.

    v3 weights: R_Slope 0.25, Sharpe_adj 0.40, LTC 0.15, DD 0.20
    Note: components.sharpe should already be normalized from Sharpe_adj (not raw).
    """
    return (
        W_R_SLOPE * components.r_slope
        + W_SHARPE * components.sharpe
        + W_LTC * components.ltc
        + W_DD_CONTAINMENT * components.dd_containment
    )


def compress(wss: float) -> float:
    """Logistic compression: WSS → AFI_raw (soft 300-900 range)."""
    return CENTER + K * math.tanh(S * (wss - SHIFT))


# ---------------------------------------------------------------------------
#  Credibility Functions (v3)
# ---------------------------------------------------------------------------

def cred_sharpe(n: int) -> float:
    """Credibility gate for Sharpe: sqrt(N / (N + 50))."""
    return math.sqrt(max(n, 0) / (max(n, 0) + CRED_SHARPE_K))


def cred_bonus(n: int) -> float:
    """Credibility gate for bonuses: sqrt(N / (N + 150))."""
    return math.sqrt(max(n, 0) / (max(n, 0) + CRED_BONUS_K))


def compute_sharpe_adj(sharpe_raw: float, trade_count: int) -> float:
    """Sharpe_adj = Sharpe_raw × Cred_sharpe(N)."""
    return sharpe_raw * cred_sharpe(trade_count)


# ---------------------------------------------------------------------------
#  Convexity Amplifier (v3)
# ---------------------------------------------------------------------------

def compute_tail_ratio(r_multiples: np.ndarray) -> float:
    """Normalized tail ratio: avg_win / avg_loss, capped to [0, 1]."""
    wins = r_multiples[r_multiples > 0]
    losses = r_multiples[r_multiples < 0]

    if len(wins) == 0 or len(losses) == 0:
        return 0.0

    avg_win = float(np.mean(wins))
    avg_loss = float(abs(np.mean(losses)))

    if avg_loss < 1e-15:
        return 1.0

    raw = avg_win / avg_loss
    return min(raw / TAIL_RATIO_CAP, 1.0)


def compute_convexity_ratio(r_multiples: np.ndarray) -> float:
    """Normalized convexity ratio: max_win / max_loss, capped to [0, 1]."""
    wins = r_multiples[r_multiples > 0]
    losses = r_multiples[r_multiples < 0]

    if len(wins) == 0 or len(losses) == 0:
        return 0.0

    max_win = float(np.max(wins))
    max_loss = float(abs(np.min(losses)))

    if max_loss < 1e-15:
        return 1.0

    raw = max_win / max_loss
    return min(raw / CONVEXITY_RATIO_CAP, 1.0)


def compute_convexity_amplifier(r_multiples: np.ndarray) -> float:
    """Convexity Amplifier: multiplicative structural reward for right-skew.

    CA = 1 + 0.15 * normalized_tail_ratio + 0.10 * normalized_convexity_ratio
    Range: [1.0, 1.25]
    """
    if len(r_multiples) < 2:
        return 1.0

    tail = compute_tail_ratio(r_multiples)
    convexity = compute_convexity_ratio(r_multiples)
    return 1.0 + 0.15 * tail + 0.10 * convexity


# ---------------------------------------------------------------------------
#  Repeatability (v3 — replaces BCM)
# ---------------------------------------------------------------------------

def compute_rolling_sharpe_stability(
    r_multiples: np.ndarray,
    weights: np.ndarray,
) -> float:
    """Sharpe stability: 1 - normalized variance of rolling Sharpe values.

    Returns [0, 1]. If < ROLLING_WSS_WINDOW trades, returns 0.5 (neutral).
    """
    n = len(r_multiples)
    if n < ROLLING_WSS_WINDOW:
        return 0.5

    from .component_engine import compute_sharpe

    sharpe_series = []
    for start in range(n - ROLLING_WSS_WINDOW + 1):
        chunk = r_multiples[start:start + ROLLING_WSS_WINDOW]
        w = np.full(ROLLING_WSS_WINDOW, 1.0 / ROLLING_WSS_WINDOW, dtype=np.float64)
        sharpe_series.append(compute_sharpe(chunk, w))

    if len(sharpe_series) < 3:
        return 0.5

    variance = float(np.var(sharpe_series))
    return max(0.0, min(1.0, 1.0 - min(variance / STABILITY_VAR_CAP, 1.0)))


def compute_rolling_wss_stability(
    r_multiples: np.ndarray,
    weights: np.ndarray,
) -> float:
    """Compute behavioral stability from rolling WSS over trade history.

    Returns stability score in [0, 1]. If < ROLLING_WSS_WINDOW trades, returns 0.5 (neutral).
    """
    n = len(r_multiples)
    if n < ROLLING_WSS_WINDOW:
        return 0.5

    wss_series = []
    window_size = ROLLING_WSS_WINDOW

    for start in range(n - window_size + 1):
        chunk = r_multiples[start:start + window_size]
        w = np.full(window_size, 1.0 / window_size, dtype=np.float64)

        from .component_engine import (
            compute_dd_containment,
            compute_ltc,
            compute_r_slope,
            compute_sharpe,
        )
        r_slope_raw = compute_r_slope(chunk, w)
        sharpe_raw = compute_sharpe(chunk, w)
        ltc_raw = compute_ltc(chunk, w)
        dd_raw = compute_dd_containment(chunk)

        components = normalize_components(r_slope_raw, sharpe_raw, ltc_raw, dd_raw)
        wss = compute_wss(components)
        wss_series.append(wss)

    if len(wss_series) < 3:
        return 0.5

    variance = float(np.var(wss_series))
    return 1.0 - min(variance / STABILITY_VAR_CAP, 1.0)


def _sample_skewness(arr: np.ndarray) -> float:
    """Compute sample skewness (unbiased, Fisher's definition).

    Equivalent to scipy.stats.skew(arr, bias=False).
    Returns 0.0 if fewer than 3 elements.
    """
    n = len(arr)
    if n < 3:
        return 0.0
    mean = float(np.mean(arr))
    m2 = float(np.mean((arr - mean) ** 2))
    m3 = float(np.mean((arr - mean) ** 3))
    if m2 < 1e-15:
        return 0.0
    # Biased skewness (G1)
    g1 = m3 / (m2 ** 1.5)
    # Adjust for sample bias (Fisher's correction)
    return g1 * math.sqrt(n * (n - 1)) / (n - 2)


def compute_skew_persistence(r_multiples: np.ndarray) -> float:
    """Skew persistence: stability of rolling skew across windows.

    Returns [0, 1]. High value = consistently skewed distribution.
    If < ROLLING_WSS_WINDOW trades, returns 0.5 (neutral).
    """
    n = len(r_multiples)
    if n < ROLLING_WSS_WINDOW:
        return 0.5

    skew_series = []
    for start in range(n - ROLLING_WSS_WINDOW + 1):
        chunk = r_multiples[start:start + ROLLING_WSS_WINDOW]
        s = _sample_skewness(chunk)
        skew_series.append(s)

    if len(skew_series) < 3:
        return 0.5

    # Persistence = fraction of windows with positive skew × stability
    positive_fraction = sum(1 for s in skew_series if s > 0) / len(skew_series)
    variance = float(np.var(skew_series))
    stability = 1.0 - min(variance / 1.0, 1.0)  # variance cap of 1.0 for skew

    return max(0.0, min(1.0, positive_fraction * stability))


def compute_repeatability(
    sharpe_stability: float,
    wss_stability: float,
    skew_persistence: float,
    trade_count: int,
) -> float:
    """Repeatability multiplier (replaces BCM).

    Rep_raw = (0.4 × Sharpe_stability + 0.3 × WSS_stability + 0.3 × Skew_persistence) × Cred_bonus(N)
    Repeatability = 1.0 + 0.15 × Rep_raw  → [1.0, ~1.15]

    Note: stability inputs are raw (no credibility inside). Credibility applied at composite.
    """
    rep_raw = (
        REP_SHARPE_W * max(0.0, min(1.0, sharpe_stability))
        + REP_WSS_W * max(0.0, min(1.0, wss_stability))
        + REP_SKEW_W * max(0.0, min(1.0, skew_persistence))
    ) * cred_bonus(trade_count)

    return 1.0 + REPEATABILITY_SCALE * rep_raw


# ---------------------------------------------------------------------------
#  Skew Bonus (v3)
# ---------------------------------------------------------------------------

def compute_skew_bonus(r_multiples: np.ndarray, trade_count: int) -> float:
    """Skew bonus: additive adjustment based on full-history sample skew.

    Skew_bonus = Cred_bonus(N) × Skew_persistence × 10 × tanh(sample_skew)
    Range: [-10, +10]

    sample_skew is full-history (all R-multiples), not windowed.
    """
    if len(r_multiples) < 3:
        return 0.0

    sample_skew = _sample_skewness(r_multiples)
    skew_persist = compute_skew_persistence(r_multiples)

    return cred_bonus(trade_count) * skew_persist * SKEW_BONUS_SCALE * math.tanh(sample_skew)


# ---------------------------------------------------------------------------
#  Elite Bonus (v3)
# ---------------------------------------------------------------------------

def compute_elite_bonus(sharpe_adj: float, trade_count: int) -> float:
    """Elite bonus for exceptional Sharpe_adj (credibility-adjusted).

    if Sharpe_adj > 5.0:
        Elite_bonus = Cred_bonus(N) × 20 × tanh(Sharpe_adj - 5.0)
    else: 0

    Cap: +20
    """
    if sharpe_adj <= ELITE_SHARPE_THRESHOLD:
        return 0.0

    return cred_bonus(trade_count) * ELITE_BONUS_SCALE * math.tanh(sharpe_adj - ELITE_SHARPE_THRESHOLD)


# ---------------------------------------------------------------------------
#  Robustness (v1 only)
# ---------------------------------------------------------------------------

def compute_robustness(
    trade_count: int,
    active_days: int,
    regime_diversity: float,
    survived_dds: int,
) -> float:
    """Robustness score (0-100+, uncapped). v1 only."""
    return (
        RB_ALPHA * math.sqrt(max(trade_count, 0))
        + RB_BETA * math.sqrt(max(active_days, 0))
        + RB_GAMMA * max(0.0, min(1.0, regime_diversity))
        + RB_DELTA * max(survived_dds, 0)
    )


def dampen(
    afi_raw: float,
    prior_afi: Optional[float],
    rb: float,
) -> float:
    """Apply RB dampening to slow AFI movement. v1 only."""
    if prior_afi is None:
        return afi_raw

    factor = 1.0 / (1.0 + rb / RB_C)
    return prior_afi + (afi_raw - prior_afi) * factor


def compute_trend(wss_history: List[dict]) -> TrendSignal:
    """Detect trend from recent WSS history."""
    if len(wss_history) < 3:
        return TrendSignal.STABLE

    recent = wss_history[-TREND_WINDOW_DAYS:]
    if len(recent) < 3:
        return TrendSignal.STABLE

    y = np.array([entry["wss"] for entry in recent], dtype=np.float64)
    x = np.arange(len(y), dtype=np.float64)

    x_bar = x.mean()
    y_bar = y.mean()
    dx = x - x_bar
    var_x = np.dot(dx, dx)
    if var_x < 1e-15:
        return TrendSignal.STABLE

    slope = float(np.dot(dx, y - y_bar) / var_x)

    if slope > TREND_THRESHOLD:
        return TrendSignal.IMPROVING
    elif slope < -TREND_THRESHOLD:
        return TrendSignal.DECAYING
    else:
        return TrendSignal.STABLE


def is_provisional(trade_count: int, active_days: int) -> bool:
    """Check if user is in provisional state."""
    return trade_count < MIN_TRADES_PROVISIONAL or active_days < MIN_ACTIVE_DAYS_PROVISIONAL


# ---------------------------------------------------------------------------
#  v2: Robustness & Distribution Stability
# ---------------------------------------------------------------------------

def compute_robustness_v2(
    regime_diversity: float,
    survived_dds: int,
    distribution_stability: float,
) -> float:
    """Robustness v2: no trade_count, no active_days."""
    return (
        10.0 * max(0.0, min(1.0, regime_diversity))
        + 3.0 * max(survived_dds, 0)
        + 5.0 * max(0.0, min(1.0, distribution_stability))
    )


def compute_distribution_stability(wss_history: List[dict]) -> float:
    """Compute distribution stability from full lifetime WSS history."""
    if len(wss_history) < 3:
        return 0.5

    wss_values = np.array([e["wss"] for e in wss_history], dtype=np.float64)
    variance = float(np.var(wss_values))
    return 1.0 - min(variance / STABILITY_VAR_CAP, 1.0)


# ===========================================================================
#  AFI v4 — Dual-Index Architecture
# ===========================================================================

# v4 eligibility (stricter than v1-v3)
V4_MIN_TRADES: int = 50
V4_MIN_ACTIVE_DAYS: int = 30

# AFI-M rolling window (calendar days)
AFI_M_WINDOW_DAYS: int = 45

# v4 component weights for AFI-R
V4_W_SHARPE: float = 0.30
V4_W_DRAWDOWN: float = 0.30
V4_W_ASYMMETRY: float = 0.20
V4_W_RECOVERY: float = 0.20

# v4 composite blend
V4_R_WEIGHT: float = 0.65
V4_M_WEIGHT: float = 0.35

# v4 drawdown resilience sub-weights
V4_DD_DEPTH_W: float = 0.40
V4_DD_AVG_W: float = 0.20
V4_DD_RECOVERY_W: float = 0.20
V4_DD_CYCLES_W: float = 0.20

# v4 drawdown normalization caps
V4_DD_MAX_CAP: float = 5.0       # max DD in R-units
V4_DD_AVG_CAP: float = 3.0       # avg DD in R-units
V4_DD_RECOVERY_DAYS: float = 30.0  # days normalization reference
V4_DD_CYCLES_CAP: float = 5.0    # recovery cycle count cap

# v4 asymmetry normalization cap
V4_ASYMMETRY_CAP: float = 3.0    # avg_win/avg_loss cap

# v4 recovery velocity normalization
V4_VELOCITY_TRADES: float = 20.0  # trades normalization reference

# v4 confidence dual-gate
V4_CRED_TRADES_K: float = 50.0   # half-saturation for trade count
V4_CRED_DAYS_K: float = 30.0     # half-saturation for active days

# Annualization factor for daily Sharpe
ANNUALIZATION_FACTOR: float = math.sqrt(252)


def build_daily_equity_series(
    trades: List[dict],
    starting_capital: float,
) -> List[tuple]:
    """Build daily equity series from closed trades (realized PnL only).

    Args:
        trades: List of trade dicts with 'pnl' and 'exit_time' fields,
                sorted by exit_time ASC.
        starting_capital: Starting capital in cents.

    Returns:
        List of (date_str, equity_value) tuples, one per trading day,
        sorted chronologically. equity_value is in cents.
    """
    if not trades or starting_capital <= 0:
        return []

    # Aggregate realized PnL by exit day
    daily_pnl: dict = {}
    for t in trades:
        exit_time = t.get('exit_time')
        pnl = t.get('pnl', 0.0)
        if exit_time is None or pnl is None:
            continue
        if hasattr(exit_time, 'strftime'):
            day = exit_time.strftime('%Y-%m-%d')
        else:
            day = str(exit_time).split('T')[0]
        daily_pnl[day] = daily_pnl.get(day, 0.0) + float(pnl)

    if not daily_pnl:
        return []

    # Build cumulative equity series
    sorted_days = sorted(daily_pnl.keys())
    cumulative_pnl = 0.0
    series = []
    for day in sorted_days:
        cumulative_pnl += daily_pnl[day]
        series.append((day, starting_capital + cumulative_pnl))

    return series


def compute_daily_sharpe(
    equity_series: List[tuple],
    window_days: Optional[int] = None,
) -> float:
    """Compute annualized Sharpe ratio from daily equity series.

    Args:
        equity_series: List of (date_str, equity_value) tuples.
        window_days: If set, only use the last N calendar days.

    Returns:
        Annualized Sharpe ratio (raw, not normalized).
        Returns 0.0 if insufficient data (< 2 days).
    """
    if len(equity_series) < 2:
        return 0.0

    series = equity_series
    if window_days is not None and window_days > 0:
        # Filter to last N calendar days
        from datetime import datetime as dt, timedelta
        cutoff = (dt.strptime(series[-1][0], '%Y-%m-%d') - timedelta(days=window_days)).strftime('%Y-%m-%d')
        series = [(d, e) for d, e in series if d >= cutoff]
        if len(series) < 2:
            return 0.0

    # Compute daily returns: R_t = (Equity_t - Equity_{t-1}) / Equity_{t-1}
    equities = np.array([e for _, e in series], dtype=np.float64)
    returns = np.diff(equities) / equities[:-1]

    # Filter out infinite/nan returns
    returns = returns[np.isfinite(returns)]
    if len(returns) < 2:
        return 0.0

    mean_ret = float(np.mean(returns))
    std_ret = float(np.std(returns, ddof=1))

    if std_ret < 1e-15:
        return 0.0

    return (mean_ret / std_ret) * ANNUALIZATION_FACTOR


def compute_drawdown_resilience_v4(trades: List[dict]) -> float:
    """Compute drawdown resilience score [0, 1] using distribution_core.

    Components (weighted):
      40% depth_score:    1 - min(max_dd / 5.0, 1.0)
      20% avg_dd_score:   1 - min(avg_dd / 3.0, 1.0)
      20% recovery_score: 1 / (1 + avg_recovery_days / 30)
      20% cycle_score:    min(num_cycles / 5.0, 1.0)
    """
    from ..distribution_core.drawdown_engine import DrawdownEngine
    from ..distribution_core.models import (
        OutcomeType,
        PriceZone,
        RegimeBucket,
        SessionBucket,
        StrategyCategory,
        TradeRecord,
    )

    # Convert trade dicts to TradeRecord objects
    trade_records = []
    for i, t in enumerate(trades):
        r = t.get('r_multiple')
        pnl = t.get('pnl', 0.0)
        risk = t.get('planned_risk')
        if r is None or risk is None or risk <= 0:
            continue
        exit_time = t.get('exit_time')
        if exit_time is None:
            continue
        try:
            trade_records.append(TradeRecord(
                trade_id=str(i),
                strategy_category=StrategyCategory.PREMIUM_COLLECTION,
                structure_signature="afi_v4",
                entry_timestamp=exit_time,  # approx — entry not stored in AFI query
                exit_timestamp=exit_time,
                risk_unit=float(risk),
                pnl_realized=float(pnl),
                r_multiple=float(r),
                regime_bucket=RegimeBucket.GOLDILOCKS_1,
                session_bucket=SessionBucket.MORNING,
                price_zone=PriceZone.INSIDE_CONVEX_BAND,
                outcome_type=OutcomeType.STRUCTURAL_WIN if float(r) >= 0 else OutcomeType.STRUCTURAL_LOSS,
            ))
        except (ValueError, TypeError):
            continue

    if not trade_records:
        return 0.5  # neutral

    engine = DrawdownEngine()
    profile = engine.compute(trade_records)

    depth_score = 1.0 - min(profile.max_drawdown_depth / V4_DD_MAX_CAP, 1.0)
    avg_dd_score = 1.0 - min(profile.average_drawdown_depth / V4_DD_AVG_CAP, 1.0)
    recovery_score = 1.0 / (1.0 + profile.average_recovery_days / V4_DD_RECOVERY_DAYS)
    num_cycles = len(profile.drawdown_depths)
    cycle_score = min(num_cycles / V4_DD_CYCLES_CAP, 1.0)

    return (
        V4_DD_DEPTH_W * depth_score
        + V4_DD_AVG_W * avg_dd_score
        + V4_DD_RECOVERY_W * recovery_score
        + V4_DD_CYCLES_W * cycle_score
    )


def compute_payoff_asymmetry_v4(trades: List[dict]) -> float:
    """Compute payoff asymmetry [0, 1]: avg_win / avg_loss, capped at 3:1."""
    r_multiples = np.array([t['r_multiple'] for t in trades if t.get('r_multiple') is not None], dtype=np.float64)
    if len(r_multiples) < 2:
        return 0.5

    wins = r_multiples[r_multiples > 0]
    losses = r_multiples[r_multiples < 0]

    if len(wins) == 0 or len(losses) == 0:
        return 0.0 if len(wins) == 0 else 1.0

    avg_win = float(np.mean(wins))
    avg_loss = float(abs(np.mean(losses)))

    if avg_loss < 1e-15:
        return 1.0

    ratio = avg_win / avg_loss
    return min(ratio / V4_ASYMMETRY_CAP, 1.0)


def compute_recovery_velocity_v4(trades: List[dict]) -> float:
    """Compute recovery velocity [0, 1]: speed from trough to new equity high.

    Uses DrawdownProfile.average_recovery_trades.
    Faster recovery → higher score.
    """
    from ..distribution_core.drawdown_engine import DrawdownEngine
    from ..distribution_core.models import (
        OutcomeType,
        PriceZone,
        RegimeBucket,
        SessionBucket,
        StrategyCategory,
        TradeRecord,
    )

    trade_records = []
    for i, t in enumerate(trades):
        r = t.get('r_multiple')
        pnl = t.get('pnl', 0.0)
        risk = t.get('planned_risk')
        if r is None or risk is None or risk <= 0:
            continue
        exit_time = t.get('exit_time')
        if exit_time is None:
            continue
        try:
            trade_records.append(TradeRecord(
                trade_id=str(i),
                strategy_category=StrategyCategory.PREMIUM_COLLECTION,
                structure_signature="afi_v4",
                entry_timestamp=exit_time,
                exit_timestamp=exit_time,
                risk_unit=float(risk),
                pnl_realized=float(pnl),
                r_multiple=float(r),
                regime_bucket=RegimeBucket.GOLDILOCKS_1,
                session_bucket=SessionBucket.MORNING,
                price_zone=PriceZone.INSIDE_CONVEX_BAND,
                outcome_type=OutcomeType.STRUCTURAL_WIN if float(r) >= 0 else OutcomeType.STRUCTURAL_LOSS,
            ))
        except (ValueError, TypeError):
            continue

    if not trade_records:
        return 0.5

    engine = DrawdownEngine()
    profile = engine.compute(trade_records)

    if profile.average_recovery_trades > 0:
        return 1.0 / (1.0 + profile.average_recovery_trades / V4_VELOCITY_TRADES)
    return 0.5  # neutral when no drawdowns measured


def compute_confidence_v4(trade_count: int, active_days: int) -> float:
    """Dual-gate confidence: sqrt(N/(N+50)) × sqrt(D/(D+30))."""
    n = max(trade_count, 0)
    d = max(active_days, 0)
    return math.sqrt(n / (n + V4_CRED_TRADES_K)) * math.sqrt(d / (d + V4_CRED_DAYS_K))


def compute_afi_v4(
    trades: List[dict],
    starting_capital: float,
    wss_history: List[dict],
) -> AFIResultV4:
    """Compute AFI v4 dual-index scores.

    Args:
        trades: Closed trades sorted by exit_time ASC (from DB).
        starting_capital: Starting capital in cents.
        wss_history: Prior WSS history for trend detection.

    Returns:
        AFIResultV4 with AFI-M, AFI-R, composite, raw values, and components.
    """
    from datetime import datetime as dt

    trade_count = len(trades)

    # Count active trading days
    active_days_set = set()
    for t in trades:
        exit_time = t.get('exit_time')
        if exit_time is not None:
            if hasattr(exit_time, 'strftime'):
                active_days_set.add(exit_time.strftime('%Y-%m-%d'))
            else:
                active_days_set.add(str(exit_time).split('T')[0])
    active_days = len(active_days_set)

    # Build daily equity series (realized only)
    equity_series = build_daily_equity_series(trades, starting_capital)

    # --- Daily Sharpe ---
    raw_sharpe_lifetime = compute_daily_sharpe(equity_series, window_days=None)
    raw_sharpe_momentum = compute_daily_sharpe(equity_series, window_days=AFI_M_WINDOW_DAYS)

    norm_sharpe = normalize_sharpe(raw_sharpe_lifetime)

    # --- Drawdown Resilience ---
    drawdown_resilience = compute_drawdown_resilience_v4(trades)

    # --- Payoff Asymmetry ---
    payoff_asymmetry = compute_payoff_asymmetry_v4(trades)

    # --- Recovery Velocity ---
    recovery_velocity = compute_recovery_velocity_v4(trades)

    # --- Confidence ---
    confidence = compute_confidence_v4(trade_count, active_days)

    # --- AFI-R ---
    components = AFIComponentsV4(
        daily_sharpe=norm_sharpe,
        drawdown_resilience=drawdown_resilience,
        payoff_asymmetry=payoff_asymmetry,
        recovery_velocity=recovery_velocity,
    )

    afi_r_raw = confidence * (
        V4_W_SHARPE * components.daily_sharpe
        + V4_W_DRAWDOWN * components.drawdown_resilience
        + V4_W_ASYMMETRY * components.payoff_asymmetry
        + V4_W_RECOVERY * components.recovery_velocity
    )
    afi_r = compress(afi_r_raw)

    # --- AFI-M ---
    norm_sharpe_m = normalize_sharpe(raw_sharpe_momentum)
    afi_m_raw = norm_sharpe_m  # AFI-M is purely momentum Sharpe
    afi_m = compress(afi_m_raw)

    # --- Composite ---
    composite = V4_R_WEIGHT * afi_r + V4_M_WEIGHT * afi_m

    # --- Trend (reuse existing WSS-based trend) ---
    # For v4, compute a WSS-equivalent from the 4 components for trend tracking
    wss_equivalent = (
        V4_W_SHARPE * components.daily_sharpe
        + V4_W_DRAWDOWN * components.drawdown_resilience
        + V4_W_ASYMMETRY * components.payoff_asymmetry
        + V4_W_RECOVERY * components.recovery_velocity
    )
    # Append today's wss_equivalent to history for trend
    today_str = dt.utcnow().strftime('%Y-%m-%d')
    trend_history = [e for e in wss_history if e.get('date') != today_str]
    trend_history.append({'date': today_str, 'wss': round(wss_equivalent, 5)})
    trend = compute_trend(trend_history)

    # --- Provisional ---
    provisional = trade_count < V4_MIN_TRADES or active_days < V4_MIN_ACTIVE_DAYS

    return AFIResultV4(
        afi_m=round(afi_m, 2),
        afi_r=round(afi_r, 2),
        composite=round(composite, 2),
        raw_afi_m=round(afi_m_raw, 6),
        raw_afi_r=round(afi_r_raw, 6),
        raw_sharpe_lifetime=round(raw_sharpe_lifetime, 6),
        components=components,
        confidence=round(confidence, 6),
        trend=trend,
        is_provisional=provisional,
        trade_count=trade_count,
        active_days=active_days,
        computed_at=dt.utcnow(),
    )
