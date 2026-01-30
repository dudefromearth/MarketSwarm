"""
Session Effectiveness Calculator - MEL Model for Time-of-Day Structure.

Determines if typical session structure is present.

Expected Behaviors to Monitor:
- Open discovery (normal price discovery at open)
- Midday balance (typical midday consolidation)
- Late resolution (end-of-day directional resolution)
- Liquidity window respect (MOC/VWAP windows behave normally)

Failure/Stress Indicators:
- Extended discovery (open lasting too long)
- No midday balance (continuous trending)
- Late chaos (no resolution, volatility spike)
- Liquidity window failure (MOC/VWAP abnormal)
"""

from typing import Dict, Any, Tuple, List, Optional
from datetime import datetime, time, timedelta
import logging

from .mel_calculator import MELCalculator
from .mel_models import MELConfig, Confidence


class SessionEffectivenessCalculator(MELCalculator):
    """
    Calculator for Session/Time-of-Day effectiveness.

    Measures how well typical session structure is present.
    """

    # RTH session times (Eastern)
    RTH_OPEN = time(9, 30)
    RTH_CLOSE = time(16, 0)
    MIDDAY_START = time(11, 30)
    MIDDAY_END = time(14, 0)
    LATE_SESSION_START = time(14, 30)
    MOC_WINDOW_START = time(15, 45)

    @property
    def model_name(self) -> str:
        return "session"

    def _get_required_data_fields(self) -> List[str]:
        return [
            "price_history",
            "session_start",
            "current_time",
        ]

    def calculate_effectiveness(self, market_data: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        """
        Calculate session effectiveness score.

        Composite of:
        - Open discovery (30%)
        - Midday balance (25%)
        - Late resolution (25%)
        - Liquidity window respect (20%)
        """
        detail = {}

        # Extract data
        price_history = market_data.get("price_history", [])
        current_time = market_data.get("current_time") or datetime.now()
        vah = market_data.get("vah")
        val = market_data.get("val")
        volume_history = market_data.get("volume_history", [])

        # If minimal data, return neutral
        if not price_history:
            return 65.0, {"note": "Insufficient data for session effectiveness"}

        # Split price history by session phase
        open_bars, midday_bars, late_bars = self._split_by_session_phase(
            price_history, current_time
        )

        # 1. Open Discovery (30%)
        detail["open_discovery"] = self._analyze_open_discovery(open_bars, vah, val)
        detail["open_score"] = self._score_open_discovery(detail["open_discovery"])

        # 2. Midday Balance (25%)
        detail["midday_balance"] = self._analyze_midday_balance(midday_bars, vah, val)
        detail["midday_score"] = self._score_midday_balance(detail["midday_balance"])

        # 3. Late Resolution (25%)
        detail["late_resolution"] = self._analyze_late_resolution(late_bars, vah, val)
        detail["late_score"] = self._score_late_resolution(detail["late_resolution"])

        # 4. Liquidity Window Respect (20%)
        detail["liquidity_window"] = self._analyze_liquidity_windows(
            price_history, volume_history, current_time
        )
        detail["liquidity_score"] = self._score_liquidity_window(detail["liquidity_window"])

        # Stress indicators
        detail["stress_indicators"] = self._check_stress_indicators(detail)

        # Current session phase
        detail["current_phase"] = self._determine_current_phase(current_time)

        # Session structure summary
        detail["session_structure"] = {
            "open": detail["open_discovery"],
            "midday": detail["midday_balance"],
            "late": detail["late_resolution"],
        }

        # Composite effectiveness score
        effectiveness = (
            detail["open_score"] * 0.30 +
            detail["midday_score"] * 0.25 +
            detail["late_score"] * 0.25 +
            detail["liquidity_score"] * 0.20
        )

        return self.normalize_score(effectiveness), detail

    def _split_by_session_phase(
        self,
        price_history: List[Dict],
        current_time: datetime,
    ) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        """
        Split price history into session phases.

        Returns: (open_bars, midday_bars, late_bars)
        """
        open_bars = []
        midday_bars = []
        late_bars = []

        for bar in price_history:
            bar_time = bar.get("timestamp") or bar.get("time")

            if bar_time is None:
                continue

            # Parse time if string
            if isinstance(bar_time, str):
                try:
                    bar_time = datetime.fromisoformat(bar_time)
                except ValueError:
                    continue

            if isinstance(bar_time, datetime):
                t = bar_time.time()

                if self.RTH_OPEN <= t < self.MIDDAY_START:
                    open_bars.append(bar)
                elif self.MIDDAY_START <= t < self.LATE_SESSION_START:
                    midday_bars.append(bar)
                elif t >= self.LATE_SESSION_START:
                    late_bars.append(bar)

        # If no timestamps, split by position
        if not open_bars and not midday_bars and not late_bars:
            n = len(price_history)
            third = n // 3
            open_bars = price_history[:third]
            midday_bars = price_history[third:2*third]
            late_bars = price_history[2*third:]

        return open_bars, midday_bars, late_bars

    def _analyze_open_discovery(
        self,
        open_bars: List[Dict],
        vah: Optional[float],
        val: Optional[float],
    ) -> str:
        """
        Analyze opening discovery behavior.

        Returns: 'Normal', 'Extended', 'Absent'
        """
        if not open_bars:
            return "Normal"

        # Calculate opening range
        highs = [b.get("high") for b in open_bars if b.get("high")]
        lows = [b.get("low") for b in open_bars if b.get("low")]

        if not highs or not lows:
            return "Normal"

        open_range = max(highs) - min(lows)

        # Calculate expected range (from value area or default)
        if vah and val:
            expected_range = (vah - val) * 0.3  # ~30% of value area
        else:
            expected_range = 10.0  # Default assumption

        # Count directional changes (discovery = back and forth)
        direction_changes = self._count_direction_changes(open_bars)

        # Normal discovery: moderate range, several direction changes
        if direction_changes >= 2 and open_range <= expected_range * 2:
            return "Normal"
        elif open_range > expected_range * 2 or direction_changes < 2:
            return "Extended"  # Trending open or very wide
        else:
            return "Absent"

    def _score_open_discovery(self, discovery: str) -> float:
        """Score open discovery."""
        return self.score_categorical(discovery, {
            "Normal": 90,
            "Extended": 50,
            "Absent": 30,
        })

    def _analyze_midday_balance(
        self,
        midday_bars: List[Dict],
        vah: Optional[float],
        val: Optional[float],
    ) -> str:
        """
        Analyze midday balance behavior.

        Returns: 'Stable', 'Fragile', 'Absent'
        """
        if not midday_bars:
            return "Stable"

        # Calculate midday range
        highs = [b.get("high") for b in midday_bars if b.get("high")]
        lows = [b.get("low") for b in midday_bars if b.get("low")]

        if not highs or not lows:
            return "Stable"

        midday_range = max(highs) - min(lows)

        # Check if staying within value area
        if vah and val:
            va_range = vah - val
            in_va_count = 0

            for bar in midday_bars:
                close = bar.get("close") or bar.get("price")
                if close and val <= close <= vah:
                    in_va_count += 1

            in_va_pct = in_va_count / len(midday_bars) * 100 if midday_bars else 0

            if in_va_pct >= 70 and midday_range <= va_range * 0.5:
                return "Stable"
            elif in_va_pct >= 40:
                return "Fragile"
            else:
                return "Absent"
        else:
            # Without value area, use range contraction
            direction_changes = self._count_direction_changes(midday_bars)
            if direction_changes >= 3:
                return "Stable"
            elif direction_changes >= 1:
                return "Fragile"
            else:
                return "Absent"

    def _score_midday_balance(self, balance: str) -> float:
        """Score midday balance."""
        return self.score_categorical(balance, {
            "Stable": 90,
            "Fragile": 55,
            "Absent": 25,
        })

    def _analyze_late_resolution(
        self,
        late_bars: List[Dict],
        vah: Optional[float],
        val: Optional[float],
    ) -> str:
        """
        Analyze late session resolution.

        Returns: 'Clear', 'Mixed', 'Chaotic'
        """
        if not late_bars:
            return "Clear"

        # Calculate late session trend
        closes = [b.get("close") or b.get("price") for b in late_bars]
        closes = [c for c in closes if c]

        if len(closes) < 2:
            return "Clear"

        # Check for clear directional move
        start_price = closes[0]
        end_price = closes[-1]
        move = end_price - start_price

        # Calculate volatility of late session
        if len(closes) >= 3:
            avg = sum(closes) / len(closes)
            variance = sum((c - avg) ** 2 for c in closes) / len(closes)
            volatility = variance ** 0.5
        else:
            volatility = 0

        # Determine resolution type
        va_range = (vah - val) if vah and val else 20

        if abs(move) > va_range * 0.2 and volatility < va_range * 0.15:
            return "Clear"  # Directional move, low chop
        elif volatility > va_range * 0.3:
            return "Chaotic"  # High volatility, no direction
        else:
            return "Mixed"

    def _score_late_resolution(self, resolution: str) -> float:
        """Score late resolution."""
        return self.score_categorical(resolution, {
            "Clear": 90,
            "Mixed": 60,
            "Chaotic": 25,
        })

    def _analyze_liquidity_windows(
        self,
        price_history: List[Dict],
        volume_history: List[float],
        current_time: datetime,
    ) -> str:
        """
        Analyze behavior during liquidity windows (MOC, VWAP).

        Returns: 'Yes', 'Partial', 'No'
        """
        # Check if we're past MOC window time
        if isinstance(current_time, datetime):
            if current_time.time() < self.MOC_WINDOW_START:
                return "Yes"  # Haven't reached window yet

        # Look at final 15 minutes of available data
        moc_bars = price_history[-15:] if len(price_history) >= 15 else price_history

        if not moc_bars:
            return "Yes"

        # Check for abnormal behavior
        highs = [b.get("high") for b in moc_bars if b.get("high")]
        lows = [b.get("low") for b in moc_bars if b.get("low")]

        if not highs or not lows:
            return "Yes"

        moc_range = max(highs) - min(lows)

        # Compare to earlier bars
        earlier_bars = price_history[:-15] if len(price_history) > 15 else []
        if earlier_bars:
            earlier_highs = [b.get("high") for b in earlier_bars[-30:] if b.get("high")]
            earlier_lows = [b.get("low") for b in earlier_bars[-30:] if b.get("low")]

            if earlier_highs and earlier_lows:
                earlier_range = max(earlier_highs) - min(earlier_lows)
                avg_bar_range = earlier_range / 30

                if moc_range > avg_bar_range * 3:
                    return "No"  # Abnormally wide MOC
                elif moc_range > avg_bar_range * 2:
                    return "Partial"

        return "Yes"

    def _score_liquidity_window(self, window: str) -> float:
        """Score liquidity window behavior."""
        return self.score_categorical(window, {
            "Yes": 90,
            "Partial": 60,
            "No": 25,
        })

    def _count_direction_changes(self, bars: List[Dict]) -> int:
        """Count number of direction changes in price."""
        if len(bars) < 2:
            return 0

        changes = 0
        prev_direction = None

        for i in range(1, len(bars)):
            prev_close = bars[i - 1].get("close") or bars[i - 1].get("price")
            curr_close = bars[i].get("close") or bars[i].get("price")

            if prev_close is None or curr_close is None:
                continue

            direction = 1 if curr_close > prev_close else -1

            if prev_direction is not None and direction != prev_direction:
                changes += 1

            prev_direction = direction

        return changes

    def _check_stress_indicators(self, detail: Dict[str, Any]) -> Dict[str, bool]:
        """Check for session stress indicators."""
        indicators = {
            "extended_discovery": detail.get("open_discovery") == "Extended",
            "no_midday_balance": detail.get("midday_balance") == "Absent",
            "late_chaos": detail.get("late_resolution") == "Chaotic",
            "liquidity_window_failure": detail.get("liquidity_window") == "No",
        }
        return indicators

    def _determine_current_phase(self, current_time: datetime) -> str:
        """Determine current session phase."""
        if isinstance(current_time, datetime):
            t = current_time.time()

            if t < self.RTH_OPEN:
                return "pre_market"
            elif t < self.MIDDAY_START:
                return "open_discovery"
            elif t < self.LATE_SESSION_START:
                return "midday_balance"
            elif t < self.RTH_CLOSE:
                return "late_session"
            else:
                return "after_hours"

        return "unknown"

    def _determine_confidence(
        self,
        detail: Dict[str, Any],
        market_data: Dict[str, Any],
    ) -> Confidence:
        """Determine confidence in session effectiveness."""
        price_history = market_data.get("price_history", [])
        current_time = market_data.get("current_time")

        if len(price_history) < 10:
            return Confidence.LOW

        # Early in session = lower confidence
        if isinstance(current_time, datetime):
            t = current_time.time()
            if t < self.MIDDAY_START:
                return Confidence.MEDIUM

        if len(price_history) < 50:
            return Confidence.MEDIUM

        return Confidence.HIGH
