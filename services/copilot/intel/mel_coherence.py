"""
Cross-Model Coherence Calculator - MEL Model for Inter-Model Agreement.

Determines if models agree or contradict each other.

States:
- STABLE: Models generally agree, signals reinforce
- MIXED: Some disagreement, selective trust needed
- COLLAPSING: Models contradict, no clear signal
- RECOVERED: Previously collapsing, now stabilizing

Indicators:
- Gamma says pin, VP says breakout -> Contradiction
- Gamma, VP, Liquidity all agree -> Coherence
- One model working while others fail -> Asymmetric structure
"""

from typing import Dict, Any, Tuple, List, Optional
from datetime import datetime
import logging

from .mel_models import (
    MELModelScore,
    ModelState,
    CoherenceState,
    MELConfig,
)


class CoherenceCalculator:
    """
    Calculator for cross-model coherence.

    Unlike other MEL calculators, this doesn't inherit from MELCalculator
    because it operates on model scores rather than market data.
    """

    def __init__(
        self,
        config: Optional[MELConfig] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.config = config or MELConfig()
        self.logger = logger or logging.getLogger("MELCoherence")
        self._previous_state: Optional[CoherenceState] = None

    def calculate_coherence(
        self,
        gamma: MELModelScore,
        volume_profile: MELModelScore,
        liquidity: MELModelScore,
        volatility: MELModelScore,
        session: MELModelScore,
        market_data: Optional[Dict[str, Any]] = None,
    ) -> Tuple[float, CoherenceState, Dict[str, Any]]:
        """
        Calculate cross-model coherence.

        Returns:
            Tuple of (coherence_score, coherence_state, detail)
        """
        detail = {}

        # Get all scores
        scores = [
            gamma.effectiveness,
            volume_profile.effectiveness,
            liquidity.effectiveness,
            volatility.effectiveness,
            session.effectiveness,
        ]

        states = [
            gamma.state,
            volume_profile.state,
            liquidity.state,
            volatility.state,
            session.state,
        ]

        # 1. Calculate score variance (agreement on effectiveness level)
        score_coherence = self._calculate_score_coherence(scores)
        detail["score_variance"] = self._calculate_variance(scores)
        detail["score_coherence"] = score_coherence

        # 2. Calculate state agreement
        state_coherence = self._calculate_state_coherence(states)
        detail["states"] = {
            "valid_count": sum(1 for s in states if s == ModelState.VALID),
            "degraded_count": sum(1 for s in states if s == ModelState.DEGRADED),
            "revoked_count": sum(1 for s in states if s == ModelState.REVOKED),
        }
        detail["state_coherence"] = state_coherence

        # 3. Check for specific contradictions
        contradictions = self._check_contradictions(
            gamma, volume_profile, liquidity, volatility, session, market_data
        )
        detail["contradictions"] = contradictions
        detail["contradiction_count"] = sum(1 for v in contradictions.values() if v)

        # 4. Check for asymmetric structure (one model valid, others failed)
        asymmetry = self._check_asymmetry(states, scores)
        detail["asymmetric_structure"] = asymmetry

        # Composite coherence score
        coherence = self._calculate_composite_coherence(
            score_coherence, state_coherence, contradictions, asymmetry
        )
        detail["composite_coherence"] = coherence

        # Determine state
        state = self._determine_coherence_state(
            states, coherence, detail["contradiction_count"]
        )

        # Update previous state
        self._previous_state = state

        return coherence, state, detail

    def _calculate_score_coherence(self, scores: List[float]) -> float:
        """
        Calculate coherence based on score variance.

        Lower variance = higher coherence.
        """
        if not scores:
            return 50.0

        variance = self._calculate_variance(scores)

        # Max expected variance ~625 (scores 0-100, max spread)
        # Transform to coherence score (0-100)
        max_variance = 625
        coherence = max(0, 100 - (variance / max_variance * 100))

        return coherence

    def _calculate_variance(self, values: List[float]) -> float:
        """Calculate variance of values."""
        if not values:
            return 0

        avg = sum(values) / len(values)
        variance = sum((v - avg) ** 2 for v in values) / len(values)
        return variance

    def _calculate_state_coherence(self, states: List[ModelState]) -> float:
        """
        Calculate coherence based on state agreement.

        All same state = 100, all different = lower.
        """
        if not states:
            return 50.0

        valid_count = sum(1 for s in states if s == ModelState.VALID)
        degraded_count = sum(1 for s in states if s == ModelState.DEGRADED)
        revoked_count = sum(1 for s in states if s == ModelState.REVOKED)

        total = len(states)

        # Score based on majority agreement
        max_agreement = max(valid_count, degraded_count, revoked_count)
        agreement_pct = max_agreement / total * 100

        # Penalize for revoked models
        revoked_penalty = revoked_count * 10

        return max(0, agreement_pct - revoked_penalty)

    def _check_contradictions(
        self,
        gamma: MELModelScore,
        volume_profile: MELModelScore,
        liquidity: MELModelScore,
        volatility: MELModelScore,
        session: MELModelScore,
        market_data: Optional[Dict[str, Any]],
    ) -> Dict[str, bool]:
        """
        Check for specific model contradictions.

        These are cases where models give opposite signals.
        """
        contradictions = {
            "gamma_vp_conflict": False,
            "liquidity_volatility_conflict": False,
            "session_structure_conflict": False,
        }

        # Gamma vs Volume Profile conflict
        # If gamma says pin but VP says breakout
        gamma_detail = gamma.detail
        vp_detail = volume_profile.detail

        if gamma_detail and vp_detail:
            gamma_pin = gamma_detail.get("pin_duration") == "Strong"
            vp_breakout = vp_detail.get("initiative_follow_through") == "Strong"

            if gamma_pin and vp_breakout:
                contradictions["gamma_vp_conflict"] = True

            # Or if gamma says strong control but VP shows no rotation
            gamma_strong = gamma.effectiveness > 75
            vp_no_rotation = vp_detail.get("rotation_completion") == "Inconsistent"

            if gamma_strong and vp_no_rotation:
                contradictions["gamma_vp_conflict"] = True

        # Liquidity vs Volatility conflict
        # High liquidity effectiveness but high volatility stress
        liq_detail = liquidity.detail
        vol_detail = volatility.detail

        if liq_detail and vol_detail:
            liq_good = liquidity.effectiveness > 70
            vol_stressed = vol_detail.get("regime_consistency") == "Chaotic"

            if liq_good and vol_stressed:
                contradictions["liquidity_volatility_conflict"] = True

        # Session structure conflict
        # Session says balance but other models show chaos
        session_detail = session.detail
        if session_detail:
            session_balance = session_detail.get("midday_balance") == "Stable"

            if session_balance and (gamma.state == ModelState.REVOKED or
                                     volume_profile.state == ModelState.REVOKED):
                contradictions["session_structure_conflict"] = True

        return contradictions

    def _check_asymmetry(
        self,
        states: List[ModelState],
        scores: List[float],
    ) -> str:
        """
        Check for asymmetric structure.

        Returns: 'None', 'Mild', 'Severe'
        """
        valid_count = sum(1 for s in states if s == ModelState.VALID)
        revoked_count = sum(1 for s in states if s == ModelState.REVOKED)

        # Check score spread
        score_spread = max(scores) - min(scores) if scores else 0

        if valid_count >= 4 and revoked_count == 0:
            return "None"  # All models agree
        elif valid_count >= 1 and revoked_count >= 3:
            return "Severe"  # One working, others failed
        elif score_spread > 40:
            return "Mild"  # Significant spread
        else:
            return "None"

    def _calculate_composite_coherence(
        self,
        score_coherence: float,
        state_coherence: float,
        contradictions: Dict[str, bool],
        asymmetry: str,
    ) -> float:
        """Calculate composite coherence score."""
        # Base coherence from score and state agreement
        base = (score_coherence * 0.4 + state_coherence * 0.4)

        # Penalty for contradictions
        contradiction_penalty = sum(1 for v in contradictions.values() if v) * 15

        # Penalty for asymmetry
        asymmetry_penalty = {
            "None": 0,
            "Mild": 10,
            "Severe": 25,
        }.get(asymmetry, 0)

        return max(0, base - contradiction_penalty - asymmetry_penalty)

    def _determine_coherence_state(
        self,
        states: List[ModelState],
        coherence: float,
        contradiction_count: int,
    ) -> CoherenceState:
        """
        Determine coherence state from metrics.

        STABLE: coherence >= 70, no contradictions, <= 1 revoked
        MIXED: coherence 40-70, or some contradictions
        COLLAPSING: coherence < 40, or >= 3 revoked, or >= 2 contradictions
        RECOVERED: was COLLAPSING, now improving
        """
        revoked_count = sum(1 for s in states if s == ModelState.REVOKED)

        # Check for recovery
        if self._previous_state == CoherenceState.COLLAPSING:
            if coherence >= 50 and revoked_count < 3 and contradiction_count < 2:
                return CoherenceState.RECOVERED

        # COLLAPSING conditions
        if coherence < 40 or revoked_count >= 3 or contradiction_count >= 2:
            return CoherenceState.COLLAPSING

        # STABLE conditions
        if coherence >= 70 and contradiction_count == 0 and revoked_count <= 1:
            return CoherenceState.STABLE

        # Otherwise MIXED
        return CoherenceState.MIXED


def get_coherence_multiplier(state: CoherenceState, config: Optional[MELConfig] = None) -> float:
    """Get the coherence multiplier for global integrity calculation."""
    if config:
        return config.coherence_multipliers.get(state.value, 1.0)

    # Defaults
    multipliers = {
        CoherenceState.STABLE: 1.0,
        CoherenceState.MIXED: 0.85,
        CoherenceState.COLLAPSING: 0.60,
        CoherenceState.RECOVERED: 0.90,
    }
    return multipliers.get(state, 1.0)
