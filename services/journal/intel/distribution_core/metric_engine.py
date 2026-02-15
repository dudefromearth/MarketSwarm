"""
Distribution Core v1.0.0 — Metric Engine

Core distribution metric computations. All formulas frozen for v1.0.0.
Uses vectorized numpy for performance (<200ms for 10K trades).

Min sample enforcement is NOT this module's responsibility.
That belongs to window_engine.py. This module is pure computation.

Formulas:
    skew        = E[(R - μ)^3] / σ^3                    (σ=0 → 0)
    kurtosis    = E[(R - μ)^4] / σ^4 - 3                (excess kurtosis)
    LTC         = count(losses where |R| ≤ 1) / losses   (0 losses → 1.0)
    ROCPR       = sum(pnl) / sum(risk_unit)
    RTC         = sum(R where R > 1.5) / sum(R)          (sum(R) ≤ 0 → 0)
    LTC_contrib = sum(|R| where R < -1) / sum(|R|)       (sum(|R|) = 0 → 0)
    tail_ratio  = mean(top decile R) / |mean(bottom decile R)|
"""

import numpy as np

from .models import (
    TradeRecord,
    TailContribution,
    StrategyMixExposure,
    StrategyCategory,
)


class MetricEngine:
    """Stateless metric computation engine. All methods are pure functions."""

    @staticmethod
    def _r_array(trades: list[TradeRecord]) -> np.ndarray:
        """Extract R-multiples as numpy array."""
        return np.array([t.r_multiple for t in trades], dtype=np.float64)

    def compute_skew(self, trades: list[TradeRecord]) -> float | None:
        """
        Population skewness of R-multiples.

        Formula: E[(R - μ)^3] / σ^3
        If σ = 0, returns 0.0 (no variance = no skew).
        Returns None if trades is empty.
        """
        if not trades:
            return None
        r = self._r_array(trades)
        mu = np.mean(r)
        sigma = np.std(r, ddof=0)
        if sigma == 0:
            return 0.0
        return float(np.mean(((r - mu) / sigma) ** 3))

    def compute_excess_kurtosis(self, trades: list[TradeRecord]) -> float | None:
        """
        Excess kurtosis of R-multiples.

        Formula: E[(R - μ)^4] / σ^4 - 3
        Normal distribution = 0. Positive = fat tails.
        If σ = 0, returns 0.0.
        Returns None if trades is empty.
        """
        if not trades:
            return None
        r = self._r_array(trades)
        mu = np.mean(r)
        sigma = np.std(r, ddof=0)
        if sigma == 0:
            return 0.0
        return float(np.mean(((r - mu) / sigma) ** 4) - 3.0)

    def compute_ltc(self, trades: list[TradeRecord]) -> float | None:
        """
        Left Tail Containment.

        Formula: count(losses where |R| ≤ 1) / total_losses
        If total_losses = 0, returns 1.0 (perfect containment).
        Returns None if trades is empty.
        """
        if not trades:
            return None
        r = self._r_array(trades)
        losses = r[r < 0]
        if len(losses) == 0:
            return 1.0
        contained = np.sum(np.abs(losses) <= 1.0)
        return float(contained / len(losses))

    def compute_rocpr(self, trades: list[TradeRecord]) -> float | None:
        """
        Return on Capital Put at Risk.

        Formula: sum(pnl_realized) / sum(risk_unit)
        Returns None if trades is empty or total risk is zero.
        """
        if not trades:
            return None
        total_pnl = sum(t.pnl_realized for t in trades)
        total_risk = sum(t.risk_unit for t in trades)
        if total_risk == 0:
            return None
        return float(total_pnl / total_risk)

    def compute_avg_winner_loser(
        self, trades: list[TradeRecord]
    ) -> tuple[float | None, float | None, float | None]:
        """
        Average winner R, average loser |R|, and ratio.

        Returns (avg_winner, avg_loser, ratio).
        If no winners or no losers, affected values are None.
        Returns (None, None, None) if trades is empty.
        """
        if not trades:
            return None, None, None
        r = self._r_array(trades)
        winners = r[r > 0]
        losers = r[r < 0]

        avg_w = float(np.mean(winners)) if len(winners) > 0 else None
        avg_l = float(np.mean(np.abs(losers))) if len(losers) > 0 else None

        if avg_w is not None and avg_l is not None and avg_l > 0:
            ratio = avg_w / avg_l
        else:
            ratio = None

        return avg_w, avg_l, ratio

    def compute_profit_factor(self, trades: list[TradeRecord]) -> float | None:
        """
        Profit factor: sum(winning R) / sum(|losing R|).

        Returns None if no trades or no losers (infinite profit factor undefined).
        """
        if not trades:
            return None
        r = self._r_array(trades)
        gross_win = float(np.sum(r[r > 0]))
        gross_loss = float(np.sum(np.abs(r[r < 0])))
        if gross_loss == 0:
            return None
        return gross_win / gross_loss

    def compute_tail_contribution(
        self, trades: list[TradeRecord]
    ) -> TailContribution | None:
        """
        Right and left tail contribution.

        RTC = sum(R where R > 1.5) / sum(R)      — denominator ≤ 0 → 0
        LTC_c = sum(|R| where R < -1) / sum(|R|)  — denominator = 0 → 0

        Note: RTC interpretation is unstable if total R is near zero.
        A small positive total with a large right tail will show inflated RTC.
        This is correct per spec but consumers should interpret with context.

        Returns None if trades is empty.
        """
        if not trades:
            return None
        r = self._r_array(trades)

        # Right tail contribution
        sum_r = float(np.sum(r))
        if sum_r <= 0:
            rtc = 0.0
        else:
            right_tail = r[r > 1.5]
            rtc = float(np.sum(right_tail) / sum_r) if len(right_tail) > 0 else 0.0

        # Left tail contribution
        abs_r = np.abs(r)
        sum_abs_r = float(np.sum(abs_r))
        if sum_abs_r == 0:
            ltc_c = 0.0
        else:
            left_mask = r < -1.0
            ltc_c = float(np.sum(abs_r[left_mask]) / sum_abs_r)

        return TailContribution(
            right_tail_contribution=rtc,
            left_tail_contribution=ltc_c,
        )

    def compute_tail_ratio(self, trades: list[TradeRecord]) -> float | None:
        """
        Tail ratio: mean(top decile R) / |mean(bottom decile R)|.

        Decile split is floor-based: decile_size = max(1, n // 10).
        For n=19, top decile = top 1 trade, bottom decile = bottom 1 trade.
        For n=100, top decile = top 10 trades, bottom decile = bottom 10 trades.

        Returns None if empty, fewer than 10 trades, or bottom decile mean = 0.
        """
        if not trades:
            return None
        r = self._r_array(trades)
        n = len(r)
        if n < 10:
            return None

        sorted_r = np.sort(r)
        decile_size = max(1, n // 10)

        top_decile = sorted_r[-decile_size:]
        bottom_decile = sorted_r[:decile_size]

        top_mean = float(np.mean(top_decile))
        bottom_mean = float(np.mean(bottom_decile))

        if bottom_mean == 0:
            return None

        return top_mean / abs(bottom_mean)

    def compute_strategy_mix(
        self, trades: list[TradeRecord]
    ) -> StrategyMixExposure:
        """
        Strategy category exposure as normalized weights summing to 1.

        Returns zero weights if trades is empty.
        """
        n = len(trades)
        if n == 0:
            return StrategyMixExposure(
                convex_expansion=0.0,
                event_compression=0.0,
                premium_collection=0.0,
            )

        counts = {cat: 0 for cat in StrategyCategory}
        for t in trades:
            counts[t.strategy_category] += 1

        ce = counts[StrategyCategory.CONVEX_EXPANSION] / n
        ec = counts[StrategyCategory.EVENT_COMPRESSION] / n
        pc = counts[StrategyCategory.PREMIUM_COLLECTION] / n

        assert abs((ce + ec + pc) - 1.0) < 1e-9, (
            f"Strategy mix weights must sum to 1.0, got {ce + ec + pc}"
        )

        return StrategyMixExposure(
            convex_expansion=ce,
            event_compression=ec,
            premium_collection=pc,
        )
