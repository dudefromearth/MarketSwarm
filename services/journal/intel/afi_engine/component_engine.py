"""
AFI — Component Engine

Computes the four raw AFI structural metrics:
  A) R-Slope   (35% of WSS)
  B) Sharpe    (25% of WSS)
  C) LTC       (20% of WSS)
  D) DD Containment (20% of WSS)

All functions are pure computation — no IO, no DB, no Redis.
"""
from __future__ import annotations

from typing import List, Tuple

import numpy as np

from .recency import weighted_mean, weighted_std

# ---------------------------------------------------------------------------
#  A) R-Slope — Weighted Least Squares on cumulative R
# ---------------------------------------------------------------------------

def compute_r_slope(r_multiples: np.ndarray, weights: np.ndarray) -> float:
    """Weighted linear regression slope on the cumulative R equity curve.

    cum_R[i] = Σ R[0..i]
    x[i] = i  (trade index)

    Minimise Σ w_i (cum_R_i - (α + β x_i))²
    Returns β (the WLS slope).
    """
    n = len(r_multiples)
    if n < 2:
        return 0.0

    cum_r = np.cumsum(r_multiples)
    x = np.arange(n, dtype=np.float64)

    # Weighted means
    x_bar = np.dot(weights, x)
    y_bar = np.dot(weights, cum_r)

    # Weighted covariance & variance
    dx = x - x_bar
    dy = cum_r - y_bar
    cov_xy = np.dot(weights, dx * dy)
    var_x = np.dot(weights, dx * dx)

    if abs(var_x) < 1e-15:
        return 0.0

    return float(cov_xy / var_x)


# ---------------------------------------------------------------------------
#  B) Sharpe — Weighted Sharpe on R-multiples
# ---------------------------------------------------------------------------

def compute_sharpe(r_multiples: np.ndarray, weights: np.ndarray) -> float:
    """Weighted Sharpe ratio on R-series.

    Sharpe = weighted_mean(R) / weighted_std(R)
    Risk-free rate omitted — R-multiples are already risk-adjusted.
    """
    if len(r_multiples) < 2:
        return 0.0

    std = weighted_std(r_multiples, weights)
    if std < 1e-8:
        return 0.0

    return weighted_mean(r_multiples, weights) / std


# ---------------------------------------------------------------------------
#  C) LTC — Left Tail Containment (recency-weighted)
# ---------------------------------------------------------------------------

def compute_ltc(r_multiples: np.ndarray, weights: np.ndarray) -> float:
    """Recency-weighted Left Tail Containment.

    For losses (R < 0):
      contained = 1 if |R| <= 1.0 (within planned risk)
      contained = 0 if |R| > 1.0  (exceeded planned risk)

    LTC = Σ(w_i × contained_i) / Σ(w_i)   over losses only.
    If no losses: LTC = 1.0
    """
    loss_mask = r_multiples < 0
    if not np.any(loss_mask):
        return 1.0

    loss_r = r_multiples[loss_mask]
    loss_w = weights[loss_mask]

    contained = (np.abs(loss_r) <= 1.0).astype(np.float64)
    w_sum = loss_w.sum()
    if w_sum < 1e-15:
        return 1.0

    return float(np.dot(loss_w, contained) / w_sum)


# ---------------------------------------------------------------------------
#  D) Drawdown Containment
# ---------------------------------------------------------------------------

# Constants
DD_CAP: float = 5.0        # 5R max drawdown = floor score
RECOVERY_CAP: float = 20.0 # 20 trades to recover = middle score


def _identify_drawdown_periods(
    r_multiples: np.ndarray,
) -> List[Tuple[float, int, bool]]:
    """Identify drawdown periods from the R-based equity curve.

    Returns list of (depth, recovery_trades, recovered) tuples.
    - depth: peak - trough (in R-units, positive)
    - recovery_trades: trades from trough to recovery (0 if unrecovered)
    - recovered: True if equity recovered to or above prior peak
    """
    n = len(r_multiples)
    if n == 0:
        return []

    equity = np.cumsum(r_multiples)
    peak = np.maximum.accumulate(equity)

    periods: List[Tuple[float, int, bool]] = []
    in_dd = False
    dd_peak = 0.0
    dd_trough = 0.0
    trough_idx = 0

    for i in range(n):
        if equity[i] < peak[i]:
            if not in_dd:
                # Entering drawdown
                in_dd = True
                dd_peak = peak[i]
                dd_trough = equity[i]
                trough_idx = i
            else:
                # Still in drawdown — update trough if deeper
                if equity[i] < dd_trough:
                    dd_trough = equity[i]
                    trough_idx = i
        else:
            if in_dd:
                # Recovered
                depth = dd_peak - dd_trough
                recovery_trades = i - trough_idx
                periods.append((depth, recovery_trades, True))
                in_dd = False

    # Handle unrecovered drawdown at end of series
    if in_dd:
        depth = dd_peak - dd_trough
        periods.append((depth, 0, False))

    return periods


def compute_dd_containment(r_multiples: np.ndarray) -> float:
    """Composite drawdown containment: depth(50%) + recovery speed(50%).

    Uses full equity curve (no recency weighting — drawdowns are
    multi-trade events; recency captured by R-slope and Sharpe).
    """
    periods = _identify_drawdown_periods(r_multiples)

    if not periods:
        return 1.0

    # --- Depth score (50%) ---
    max_dd = max(depth for depth, _, _ in periods)
    depth_score = 1.0 - min(max_dd / DD_CAP, 1.0)

    # --- Recovery score (50%) ---
    recovery_speeds = []
    for depth, rec_trades, recovered in periods:
        if recovered:
            recovery_speeds.append(1.0 / (1.0 + rec_trades / RECOVERY_CAP))
        else:
            recovery_speeds.append(0.0)

    recovery_score = float(np.mean(recovery_speeds)) if recovery_speeds else 1.0

    return 0.50 * depth_score + 0.50 * recovery_score
