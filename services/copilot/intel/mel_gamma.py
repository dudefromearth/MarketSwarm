"""
Gamma Effectiveness Calculator - MEL Model for Dealer/Gamma Structure.

Determines if dealer gamma positioning is actually controlling price behavior.

Expected Behaviors to Monitor:
- Level respect rate (do prices respect gamma levels?)
- Mean reversion success (do excursions revert to gamma magnet?)
- Pin duration (how long does price stay at dominant gamma level?)
- Violation frequency/magnitude
- Gamma level stability
- Dealer control consistency

Failure/Stress Indicators:
- Rapid level churn
- Large impulse ignoring gamma
- Late-day breakdown
- Event override detected
"""

from typing import Dict, Any, Tuple, List, Optional
from datetime import datetime, timedelta
import logging

from .mel_calculator import MELCalculator
from .mel_models import MELConfig, Confidence


class GammaEffectivenessCalculator(MELCalculator):
    """
    Calculator for Gamma/Dealer Structure effectiveness.

    Measures how well dealer gamma positioning is controlling price action.
    """

    @property
    def model_name(self) -> str:
        return "gamma"

    def _get_required_data_fields(self) -> List[str]:
        return [
            "spot_price",
            "gamma_levels",
            "zero_gamma",
            "gamma_magnet",
            "price_history",
        ]

    def calculate_effectiveness(self, market_data: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        """
        Calculate gamma effectiveness score.

        Composite of:
        - Level respect rate (25%)
        - Mean reversion success (25%)
        - Pin duration (15%)
        - Violation frequency (15%)
        - Gamma level stability (10%)
        - Dealer control consistency (10%)
        """
        detail = {}

        # Extract data
        spot = market_data.get("spot_price")
        gamma_levels = market_data.get("gamma_levels", [])
        zero_gamma = market_data.get("zero_gamma")
        gamma_magnet = market_data.get("gamma_magnet")
        price_history = market_data.get("price_history", [])

        # If no data, return neutral score
        if not gamma_levels or not price_history:
            return 65.0, {"note": "Insufficient data for gamma effectiveness"}

        # 1. Level Respect Rate (25%)
        detail["level_respect_rate"] = self._calculate_level_respect_rate(
            price_history, gamma_levels
        )

        # 2. Mean Reversion Success (25%)
        detail["mean_reversion_success"] = self._calculate_mean_reversion_success(
            price_history, gamma_magnet, zero_gamma
        )

        # 3. Pin Duration (15%)
        detail["pin_duration"] = self._calculate_pin_duration(
            price_history, gamma_magnet
        )
        detail["pin_duration_score"] = self._score_pin_duration(detail["pin_duration"])

        # 4. Violation Frequency (15%)
        violations = self._analyze_violations(price_history, gamma_levels)
        detail["violation_frequency"] = violations["frequency"]
        detail["violation_magnitude"] = violations["magnitude"]
        detail["violation_score"] = 100 - self._score_violation_frequency(violations["frequency"])

        # 5. Gamma Level Stability (10%)
        detail["gamma_level_stability"] = self._calculate_gamma_stability(gamma_levels)
        detail["stability_score"] = self._score_stability(detail["gamma_level_stability"])

        # 6. Dealer Control Consistency (10%)
        detail["dealer_control"] = self._calculate_dealer_control(market_data)
        detail["dealer_control_score"] = self._score_dealer_control(detail["dealer_control"])

        # Stress indicators
        detail["stress_indicators"] = self._check_stress_indicators(
            market_data, detail
        )

        # Time-of-day behavior
        detail["time_of_day"] = self._analyze_time_of_day(price_history, gamma_levels)

        # Composite effectiveness score
        effectiveness = (
            detail["level_respect_rate"] * 0.25 +
            detail["mean_reversion_success"] * 0.25 +
            detail["pin_duration_score"] * 0.15 +
            detail["violation_score"] * 0.15 +
            detail["stability_score"] * 0.10 +
            detail["dealer_control_score"] * 0.10
        )

        return self.normalize_score(effectiveness), detail

    def _calculate_level_respect_rate(
        self,
        price_history: List[Dict],
        gamma_levels: List[Dict],
    ) -> float:
        """
        Calculate percentage of times price respects gamma levels.

        A "test" is when price approaches a gamma level.
        A "respect" is when price reverses or consolidates at that level.
        """
        if not price_history or not gamma_levels:
            return 65.0  # Neutral

        # Extract level prices
        levels = [lvl.get("strike") or lvl.get("price") for lvl in gamma_levels if lvl]
        if not levels:
            return 65.0

        tests = 0
        respects = 0

        # Simple implementation - look for price approaching levels
        tolerance = 5.0  # Points tolerance for "approaching"

        for i in range(1, len(price_history)):
            prev_price = price_history[i - 1].get("price") or price_history[i - 1].get("close")
            curr_price = price_history[i].get("price") or price_history[i].get("close")

            if prev_price is None or curr_price is None:
                continue

            for level in levels:
                # Did price approach this level?
                prev_dist = abs(prev_price - level)
                curr_dist = abs(curr_price - level)

                if prev_dist > tolerance and curr_dist <= tolerance:
                    # Price approached the level
                    tests += 1

                    # Check if it reversed (next few bars)
                    if i + 3 < len(price_history):
                        future_prices = [
                            p.get("price") or p.get("close")
                            for p in price_history[i:i+3]
                        ]
                        future_prices = [p for p in future_prices if p is not None]

                        if future_prices:
                            # Did price move away from the level direction it came from?
                            approach_dir = 1 if curr_price > prev_price else -1
                            future_dir = 1 if future_prices[-1] > curr_price else -1

                            if approach_dir != future_dir:
                                # Reversed at level
                                respects += 1

        return self.calculate_rate(respects, tests, 65.0)

    def _calculate_mean_reversion_success(
        self,
        price_history: List[Dict],
        gamma_magnet: Optional[float],
        zero_gamma: Optional[float],
    ) -> float:
        """
        Calculate percentage of excursions that revert to gamma magnet.

        An excursion is when price moves away from gamma magnet.
        Success is when it returns within a session.
        """
        if not price_history or not gamma_magnet:
            return 65.0

        excursions = 0
        reversions = 0
        threshold = 10.0  # Points to consider an excursion

        in_excursion = False
        excursion_start_idx = 0

        for i, bar in enumerate(price_history):
            price = bar.get("price") or bar.get("close")
            if price is None:
                continue

            dist = abs(price - gamma_magnet)

            if not in_excursion and dist > threshold:
                # Starting an excursion
                in_excursion = True
                excursion_start_idx = i
                excursions += 1

            elif in_excursion and dist <= threshold / 2:
                # Reverted to magnet
                in_excursion = False
                reversions += 1

        return self.calculate_rate(reversions, excursions, 65.0)

    def _calculate_pin_duration(
        self,
        price_history: List[Dict],
        gamma_magnet: Optional[float],
    ) -> str:
        """
        Calculate how long price stays pinned to dominant gamma level.

        Returns: 'Strong', 'Medium', 'Weak'
        """
        if not price_history or not gamma_magnet:
            return "Medium"

        near_magnet = 0
        tolerance = 5.0

        for bar in price_history:
            price = bar.get("price") or bar.get("close")
            if price and abs(price - gamma_magnet) <= tolerance:
                near_magnet += 1

        pct = near_magnet / len(price_history) * 100 if price_history else 0

        if pct >= 50:
            return "Strong"
        elif pct >= 25:
            return "Medium"
        else:
            return "Weak"

    def _score_pin_duration(self, duration: str) -> float:
        """Convert pin duration to numeric score."""
        return self.score_categorical(duration, {
            "Strong": 90,
            "Medium": 60,
            "Weak": 30,
        })

    def _analyze_violations(
        self,
        price_history: List[Dict],
        gamma_levels: List[Dict],
    ) -> Dict[str, str]:
        """
        Analyze gamma level violations.

        Returns frequency (Low/Medium/High) and magnitude (Contained/Extended).
        """
        if not price_history or not gamma_levels:
            return {"frequency": "Medium", "magnitude": "Contained"}

        levels = [lvl.get("strike") or lvl.get("price") for lvl in gamma_levels if lvl]
        if not levels:
            return {"frequency": "Medium", "magnitude": "Contained"}

        violations = []

        for bar in price_history:
            high = bar.get("high")
            low = bar.get("low")
            if high is None or low is None:
                continue

            for level in levels:
                # Did price move through this level?
                if low < level < high:
                    # Calculate magnitude of the violation
                    magnitude = max(high - level, level - low)
                    violations.append(magnitude)

        violation_rate = len(violations) / len(price_history) * 100 if price_history else 0

        if violation_rate < 10:
            frequency = "Low"
        elif violation_rate < 25:
            frequency = "Medium"
        else:
            frequency = "High"

        avg_magnitude = sum(violations) / len(violations) if violations else 0

        if avg_magnitude < 5:
            magnitude = "Contained"
        else:
            magnitude = "Extended"

        return {"frequency": frequency, "magnitude": magnitude}

    def _score_violation_frequency(self, frequency: str) -> float:
        """Convert violation frequency to penalty score."""
        return self.score_categorical(frequency, {
            "Low": 10,
            "Medium": 40,
            "High": 80,
        })

    def _calculate_gamma_stability(self, gamma_levels: List[Dict]) -> str:
        """
        Calculate how much gamma levels shift intraday.

        Returns: 'Stable', 'Shifting', 'Churning'
        """
        # In a real implementation, this would compare
        # gamma levels across multiple snapshots
        if not gamma_levels:
            return "Stable"

        # Placeholder - would need historical gamma level data
        return "Stable"

    def _score_stability(self, stability: str) -> float:
        """Convert stability to numeric score."""
        return self.score_categorical(stability, {
            "Stable": 90,
            "Shifting": 60,
            "Churning": 20,
        })

    def _calculate_dealer_control(self, market_data: Dict[str, Any]) -> str:
        """
        Calculate overall dealer positioning coherence.

        Returns: 'High', 'Medium', 'Low'
        """
        # Would integrate with GEX ratio, put/call gamma balance, etc.
        gex_ratio = market_data.get("gex_ratio")

        if gex_ratio is None:
            return "Medium"

        if abs(gex_ratio) > 2:
            return "High"
        elif abs(gex_ratio) > 1:
            return "Medium"
        else:
            return "Low"

    def _score_dealer_control(self, control: str) -> float:
        """Convert dealer control to numeric score."""
        return self.score_categorical(control, {
            "High": 90,
            "Medium": 60,
            "Low": 30,
        })

    def _check_stress_indicators(
        self,
        market_data: Dict[str, Any],
        detail: Dict[str, Any],
    ) -> Dict[str, bool]:
        """Check for failure/stress indicators."""
        indicators = {
            "rapid_level_churn": detail.get("gamma_level_stability") == "Churning",
            "large_impulse_ignoring_gamma": detail.get("violation_magnitude") == "Extended",
            "late_day_breakdown": False,  # Would need time context
            "event_override_detected": len(market_data.get("event_flags", [])) > 0,
        }
        return indicators

    def _analyze_time_of_day(
        self,
        price_history: List[Dict],
        gamma_levels: List[Dict],
    ) -> Dict[str, str]:
        """
        Analyze gamma behavior by time of day.

        Returns behavior for Open, Midday, Late Session phases.
        """
        # Placeholder - would analyze price_history timestamps
        return {
            "open_discovery": "Normal",
            "midday_balance": "Stable",
            "late_session": "Structured",
        }

    def _determine_confidence(
        self,
        detail: Dict[str, Any],
        market_data: Dict[str, Any],
    ) -> Confidence:
        """
        Determine confidence in the gamma effectiveness score.

        Based on data quality and quantity.
        """
        price_history = market_data.get("price_history", [])
        gamma_levels = market_data.get("gamma_levels", [])

        # Need sufficient history
        if len(price_history) < 10:
            return Confidence.LOW
        if len(price_history) < 50:
            return Confidence.MEDIUM

        # Need gamma levels
        if len(gamma_levels) < 3:
            return Confidence.MEDIUM

        return Confidence.HIGH
