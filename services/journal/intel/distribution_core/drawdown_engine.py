"""
Distribution Core v1.0.0 — Drawdown Engine (UCSP Foundation)

Computes drawdown metrics from cumulative R-multiple equity curve.

UCSP (Universal Compounding Stability Protocol) Foundation:
    Position size scaling has superlinear drawdown elasticity (E > 1).
    This engine exposes the primitives governance systems need to detect
    instability BEFORE it compounds. Not descriptive analytics — stability
    governance infrastructure.

Equity curve: cumulative sum of R-multiples.
Peak tracking: running maximum of equity curve.
Drawdown: peak - current equity (always >= 0).

A drawdown period starts when equity drops below its peak and ends
when equity recovers to a new peak. Each period captures:
    - depth:            max(peak - equity) during the period
    - duration_trades:  number of trades in the period
    - duration_days:    calendar days from period start to period end
    - recovery_trades:  trades from deepest point to recovery
    - recovery_days:    calendar days from deepest point to recovery

All computations are deterministic. No IO. No randomness.
Empty inputs return zero-filled safe structure.
"""

from datetime import timedelta

import numpy as np

from .models import TradeRecord, DrawdownProfile


class DrawdownEngine:
    """
    Drawdown computation with UCSP primitives.

    Builds cumulative R equity curve, tracks peaks, identifies
    drawdown periods, and computes depth/duration/recovery metrics.
    """

    def compute(self, trades: list[TradeRecord]) -> DrawdownProfile:
        """
        Compute full drawdown profile from trade sequence.

        Trades must be pre-sorted by exit_timestamp (window_engine
        guarantees this). Empty input returns zero-filled profile.
        """
        if not trades:
            return self._empty_profile()

        # Build cumulative R equity curve
        r_values = np.array([t.r_multiple for t in trades], dtype=np.float64)
        equity = np.cumsum(r_values)

        # Running peak (high watermark)
        peaks = np.maximum.accumulate(equity)

        # Drawdown at each point: how far below peak
        drawdowns = peaks - equity

        # Identify drawdown periods
        periods = self._identify_periods(trades, equity, peaks, drawdowns)

        # Extract metrics from periods
        if not periods:
            return DrawdownProfile(
                max_drawdown_depth=0.0,
                average_drawdown_depth=0.0,
                max_drawdown_duration_trades=0,
                max_drawdown_duration_days=0,
                average_drawdown_duration_trades=0.0,
                average_drawdown_duration_days=0.0,
                average_recovery_trades=0.0,
                average_recovery_days=0.0,
                drawdown_volatility=0.0,
                drawdown_depths=(),
                peak_equity_series=tuple(float(p) for p in peaks),
            )

        depths = [p["depth"] for p in periods]
        durations_trades = [p["duration_trades"] for p in periods]
        durations_days = [p["duration_days"] for p in periods]
        recovery_trades = [p["recovery_trades"] for p in periods]
        recovery_days = [p["recovery_days"] for p in periods]

        dd_vol = float(np.std(depths, ddof=0)) if len(depths) > 1 else 0.0

        return DrawdownProfile(
            max_drawdown_depth=max(depths),
            average_drawdown_depth=float(np.mean(depths)),
            max_drawdown_duration_trades=max(durations_trades),
            max_drawdown_duration_days=max(durations_days),
            average_drawdown_duration_trades=float(np.mean(durations_trades)),
            average_drawdown_duration_days=float(np.mean(durations_days)),
            average_recovery_trades=float(np.mean(recovery_trades)),
            average_recovery_days=float(np.mean(recovery_days)),
            drawdown_volatility=dd_vol,
            drawdown_depths=tuple(depths),
            peak_equity_series=tuple(float(p) for p in peaks),
        )

    def _identify_periods(
        self,
        trades: list[TradeRecord],
        equity: np.ndarray,
        peaks: np.ndarray,
        drawdowns: np.ndarray,
    ) -> list[dict]:
        """
        Identify discrete drawdown periods from equity curve.

        A drawdown period:
            - Starts at the trade AFTER equity was at its peak
              (first trade where equity < peak).
            - Ends when equity recovers to or exceeds the peak
              (or at the last trade if still in drawdown).
            - Depth is the maximum drawdown within the period.

        Each period dict contains:
            depth, duration_trades, duration_days,
            recovery_trades, recovery_days
        """
        n = len(equity)
        periods = []
        i = 0

        while i < n:
            # Skip non-drawdown trades
            if drawdowns[i] == 0:
                i += 1
                continue

            # Start of a drawdown period
            start_idx = i
            max_dd = drawdowns[i]
            max_dd_idx = i

            # Walk forward until recovery or end of trades
            j = i + 1
            while j < n and drawdowns[j] > 0:
                if drawdowns[j] > max_dd:
                    max_dd = drawdowns[j]
                    max_dd_idx = j
                j += 1

            # end_idx is the recovery point (or last trade if unrecovered)
            end_idx = j - 1 if j >= n else j

            # Duration: from start of drawdown to end (recovery or last trade)
            duration_trades = end_idx - start_idx + 1
            start_time = trades[start_idx].exit_timestamp
            end_time = trades[end_idx].exit_timestamp
            duration_days = max(0, (end_time - start_time).days)

            # Recovery: from deepest point to end of period
            recovery_trades = end_idx - max_dd_idx
            deepest_time = trades[max_dd_idx].exit_timestamp
            recovery_days = max(0, (end_time - deepest_time).days)

            periods.append({
                "depth": float(max_dd),
                "duration_trades": duration_trades,
                "duration_days": duration_days,
                "recovery_trades": recovery_trades,
                "recovery_days": recovery_days,
            })

            i = j + 1 if j < n else j

        return periods

    @staticmethod
    def _empty_profile() -> DrawdownProfile:
        """Zero-filled safe structure for empty inputs."""
        return DrawdownProfile(
            max_drawdown_depth=0.0,
            average_drawdown_depth=0.0,
            max_drawdown_duration_trades=0,
            max_drawdown_duration_days=0,
            average_drawdown_duration_trades=0.0,
            average_drawdown_duration_days=0.0,
            average_recovery_trades=0.0,
            average_recovery_days=0.0,
            drawdown_volatility=0.0,
            drawdown_depths=(),
            peak_equity_series=(),
        )
