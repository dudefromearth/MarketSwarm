"""
Distribution Core v1.0.0 — Normalization Engine

Deterministic 0-1 normalization for CII components.
All bounds are frozen for v1.0.0. No dynamic scaling.

Normalization bounds (frozen):
    skew:           [-1, +1]  → [0, 1]   via (skew - min) / (max - min)
    LTC:            [0, 1]    → [0, 1]    clamped for safety
    ROCPR:          [0, cap]  → [0, 1]    cap = 2.0 (200% return on risk)
    drawdown_vol:   [0, cap]  → [0, 1]    cap = 1.0 R-units std dev

CII v1.0.0 Formula:
    CII = (0.35 * normalized_skew)
        + (0.30 * normalized_LTC)
        + (0.20 * normalized_ROCPR)
        - (0.15 * normalized_drawdown_volatility)

    Result clamped to [0, 1].
    < 0.5 → Convexity at risk
    < 0.4 → Structural warning
    < 0.3 → Convexity collapse

CII must NEVER include Sharpe.
"""

from .models import NormalizationBounds

# Frozen v1.0.0 bounds
DEFAULT_BOUNDS = NormalizationBounds()

# Frozen v1.0.0 CII weights
CII_WEIGHT_SKEW = 0.35
CII_WEIGHT_LTC = 0.30
CII_WEIGHT_ROCPR = 0.20
CII_WEIGHT_DD_VOL = 0.15  # subtracted


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp value to [lo, hi] range."""
    return max(lo, min(hi, value))


class NormalizationEngine:
    """
    Deterministic normalization with frozen bounds.

    All values pass through this engine before CII computation.
    No dynamic scaling. Bounds versioned with Distribution Core.
    """

    def __init__(self, bounds: NormalizationBounds | None = None):
        self.bounds = bounds or DEFAULT_BOUNDS

    def normalize_skew(self, skew: float) -> float:
        """
        Normalize skew from [skew_min, skew_max] → [0, 1].

        Formula: clamp((skew - min) / (max - min), 0, 1)
        Default: maps [-1, +1] → [0, 1]
        """
        span = self.bounds.skew_max - self.bounds.skew_min
        if span == 0:
            return 0.5
        raw = (skew - self.bounds.skew_min) / span
        return _clamp(raw)

    def normalize_ltc(self, ltc: float) -> float:
        """
        Normalize LTC. Already 0-1 by definition, clamped for safety.
        """
        return _clamp(ltc, self.bounds.ltc_min, self.bounds.ltc_max)

    def normalize_rocpr(self, rocpr: float) -> float:
        """
        Normalize ROCPR from [0, rocpr_cap] → [0, 1].

        Negative ROCPR maps to 0. Values above cap map to 1.
        Default cap: 2.0 (200% return on risk deployed).
        """
        if self.bounds.rocpr_cap == 0:
            return 0.0
        raw = rocpr / self.bounds.rocpr_cap
        return _clamp(raw)

    def normalize_drawdown_volatility(self, dd_vol: float) -> float:
        """
        Normalize drawdown volatility from [0, dd_vol_cap] → [0, 1].

        Higher dd_vol = worse. This is SUBTRACTED in CII.
        Default cap: 1.0 R-units std dev.
        """
        if self.bounds.drawdown_vol_cap == 0:
            return 0.0
        raw = dd_vol / self.bounds.drawdown_vol_cap
        return _clamp(raw)

    def compute_cii(
        self,
        skew: float | None,
        ltc: float | None,
        rocpr: float | None,
        drawdown_volatility: float | None,
    ) -> float | None:
        """
        Convexity Integrity Index v1.0.0.

        CII = (0.35 * norm_skew) + (0.30 * norm_ltc)
            + (0.20 * norm_rocpr) - (0.15 * norm_dd_vol)

        Returns None if any input is None (insufficient data).
        Result clamped to [0, 1].
        """
        if any(v is None for v in (skew, ltc, rocpr, drawdown_volatility)):
            return None

        n_skew = self.normalize_skew(skew)
        n_ltc = self.normalize_ltc(ltc)
        n_rocpr = self.normalize_rocpr(rocpr)
        n_dd_vol = self.normalize_drawdown_volatility(drawdown_volatility)

        cii = (
            CII_WEIGHT_SKEW * n_skew
            + CII_WEIGHT_LTC * n_ltc
            + CII_WEIGHT_ROCPR * n_rocpr
            - CII_WEIGHT_DD_VOL * n_dd_vol
        )

        return _clamp(cii)
