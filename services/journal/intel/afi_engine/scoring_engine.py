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

from .models import AFIComponents, TrendSignal

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
