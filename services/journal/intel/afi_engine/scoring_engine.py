"""
AFI — Scoring Engine

Normalization, WSS computation, logistic compression,
robustness scoring, RB dampening, and trend detection.

All constants are internal and not disclosed to users (anti-gaming).
"""
from __future__ import annotations

import math
from typing import List, Optional

import numpy as np

from .models import AFIComponents, TrendSignal

# ---------------------------------------------------------------------------
#  WSS Component Weights (not disclosed)
# ---------------------------------------------------------------------------
W_R_SLOPE: float = 0.35
W_SHARPE: float = 0.25
W_LTC: float = 0.20
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
#  Robustness Coefficients
# ---------------------------------------------------------------------------
RB_ALPHA: float = 2.0    # √(trade_count) weight
RB_BETA: float = 1.5     # √(active_days) weight
RB_GAMMA: float = 10.0   # regime_diversity weight (input 0-1)
RB_DELTA: float = 3.0    # survived_drawdowns weight

# ---------------------------------------------------------------------------
#  Dampening Constant
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
    """Weighted Structural Score from normalised components."""
    return (
        W_R_SLOPE * components.r_slope
        + W_SHARPE * components.sharpe
        + W_LTC * components.ltc
        + W_DD_CONTAINMENT * components.dd_containment
    )


def compress(wss: float) -> float:
    """Logistic compression: WSS → AFI_raw (soft 300-900 range)."""
    return CENTER + K * math.tanh(S * (wss - SHIFT))


def compute_robustness(
    trade_count: int,
    active_days: int,
    regime_diversity: float,
    survived_dds: int,
) -> float:
    """Robustness score (0-100+, uncapped)."""
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
    """Apply RB dampening to slow AFI movement.

    AFI_next = prior + (raw - prior) × 1/(1 + RB/C)

    First computation (prior_afi=None): returns afi_raw directly.
    """
    if prior_afi is None:
        return afi_raw

    factor = 1.0 / (1.0 + rb / RB_C)
    return prior_afi + (afi_raw - prior_afi) * factor


def compute_trend(wss_history: List[dict]) -> TrendSignal:
    """Detect trend from recent WSS history.

    Uses linear regression slope on WSS values from the last
    TREND_WINDOW_DAYS days.

    Each entry: {"date": "YYYY-MM-DD", "wss": float}
    """
    if len(wss_history) < 3:
        return TrendSignal.STABLE

    # Use last TREND_WINDOW_DAYS entries (one per day max)
    recent = wss_history[-TREND_WINDOW_DAYS:]
    if len(recent) < 3:
        return TrendSignal.STABLE

    y = np.array([entry["wss"] for entry in recent], dtype=np.float64)
    x = np.arange(len(y), dtype=np.float64)

    # Simple OLS slope
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
STABILITY_VAR_CAP: float = 0.05  # WSS variance cap for normalization


def compute_robustness_v2(
    regime_diversity: float,
    survived_dds: int,
    distribution_stability: float,
) -> float:
    """Robustness v2: no trade_count, no active_days.

    RB_v2 = 10 × regime_diversity + 3 × survived_dds + 5 × distribution_stability
    """
    return (
        10.0 * max(0.0, min(1.0, regime_diversity))
        + 3.0 * max(survived_dds, 0)
        + 5.0 * max(0.0, min(1.0, distribution_stability))
    )


def compute_distribution_stability(wss_history: List[dict]) -> float:
    """Compute distribution stability from full lifetime WSS history.

    Low WSS variance = high stability = consistent structural quality.
    Returns [0, 1]. If < 3 data points, returns 0.5 (neutral).
    """
    if len(wss_history) < 3:
        return 0.5

    wss_values = np.array([e["wss"] for e in wss_history], dtype=np.float64)
    variance = float(np.var(wss_values))
    return 1.0 - min(variance / STABILITY_VAR_CAP, 1.0)


# ---------------------------------------------------------------------------
#  v3: Convexity Amplifier & Behavioral Consistency
# ---------------------------------------------------------------------------
TAIL_RATIO_CAP: float = 5.0
CONVEXITY_RATIO_CAP: float = 4.0
ROLLING_WSS_WINDOW: int = 20


def compute_tail_ratio(r_multiples: np.ndarray) -> float:
    """Normalized tail ratio: avg_win / avg_loss, capped to [0, 1].

    Measures whether average wins exceed average losses in magnitude.
    """
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
    """Normalized convexity ratio: max_win / max_loss, capped to [0, 1].

    Measures right-tail expansion relative to left-tail worst case.
    """
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


def compute_rolling_wss_stability(
    r_multiples: np.ndarray,
    weights: np.ndarray,
) -> float:
    """Compute behavioral stability from rolling WSS over trade history.

    Slides a ROLLING_WSS_WINDOW-trade window across all trades,
    computes WSS per window, then measures variance of the WSS series.

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

        # Compute components for this window
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


def compute_bcm(stability_score: float) -> float:
    """Behavioral Consistency Multiplier.

    BCM = 0.90 + 0.20 * stability_score
    Range: [0.90, 1.10]
    """
    return 0.90 + 0.20 * max(0.0, min(1.0, stability_score))
