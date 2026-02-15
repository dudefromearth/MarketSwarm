"""
Distribution Core v1.0.0

Single authoritative source for all return distribution metrics.
All consumers (Edge Lab, SEE, ALE, AOL) must import from here.
No other module may independently compute these metrics.
"""

from .models import (
    StrategyCategory,
    RegimeBucket,
    SessionBucket,
    PriceZone,
    OutcomeType,
    RollingWindow,
    TradeRecord,
    DrawdownProfile,
    TailContribution,
    StrategyMixExposure,
    DistributionResult,
    RegimeDistributionResult,
    NormalizationBounds,
)
from .metric_engine import MetricEngine
from .regime_engine import RegimeEngine
from .window_engine import WindowEngine
from .normalization_engine import NormalizationEngine
from .drawdown_engine import DrawdownEngine
from .versioning import MetricVersion, VersionedBundle

__version__ = "1.0.0"

__all__ = [
    "StrategyCategory",
    "RegimeBucket",
    "SessionBucket",
    "PriceZone",
    "OutcomeType",
    "RollingWindow",
    "TradeRecord",
    "DrawdownProfile",
    "TailContribution",
    "StrategyMixExposure",
    "DistributionResult",
    "RegimeDistributionResult",
    "NormalizationBounds",
    "MetricEngine",
    "RegimeEngine",
    "WindowEngine",
    "NormalizationEngine",
    "DrawdownEngine",
    "MetricVersion",
    "VersionedBundle",
    "compute_distribution_metrics",
    "compute_regime_segmented_metrics",
    "compute_strategy_mix",
]


def compute_distribution_metrics(
    trades: list[TradeRecord],
    window: RollingWindow,
) -> DistributionResult:
    """
    Primary entry point. Compute all distribution metrics for a trade set.

    Applies window filtering, minimum sample enforcement, and versioned output.
    """
    window_eng = WindowEngine()
    filtered = window_eng.apply(trades, window)
    return _compute_from_filtered(filtered, window)


def compute_regime_segmented_metrics(
    trades: list[TradeRecord],
    window: RollingWindow,
) -> RegimeDistributionResult:
    """Compute distribution metrics segmented by regime bucket."""
    window_eng = WindowEngine()
    filtered = window_eng.apply(trades, window)
    regime_eng = RegimeEngine()
    buckets = regime_eng.segment(filtered)

    results = {}
    for bucket in RegimeBucket:
        bucket_trades = buckets.get(bucket, [])
        results[bucket.value] = _compute_from_filtered(bucket_trades, window)

    return RegimeDistributionResult(
        zombieland=results.get("zombieland"),
        goldilocks_1=results.get("goldilocks_1"),
        goldilocks_2=results.get("goldilocks_2"),
        chaos=results.get("chaos"),
    )


def compute_strategy_mix(
    trades: list[TradeRecord],
    window: RollingWindow,
) -> StrategyMixExposure:
    """Compute strategy category exposure weights for a window."""
    window_eng = WindowEngine()
    filtered = window_eng.apply(trades, window)
    metric_eng = MetricEngine()
    return metric_eng.compute_strategy_mix(filtered)


def _compute_from_filtered(
    trades: list[TradeRecord],
    window: RollingWindow,
) -> DistributionResult:
    """Internal: compute full metric bundle from pre-filtered trades."""
    from datetime import datetime, timezone

    metric_eng = MetricEngine()
    norm_eng = NormalizationEngine()
    dd_eng = DrawdownEngine()
    versioning = MetricVersion()

    n = len(trades)
    min_sample = WindowEngine.MIN_SAMPLE

    if n < min_sample:
        return DistributionResult(
            version=versioning.current_version(),
            timestamp_generated=datetime.now(timezone.utc),
            window=window.value,
            trade_count=n,
            skew=None,
            ltc=None,
            rocpr=None,
            avg_winner=None,
            avg_loser=None,
            avg_w_avg_l_ratio=None,
            profit_factor=None,
            tail_contribution=None,
            drawdown=None,
            strategy_mix=None,
            cii=None,
            excess_kurtosis=None,
            tail_ratio=None,
        )

    skew = metric_eng.compute_skew(trades)
    kurtosis = metric_eng.compute_excess_kurtosis(trades)
    ltc = metric_eng.compute_ltc(trades)
    rocpr = metric_eng.compute_rocpr(trades)
    avg_w, avg_l, ratio = metric_eng.compute_avg_winner_loser(trades)
    pf = metric_eng.compute_profit_factor(trades)
    tail = metric_eng.compute_tail_contribution(trades)
    tail_ratio = metric_eng.compute_tail_ratio(trades)
    drawdown = dd_eng.compute(trades)
    mix = metric_eng.compute_strategy_mix(trades)

    cii = norm_eng.compute_cii(
        skew=skew,
        ltc=ltc,
        rocpr=rocpr,
        drawdown_volatility=drawdown.drawdown_volatility,
    )

    return DistributionResult(
        version=versioning.current_version(),
        timestamp_generated=datetime.now(timezone.utc),
        window=window.value,
        trade_count=n,
        skew=skew,
        ltc=ltc,
        rocpr=rocpr,
        avg_winner=avg_w,
        avg_loser=avg_l,
        avg_w_avg_l_ratio=ratio,
        profit_factor=pf,
        tail_contribution=tail,
        drawdown=drawdown,
        strategy_mix=mix,
        cii=cii,
        excess_kurtosis=kurtosis,
        tail_ratio=tail_ratio,
    )
