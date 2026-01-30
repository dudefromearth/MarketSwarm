"""
Liquidity Effectiveness Calculator - MEL Model for Microstructure.

Determines if microstructure signals are predictive or noise.

Expected Behaviors to Monitor:
- Absorption accuracy (do absorption signals hold?)
- Sweep predictiveness (do sweeps predict continuation?)
- Slippage vs expectation
- Bid/ask imbalance utility

Failure/Stress Indicators:
- Liquidity vacuum events
- Spread widening
- Quote stuffing / instability
- Absorption failures
"""

from typing import Dict, Any, Tuple, List, Optional
from datetime import datetime
import logging

from .mel_calculator import MELCalculator
from .mel_models import MELConfig, Confidence


class LiquidityEffectivenessCalculator(MELCalculator):
    """
    Calculator for Liquidity/Microstructure effectiveness.

    Measures how predictive microstructure signals are.
    """

    @property
    def model_name(self) -> str:
        return "liquidity"

    def _get_required_data_fields(self) -> List[str]:
        return [
            "bid_ask_spread",
            "bid_size",
            "ask_size",
            "absorption_events",
            "sweep_events",
            "price_history",
        ]

    def calculate_effectiveness(self, market_data: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        """
        Calculate liquidity effectiveness score.

        Composite of:
        - Absorption accuracy (30%)
        - Sweep predictiveness (25%)
        - Slippage vs expectation (20%)
        - Bid/ask imbalance utility (25%)
        """
        detail = {}

        # Extract data
        bid_ask_spread = market_data.get("bid_ask_spread")
        bid_size = market_data.get("bid_size")
        ask_size = market_data.get("ask_size")
        absorption_events = market_data.get("absorption_events", [])
        sweep_events = market_data.get("sweep_events", [])
        price_history = market_data.get("price_history", [])
        avg_spread = market_data.get("avg_spread")

        # If minimal data, return neutral
        if not price_history:
            return 65.0, {"note": "Insufficient data for liquidity effectiveness"}

        # 1. Absorption Accuracy (30%)
        detail["absorption_accuracy"] = self._calculate_absorption_accuracy(
            absorption_events, price_history
        )

        # 2. Sweep Predictiveness (25%)
        detail["sweep_predictiveness"] = self._calculate_sweep_predictiveness(
            sweep_events, price_history
        )

        # 3. Slippage vs Expectation (20%)
        detail["slippage_state"] = self._analyze_slippage(
            bid_ask_spread, avg_spread, market_data
        )
        detail["slippage_score"] = self._score_slippage(detail["slippage_state"])

        # 4. Bid/Ask Imbalance Utility (25%)
        detail["imbalance_utility"] = self._calculate_imbalance_utility(
            bid_size, ask_size, price_history
        )
        detail["imbalance_state"] = self._classify_imbalance_utility(detail["imbalance_utility"])

        # Stress indicators
        detail["stress_indicators"] = self._check_stress_indicators(
            market_data, detail
        )

        # Current liquidity state
        detail["liquidity_state"] = self._determine_liquidity_state(
            bid_ask_spread, avg_spread, detail
        )

        # Composite effectiveness score
        effectiveness = (
            detail["absorption_accuracy"] * 0.30 +
            detail["sweep_predictiveness"] * 0.25 +
            detail["slippage_score"] * 0.20 +
            detail["imbalance_utility"] * 0.25
        )

        return self.normalize_score(effectiveness), detail

    def _calculate_absorption_accuracy(
        self,
        absorption_events: List[Dict],
        price_history: List[Dict],
    ) -> float:
        """
        Calculate percentage of absorption signals that hold.

        Absorption = large resting order absorbs aggressive flow.
        Accuracy = price doesn't break through the absorption level.
        """
        if not absorption_events:
            return 65.0  # Neutral if no data

        holds = 0
        total = len(absorption_events)

        for event in absorption_events:
            level = event.get("level")
            direction = event.get("direction")  # "bid" or "ask"
            timestamp = event.get("timestamp")

            if level is None:
                continue

            # Check if level held in subsequent price action
            held = self._check_level_held(level, direction, price_history, timestamp)
            if held:
                holds += 1

        return self.calculate_rate(holds, total, 65.0)

    def _check_level_held(
        self,
        level: float,
        direction: str,
        price_history: List[Dict],
        event_timestamp: Optional[datetime] = None,
    ) -> bool:
        """Check if an absorption level held."""
        tolerance = 1.0  # Points

        # Simple check: did price break through level significantly?
        for bar in price_history[-10:]:  # Check recent bars
            low = bar.get("low")
            high = bar.get("high")

            if direction == "bid" and low and low < level - tolerance:
                return False  # Bid absorption failed
            if direction == "ask" and high and high > level + tolerance:
                return False  # Ask absorption failed

        return True

    def _calculate_sweep_predictiveness(
        self,
        sweep_events: List[Dict],
        price_history: List[Dict],
    ) -> float:
        """
        Calculate percentage of sweeps followed by continuation.

        Sweep = aggressive order taking out multiple levels.
        Predictive = price continues in sweep direction.
        """
        if not sweep_events:
            return 65.0

        continuations = 0
        total = len(sweep_events)

        for event in sweep_events:
            direction = event.get("direction")  # "up" or "down"
            price_at_sweep = event.get("price")
            timestamp = event.get("timestamp")

            if price_at_sweep is None or direction is None:
                continue

            # Check if price continued in that direction
            continued = self._check_continuation(
                price_at_sweep, direction, price_history
            )
            if continued:
                continuations += 1

        return self.calculate_rate(continuations, total, 65.0)

    def _check_continuation(
        self,
        start_price: float,
        direction: str,
        price_history: List[Dict],
    ) -> bool:
        """Check if price continued in sweep direction."""
        if not price_history:
            return False

        # Check last few bars for continuation
        recent_closes = [
            b.get("close") or b.get("price")
            for b in price_history[-5:]
        ]
        recent_closes = [c for c in recent_closes if c]

        if not recent_closes:
            return False

        final_price = recent_closes[-1]
        threshold = 5.0  # Points of continuation

        if direction == "up":
            return final_price > start_price + threshold
        else:
            return final_price < start_price - threshold

    def _analyze_slippage(
        self,
        current_spread: Optional[float],
        avg_spread: Optional[float],
        market_data: Dict[str, Any],
    ) -> str:
        """
        Analyze slippage vs expectations.

        Returns: 'Normal', 'Elevated', 'Severe'
        """
        if current_spread is None:
            return "Normal"

        if avg_spread is None:
            avg_spread = 0.10  # Default assumption

        ratio = current_spread / avg_spread if avg_spread > 0 else 1.0

        if ratio <= 1.5:
            return "Normal"
        elif ratio <= 3.0:
            return "Elevated"
        else:
            return "Severe"

    def _score_slippage(self, slippage: str) -> float:
        """Convert slippage state to score."""
        return self.score_categorical(slippage, {
            "Normal": 90,
            "Elevated": 50,
            "Severe": 15,
        })

    def _calculate_imbalance_utility(
        self,
        bid_size: Optional[float],
        ask_size: Optional[float],
        price_history: List[Dict],
    ) -> float:
        """
        Calculate how useful bid/ask imbalance is for prediction.

        Check if imbalance correctly predicts short-term direction.
        """
        if bid_size is None or ask_size is None or not price_history:
            return 65.0

        total_size = bid_size + ask_size
        if total_size == 0:
            return 65.0

        # Calculate imbalance ratio
        imbalance = (bid_size - ask_size) / total_size

        # Check recent price direction
        if len(price_history) < 2:
            return 65.0

        recent = price_history[-5:] if len(price_history) >= 5 else price_history
        closes = [b.get("close") or b.get("price") for b in recent]
        closes = [c for c in closes if c]

        if len(closes) < 2:
            return 65.0

        price_direction = closes[-1] - closes[0]

        # Did imbalance predict direction?
        if imbalance > 0.1 and price_direction > 0:
            return 85.0  # Bid imbalance, price up - correct
        elif imbalance < -0.1 and price_direction < 0:
            return 85.0  # Ask imbalance, price down - correct
        elif abs(imbalance) <= 0.1:
            return 65.0  # Neutral imbalance
        else:
            return 40.0  # Imbalance didn't predict

    def _classify_imbalance_utility(self, score: float) -> str:
        """Classify imbalance utility."""
        if score >= 75:
            return "Useful"
        elif score >= 50:
            return "Mixed"
        else:
            return "Noise"

    def _check_stress_indicators(
        self,
        market_data: Dict[str, Any],
        detail: Dict[str, Any],
    ) -> Dict[str, bool]:
        """Check for liquidity stress indicators."""
        spread = market_data.get("bid_ask_spread")
        avg_spread = market_data.get("avg_spread", 0.10)

        indicators = {
            "liquidity_vacuum": detail.get("liquidity_state") == "Vacuum",
            "spread_widening": spread and avg_spread and spread > avg_spread * 3,
            "quote_instability": market_data.get("quote_instability", False),
            "absorption_failures": detail.get("absorption_accuracy", 65) < 40,
        }
        return indicators

    def _determine_liquidity_state(
        self,
        spread: Optional[float],
        avg_spread: Optional[float],
        detail: Dict[str, Any],
    ) -> str:
        """Determine current liquidity state."""
        if spread is None:
            return "Normal"

        if avg_spread is None:
            avg_spread = 0.10

        ratio = spread / avg_spread if avg_spread > 0 else 1.0

        if ratio > 5:
            return "Vacuum"
        elif ratio > 2:
            return "Thin"
        elif ratio <= 1.2:
            return "Normal"
        else:
            return "Adequate"

    def _determine_confidence(
        self,
        detail: Dict[str, Any],
        market_data: Dict[str, Any],
    ) -> Confidence:
        """Determine confidence in liquidity effectiveness."""
        absorption_events = market_data.get("absorption_events", [])
        sweep_events = market_data.get("sweep_events", [])
        price_history = market_data.get("price_history", [])

        # Need microstructure data for high confidence
        if not absorption_events and not sweep_events:
            if market_data.get("bid_ask_spread") is not None:
                return Confidence.MEDIUM
            return Confidence.LOW

        if len(price_history) < 20:
            return Confidence.MEDIUM

        return Confidence.HIGH
