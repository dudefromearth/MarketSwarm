"""
Distribution Core v1.0.0 — Regime Engine

FOTW structural regime classification using fixed VIX thresholds.
Pure deterministic classification. No percentiles. No rolling history.

Internal (4 structural regimes):
    ZOMBIELAND    : VIX ≤ 17
    GOLDILOCKS_1  : 17 < VIX ≤ 24
    GOLDILOCKS_2  : 24 < VIX ≤ 32
    CHAOS         : VIX > 32

External/UI (3 user-facing):
    Zombieland  = ZOMBIELAND
    Goldilocks  = GOLDILOCKS_1 + GOLDILOCKS_2
    Chaos       = CHAOS

Regime bucket is computed ONCE at trade entry and never recomputed retroactively.
"""

from .models import TradeRecord, RegimeBucket

# Fixed VIX thresholds — frozen for v1.0.0
VIX_ZOMBIELAND_CEILING = 17.0
VIX_GOLDILOCKS_1_CEILING = 24.0
VIX_GOLDILOCKS_2_CEILING = 32.0


class RegimeEngine:
    """
    Deterministic regime classification and segmentation.

    classify_vix() assigns a regime bucket from current VIX level.
    segment() groups trades by their pre-assigned regime bucket.
    """

    @staticmethod
    def classify_vix(current_vix: float) -> RegimeBucket:
        """
        Classify VIX into a structural regime bucket.

        Called ONCE at trade entry time. Result is stored and never
        recomputed retroactively.

        Args:
            current_vix: VIX level at trade entry.

        Returns:
            RegimeBucket enum value.
        """
        if current_vix <= VIX_ZOMBIELAND_CEILING:
            return RegimeBucket.ZOMBIELAND
        elif current_vix <= VIX_GOLDILOCKS_1_CEILING:
            return RegimeBucket.GOLDILOCKS_1
        elif current_vix <= VIX_GOLDILOCKS_2_CEILING:
            return RegimeBucket.GOLDILOCKS_2
        else:
            return RegimeBucket.CHAOS

    @staticmethod
    def segment(
        trades: list[TradeRecord],
    ) -> dict[RegimeBucket, list[TradeRecord]]:
        """
        Group trades by their pre-assigned regime bucket.

        Does NOT reclassify. Uses the regime_bucket stored on each TradeRecord.
        """
        buckets: dict[RegimeBucket, list[TradeRecord]] = {
            b: [] for b in RegimeBucket
        }
        for t in trades:
            buckets[t.regime_bucket].append(t)
        return buckets

    @staticmethod
    def is_goldilocks(bucket: RegimeBucket) -> bool:
        """Check if a bucket is either Goldilocks variant (for UI aggregation)."""
        return bucket in (RegimeBucket.GOLDILOCKS_1, RegimeBucket.GOLDILOCKS_2)
