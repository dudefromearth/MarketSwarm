"""
Volatility Effectiveness Calculator - MEL Model for Volatility Regime.

Determines if volatility models (IV, RV, regime) are descriptive of actual behavior.

Expected Behaviors to Monitor:
- IV/RV alignment (implied vs realized coherence)
- Compression in balance (vol compresses during balance)
- Expansion with initiative (vol expands on breakouts)
- Regime consistency (regime doesn't flip rapidly)

Failure/Stress Indicators:
- IV/RV divergence
- Regime whipsaw
- Vol smile inversion
- Term structure inversion
"""

from typing import Dict, Any, Tuple, List, Optional
from datetime import datetime
import logging
import math

from .mel_calculator import MELCalculator
from .mel_models import MELConfig, Confidence


class VolatilityEffectivenessCalculator(MELCalculator):
    """
    Calculator for Volatility Regime effectiveness.

    Measures how well volatility models describe actual behavior.
    """

    @property
    def model_name(self) -> str:
        return "volatility"

    def _get_required_data_fields(self) -> List[str]:
        return [
            "iv_atm",
            "realized_vol",
            "vix",
            "vol_regime",
            "price_history",
        ]

    def calculate_effectiveness(self, market_data: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        """
        Calculate volatility effectiveness score.

        Composite of:
        - IV/RV alignment (30%)
        - Compression in balance (25%)
        - Expansion with initiative (25%)
        - Regime consistency (20%)
        """
        detail = {}

        # Extract data
        iv_atm = market_data.get("iv_atm")
        realized_vol = market_data.get("realized_vol")
        vix = market_data.get("vix")
        vol_regime = market_data.get("vol_regime")
        price_history = market_data.get("price_history", [])
        iv_history = market_data.get("iv_history", [])
        vah = market_data.get("vah")
        val = market_data.get("val")

        # If minimal data, return neutral
        if not price_history:
            return 65.0, {"note": "Insufficient data for volatility effectiveness"}

        # 1. IV/RV Alignment (30%)
        detail["iv_rv_ratio"] = self._calculate_iv_rv_ratio(iv_atm, realized_vol)
        detail["iv_rv_alignment"] = self._score_iv_rv_alignment(detail["iv_rv_ratio"])

        # 2. Compression in Balance (25%)
        detail["compression_in_balance"] = self._check_compression_in_balance(
            price_history, iv_history, vah, val
        )
        detail["compression_score"] = self._score_compression(detail["compression_in_balance"])

        # 3. Expansion with Initiative (25%)
        detail["expansion_with_initiative"] = self._check_expansion_with_initiative(
            price_history, iv_history, vah, val
        )
        detail["expansion_score"] = self._score_expansion(detail["expansion_with_initiative"])

        # 4. Regime Consistency (20%)
        detail["regime_consistency"] = self._analyze_regime_consistency(
            market_data.get("regime_history", []), vol_regime
        )
        detail["regime_score"] = self._score_regime_consistency(detail["regime_consistency"])

        # Stress indicators
        detail["stress_indicators"] = self._check_stress_indicators(
            market_data, detail
        )

        # Current vol regime
        detail["current_regime"] = vol_regime or self._infer_regime(iv_atm, vix)

        # Composite effectiveness score
        effectiveness = (
            detail["iv_rv_alignment"] * 0.30 +
            detail["compression_score"] * 0.25 +
            detail["expansion_score"] * 0.25 +
            detail["regime_score"] * 0.20
        )

        return self.normalize_score(effectiveness), detail

    def _calculate_iv_rv_ratio(
        self,
        iv: Optional[float],
        rv: Optional[float],
    ) -> Optional[float]:
        """Calculate IV/RV ratio."""
        if iv is None or rv is None or rv == 0:
            return None
        return iv / rv

    def _score_iv_rv_alignment(self, ratio: Optional[float]) -> float:
        """
        Score IV/RV alignment.

        Healthy range: 0.7-1.3
        """
        if ratio is None:
            return 65.0

        # Perfect alignment = 1.0
        # Score degrades as ratio moves away from 1.0
        if 0.7 <= ratio <= 1.3:
            # In healthy range - score based on closeness to 1.0
            deviation = abs(ratio - 1.0)
            return 90 - (deviation * 50)
        elif 0.5 <= ratio <= 1.5:
            # Somewhat misaligned
            return 50
        else:
            # Severely misaligned
            return 20

    def _check_compression_in_balance(
        self,
        price_history: List[Dict],
        iv_history: List[float],
        vah: Optional[float],
        val: Optional[float],
    ) -> str:
        """
        Check if volatility compresses during balance periods.

        Returns: 'Expected', 'Unexpected'
        """
        if not price_history or vah is None or val is None:
            return "Expected"

        # Find balance periods (price within value area)
        balance_periods = []
        in_balance = False
        balance_start = 0

        for i, bar in enumerate(price_history):
            price = bar.get("close") or bar.get("price")
            if price and val <= price <= vah:
                if not in_balance:
                    in_balance = True
                    balance_start = i
            else:
                if in_balance and i - balance_start >= 5:
                    balance_periods.append((balance_start, i))
                in_balance = False

        if not balance_periods or not iv_history or len(iv_history) < len(price_history):
            return "Expected"

        # Check if IV compressed during balance periods
        compressions = 0
        for start, end in balance_periods:
            if start < len(iv_history) and end <= len(iv_history):
                start_iv = iv_history[start]
                end_iv = iv_history[end - 1]
                if end_iv < start_iv * 0.95:  # IV dropped by 5%+
                    compressions += 1

        if len(balance_periods) == 0:
            return "Expected"

        compression_rate = compressions / len(balance_periods)
        return "Expected" if compression_rate >= 0.5 else "Unexpected"

    def _score_compression(self, compression: str) -> float:
        """Score compression behavior."""
        return self.score_categorical(compression, {
            "Expected": 85,
            "Unexpected": 40,
        })

    def _check_expansion_with_initiative(
        self,
        price_history: List[Dict],
        iv_history: List[float],
        vah: Optional[float],
        val: Optional[float],
    ) -> str:
        """
        Check if volatility expands during initiative (breakout) periods.

        Returns: 'Expected', 'Unexpected'
        """
        if not price_history or vah is None or val is None:
            return "Expected"

        # Find breakout periods
        breakouts = []

        for i, bar in enumerate(price_history):
            price = bar.get("close") or bar.get("price")
            if price and (price > vah or price < val):
                breakouts.append(i)

        if not breakouts or not iv_history or len(iv_history) < len(price_history):
            return "Expected"

        # Check if IV expanded during breakouts
        expansions = 0
        for idx in breakouts:
            if idx > 0 and idx < len(iv_history):
                prev_iv = iv_history[idx - 1]
                curr_iv = iv_history[idx]
                if curr_iv > prev_iv * 1.05:  # IV rose by 5%+
                    expansions += 1

        expansion_rate = expansions / len(breakouts) if breakouts else 0
        return "Expected" if expansion_rate >= 0.5 else "Unexpected"

    def _score_expansion(self, expansion: str) -> float:
        """Score expansion behavior."""
        return self.score_categorical(expansion, {
            "Expected": 85,
            "Unexpected": 40,
        })

    def _analyze_regime_consistency(
        self,
        regime_history: List[str],
        current_regime: Optional[str],
    ) -> str:
        """
        Analyze regime consistency.

        Returns: 'Stable', 'Transitioning', 'Chaotic'
        """
        if not regime_history:
            return "Stable"

        # Count regime changes
        changes = 0
        for i in range(1, len(regime_history)):
            if regime_history[i] != regime_history[i - 1]:
                changes += 1

        # Changes per period
        change_rate = changes / len(regime_history) if regime_history else 0

        if change_rate < 0.1:
            return "Stable"
        elif change_rate < 0.3:
            return "Transitioning"
        else:
            return "Chaotic"

    def _score_regime_consistency(self, consistency: str) -> float:
        """Score regime consistency."""
        return self.score_categorical(consistency, {
            "Stable": 90,
            "Transitioning": 60,
            "Chaotic": 25,
        })

    def _check_stress_indicators(
        self,
        market_data: Dict[str, Any],
        detail: Dict[str, Any],
    ) -> Dict[str, bool]:
        """Check for volatility stress indicators."""
        iv_rv_ratio = detail.get("iv_rv_ratio")
        skew = market_data.get("iv_skew")
        term_structure = market_data.get("term_structure")

        indicators = {
            "iv_rv_divergence": iv_rv_ratio is not None and (iv_rv_ratio < 0.5 or iv_rv_ratio > 2.0),
            "regime_whipsaw": detail.get("regime_consistency") == "Chaotic",
            "vol_smile_inversion": skew is not None and skew < -0.3,  # Unusual put skew
            "term_structure_inversion": term_structure == "inverted",
        }
        return indicators

    def _infer_regime(
        self,
        iv: Optional[float],
        vix: Optional[float],
    ) -> str:
        """Infer vol regime from available data."""
        # Use VIX levels as proxy
        if vix is None and iv is None:
            return "unknown"

        level = vix or iv

        if level < 15:
            return "low"
        elif level < 20:
            return "normal"
        elif level < 30:
            return "elevated"
        else:
            return "high"

    def _determine_confidence(
        self,
        detail: Dict[str, Any],
        market_data: Dict[str, Any],
    ) -> Confidence:
        """Determine confidence in volatility effectiveness."""
        iv = market_data.get("iv_atm")
        rv = market_data.get("realized_vol")
        iv_history = market_data.get("iv_history", [])

        if iv is None and rv is None:
            return Confidence.LOW

        if not iv_history or len(iv_history) < 10:
            return Confidence.MEDIUM

        return Confidence.HIGH
