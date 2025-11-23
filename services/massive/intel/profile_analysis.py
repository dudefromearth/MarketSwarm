"""
profile_analysis.py — Vexy Structural Analysis Engine

Given the permanent SPX volume profile (0.1 SPX bins), this module produces:

  • HVN (High Volume Nodes)
  • LVN (Low Volume Nodes)
  • Volume Gaps / Voids
  • Distribution Shape (unimodal, bimodal, composite)
  • Balance Areas (value areas)
  • Volume Point of Control (POC)
  • Support/Resistance candidates
  • Meta summary for Vexy-AI generation

This is the primary analytic layer that Vexy consumes.
"""

import redis
import numpy as np
from scipy.signal import find_peaks

REDIS_HOST = "localhost"
REDIS_PORT = 6380
REDIS_DB   = 0

KEY_BINS = "volume_profile:SPX:bins"
KEY_META = "volume_profile:SPX:meta"


# ---------------------------------------------------------------
# Load profile from MARKET_REDIS
# ---------------------------------------------------------------
def load_profile():
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    bins = r.hgetall(KEY_BINS)

    xs = np.array(sorted(int(k) for k in bins.keys()))
    vs = np.array([float(bins[str(k)]) for k in xs])

    return xs, vs


# ---------------------------------------------------------------
# Core Structural Metrics
# ---------------------------------------------------------------
def compute_hvns(xs, vs, prominence=0.15):
    """Identify high-volume peaks (HVNs)."""
    peaks, _ = find_peaks(vs, prominence=prominence * vs.max())
    return xs[peaks].tolist()


def compute_lvns(xs, vs, prominence=0.10):
    """Identify volume troughs (LVNs)."""
    inv = vs.max() - vs
    troughs, _ = find_peaks(inv, prominence=prominence * inv.max())
    return xs[troughs].tolist()


def compute_gaps(xs, vs, threshold=0.02):
    """Volume voids: bins where volume < 2% of mean."""
    mean = vs.mean()
    mask = vs < (mean * threshold)
    gaps = xs[mask]
    return gaps.tolist()


def compute_distribution_shape(vs):
    """Unimodal / Bimodal / Multimodal classification."""
    peaks, _ = find_peaks(vs, prominence=0.1 * vs.max())
    n = len(peaks)
    if n == 1:
        return "unimodal"
    if n == 2:
        return "bimodal"
    return "composite"


def compute_balance_area(xs, vs, pct=0.70):
    """70% value area (market profile equivalent)."""
    total = vs.sum()
    target = total * pct

    order = np.argsort(vs)[::-1]  # high → low
    included = set()
    running = 0

    for idx in order:
        included.add(xs[idx])
        running += vs[idx]
        if running >= target:
            break

    return sorted(included)


def compute_poc(xs, vs):
    """Point of Control."""
    idx = np.argmax(vs)
    return int(xs[idx])


def compute_support_resistance(hvns, lvns):
    """Simple S/R classifier: HVNs = support, LVNs = resistance."""
    return {
        "support_levels": hvns[:5],
        "resistance_levels": lvns[:5]
    }


# ---------------------------------------------------------------
# Main API
# ---------------------------------------------------------------
def analyze_volume_profile():
    xs, vs = load_profile()

    hvns = compute_hvns(xs, vs)
    lvns = compute_lvns(xs, vs)
    gaps = compute_gaps(xs, vs)
    shape = compute_distribution_shape(vs)
    value_area = compute_balance_area(xs, vs)
    poc = compute_poc(xs, vs)
    sr = compute_support_resistance(hvns, lvns)

    return {
        "poc": poc,
        "distribution_shape": shape,
        "hvns": hvns,
        "lvns": lvns,
        "gaps": gaps,
        "value_area": value_area,
        "support_levels": sr["support_levels"],
        "resistance_levels": sr["resistance_levels"],
        "range": {
            "min": int(xs.min()),
            "max": int(xs.max()),
            "levels": len(xs)
        },
        "note": (
            "This structural snapshot is designed for Vexy-AI. "
            "It contains peak nodes, voids, balance regions, "
            "modal structure, and S/R candidates."
        )
    }


if __name__ == "__main__":
    import json
    profile = analyze_volume_profile()
    print(json.dumps(profile, indent=2))