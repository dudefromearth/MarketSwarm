"""
AFI — Recency Weighting Engine

Exponential decay with configurable half-life.
All trades contribute; recent trades contribute more.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Sequence

import numpy as np

# --- Constants (not disclosed to users) ---
HALF_LIFE_DAYS: float = 180.0
LAMBDA: float = math.log(2) / HALF_LIFE_DAYS  # ≈ 0.003851


def compute_weights(
    exit_timestamps: Sequence[datetime],
    reference_time: datetime,
) -> np.ndarray:
    """Return normalised exponential-decay weights for each trade.

    weight_i = exp(-λ × age_in_days_i)
    Normalised so Σ weights = 1.

    Parameters
    ----------
    exit_timestamps : sequence of datetime, ordered ascending
    reference_time  : "now" anchor — typically datetime.utcnow()

    Returns
    -------
    np.ndarray of shape (n,), dtype float64, sums to 1.
    """
    if len(exit_timestamps) == 0:
        return np.empty(0, dtype=np.float64)

    ages = np.array(
        [(reference_time - t).total_seconds() / 86400.0 for t in exit_timestamps],
        dtype=np.float64,
    )
    # Clamp negative ages (future timestamps) to 0
    ages = np.maximum(ages, 0.0)

    raw = np.exp(-LAMBDA * ages)
    total = raw.sum()
    if total < 1e-15:
        # All trades infinitely old — uniform fallback
        return np.full(len(exit_timestamps), 1.0 / len(exit_timestamps))
    return raw / total


def compute_equal_weights(n: int) -> np.ndarray:
    """Return uniform 1/n weights for n trades (v2: no recency decay)."""
    if n <= 0:
        return np.empty(0, dtype=np.float64)
    return np.full(n, 1.0 / n, dtype=np.float64)


def weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    """Weighted mean: Σ(w_i × v_i)  (weights already normalised)."""
    if len(values) == 0:
        return 0.0
    return float(np.dot(weights, values))


def weighted_std(values: np.ndarray, weights: np.ndarray) -> float:
    """Weighted standard deviation: sqrt(Σ(w_i × (v_i - μ)²))."""
    if len(values) < 2:
        return 0.0
    mu = weighted_mean(values, weights)
    variance = float(np.dot(weights, (values - mu) ** 2))
    return math.sqrt(max(variance, 0.0))
