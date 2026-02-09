"""
ML Service - Business logic for ML pattern confirmation.

Wraps the ml_thresholds module and provides a clean interface
for the capability to use.

Doctrine:
- ML is confirmatory only, never prescriptive
- Silence is always valid
- Never shows during live trading or market stress
- Human always outranks model
"""

from typing import Any, Dict, List, Optional, Tuple


class MLService:
    """
    ML threshold and confirmation service.

    Handles all ML-related business logic including:
    - Baseline requirement checking
    - Threshold management
    - Pattern eligibility
    - Confirmation generation
    """

    def __init__(self, config: Dict[str, Any], logger: Any):
        self.config = config
        self.logger = logger

    def get_thresholds(self) -> Dict[str, Any]:
        """Get ML confirmation thresholds."""
        from services.vexy_ai.ml_thresholds import get_threshold_summary

        return {
            "status": "provisional",
            "thresholds": get_threshold_summary(),
            "doctrine": {
                "ml_is_confirmatory": True,
                "ml_never_names_patterns": True,
                "ml_never_recommends_actions": True,
                "ml_never_escalates_urgency": True,
                "silence_is_always_valid": True,
                "human_outranks_model": True,
            },
        }

    def get_status(
        self,
        retrospective_count: int,
        closed_trade_count: int,
        distinct_period_count: int,
    ) -> Dict[str, Any]:
        """Get ML confirmation status for a user."""
        from services.vexy_ai.ml_thresholds import get_ml_status_for_user

        return get_ml_status_for_user(
            retrospective_count,
            closed_trade_count,
            distinct_period_count,
        )

    def check_pattern_eligibility(
        self,
        pattern_type: str,
        sources: List[str],
        artifact_count: int,
        is_template_induced: bool = False,
    ) -> Dict[str, Any]:
        """Check if a pattern is eligible for ML confirmation."""
        from services.vexy_ai.ml_thresholds import is_pattern_eligible

        eligible, reason = is_pattern_eligible(
            pattern_type,
            sources,
            artifact_count,
            is_template_induced,
        )

        return {
            "eligible": eligible,
            "reason": reason,
        }

    def get_confirmation(
        self,
        pattern_id: str,
        user_id: int,
        occurrences: int,
        retrospective_count: int,
        days_span: int,
        similarity_score: float,
        contradiction_ratio: float = 0.0,
        market_regimes: int = 1,
        stability_score: float = 0.5,
        description_variance: float = 0.5,
        user_has_playbooks: bool = False,
        context: str = "retrospective",
    ) -> Dict[str, Any]:
        """Get ML confirmation for a pattern if thresholds are met."""
        from services.vexy_ai.ml_thresholds import (
            PatternMetrics,
            create_ml_confirmation,
        )

        # Check baseline requirements
        baseline_met = retrospective_count >= 5

        metrics = PatternMetrics(
            occurrences=occurrences,
            retrospective_count=retrospective_count,
            days_span=days_span,
            similarity_score=similarity_score,
            contradiction_ratio=contradiction_ratio,
            market_regimes=market_regimes,
            stability_score=stability_score,
            description_variance=description_variance,
            user_has_playbooks=user_has_playbooks,
        )

        confirmation = create_ml_confirmation(
            pattern_id=pattern_id,
            user_id=user_id,
            metrics=metrics,
            context=context,
            baseline_met=baseline_met,
            overrides=[],  # In production, load from storage
        )

        if confirmation is None:
            return {
                "output": None,
                "reason": "ML chose silence (insufficient confidence or context not allowed)",
                "confidence_level": None,
            }

        return {
            "output": confirmation.output_text,
            "confidence_level": confirmation.confidence_level.name,
            "confidence_value": confirmation.confidence_level.value,
        }

    def get_allowed_contexts(self) -> Dict[str, Any]:
        """Get contexts where ML confirmation is allowed vs forbidden."""
        from services.vexy_ai.ml_thresholds import (
            ALLOWED_ML_CONTEXTS,
            FORBIDDEN_ML_CONTEXTS,
        )

        return {
            "allowed": list(ALLOWED_ML_CONTEXTS),
            "forbidden": list(FORBIDDEN_ML_CONTEXTS),
            "rule": "ML confirmation is NEVER shown during live trading, execution, or market stress",
        }

    def get_language_rules(self) -> Dict[str, Any]:
        """Get language constraints for ML confirmations."""
        from services.vexy_ai.ml_thresholds import (
            ML_ALLOWED_PHRASES,
            ML_FORBIDDEN_PHRASES,
        )

        return {
            "allowed_phrases": ML_ALLOWED_PHRASES,
            "forbidden_phrases": ML_FORBIDDEN_PHRASES,
            "rule": "If ML 'wants' to explain, it must remain silent",
        }
