"""
Distribution Core v1.0.0 — Window Engine

Standardized rolling window filtering with minimum sample enforcement.

Windows (non-configurable in Phase 0):
    7D, 30D, 90D, 180D

Rules:
    - Time-based rolling window from reference date.
    - Minimum sample enforcement: ≥10 trades per window.
    - Deterministic ordering by exit_timestamp.
    - Trades filtered by exit_timestamp (trade must be closed within window).
"""

from datetime import datetime, timedelta, timezone

from .models import TradeRecord, RollingWindow

# Window durations in calendar days
WINDOW_DAYS: dict[RollingWindow, int] = {
    RollingWindow.D7: 7,
    RollingWindow.D30: 30,
    RollingWindow.D90: 90,
    RollingWindow.D180: 180,
}


class WindowEngine:
    """
    Rolling window filter with minimum sample enforcement.

    Filters trades by exit_timestamp falling within the window period,
    then sorts deterministically by exit_timestamp.
    """

    MIN_SAMPLE = 10

    def __init__(self, reference_time: datetime | None = None):
        """
        Args:
            reference_time: The "now" anchor for window computation.
                            Defaults to current UTC time. Override for
                            deterministic replay and testing.
        """
        self._reference_time = reference_time

    @property
    def reference_time(self) -> datetime:
        if self._reference_time is not None:
            return self._reference_time
        return datetime.now(timezone.utc)

    def apply(
        self,
        trades: list[TradeRecord],
        window: RollingWindow,
    ) -> list[TradeRecord]:
        """
        Filter trades to those within the rolling window period.

        Returns trades sorted by exit_timestamp (deterministic ordering).
        Trades with exit_timestamp within [reference_time - window_days, reference_time]
        are included.

        Note: This method does NOT enforce minimum sample size.
        That is the caller's responsibility (the __init__.py entry points
        check trade_count and return None-filled results if < MIN_SAMPLE).
        """
        days = WINDOW_DAYS[window]
        cutoff = self.reference_time - timedelta(days=days)

        filtered = [
            t for t in trades
            if t.exit_timestamp >= cutoff and t.exit_timestamp <= self.reference_time
        ]

        filtered.sort(key=lambda t: t.exit_timestamp)
        return filtered

    def meets_minimum_sample(self, trades: list[TradeRecord]) -> bool:
        """Check if trade count meets minimum sample threshold."""
        return len(trades) >= self.MIN_SAMPLE
