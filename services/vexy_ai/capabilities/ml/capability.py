"""
ML Capability - Machine Learning pattern confirmation.

Handles all ML threshold checking, pattern eligibility,
and confirmation generation with strict doctrine:
- ML is confirmatory only
- Silence is first-class
- Never active during live trading
"""

from typing import Optional

from fastapi import APIRouter

from ...core.capability import BaseCapability
from .service import MLService
from .models import MLStatusRequest, PatternEligibilityRequest, PatternConfirmationRequest


class MLCapability(BaseCapability):
    """
    ML pattern confirmation capability.

    Provides endpoints for:
    - ML status checking (baseline requirements)
    - Threshold retrieval
    - Pattern eligibility checking
    - ML confirmation generation
    - Context and language rules
    """

    name = "ml"
    version = "1.0.0"
    dependencies = []  # No dependencies on other capabilities
    buses_required = []  # ML doesn't need direct bus access

    def __init__(self, vexy):
        super().__init__(vexy)
        self.service: Optional[MLService] = None

    async def start(self) -> None:
        """Initialize ML service."""
        self.service = MLService(self.config, self.logger)
        self.logger.info("ML capability started", emoji="🧠")

    async def stop(self) -> None:
        """Clean up ML service."""
        self.service = None
        self.logger.info("ML capability stopped", emoji="🧠")

    def get_routes(self) -> APIRouter:
        """Return FastAPI router with ML endpoints."""
        router = APIRouter(prefix="/api/vexy/ml", tags=["ML Thresholds"])

        @router.get("/thresholds")
        async def get_thresholds():
            """Get ML confirmation thresholds."""
            return self.service.get_thresholds()

        @router.post("/status")
        async def get_status(request: MLStatusRequest):
            """Get ML confirmation status for a user."""
            return self.service.get_status(
                request.retrospective_count,
                request.closed_trade_count,
                request.distinct_period_count,
            )

        @router.post("/pattern-eligible")
        async def check_pattern_eligibility(request: PatternEligibilityRequest):
            """Check if a pattern is eligible for ML confirmation."""
            return self.service.check_pattern_eligibility(
                request.pattern_type,
                request.sources,
                request.artifact_count,
                request.is_template_induced,
            )

        @router.post("/confirm")
        async def get_confirmation(request: PatternConfirmationRequest):
            """Get ML confirmation for a pattern if thresholds are met."""
            return self.service.get_confirmation(
                pattern_id=request.pattern_id,
                user_id=request.user_id,
                occurrences=request.occurrences,
                retrospective_count=request.retrospective_count,
                days_span=request.days_span,
                similarity_score=request.similarity_score,
                contradiction_ratio=request.contradiction_ratio,
                market_regimes=request.market_regimes,
                stability_score=request.stability_score,
                description_variance=request.description_variance,
                user_has_playbooks=request.user_has_playbooks,
                context=request.context,
            )

        @router.get("/allowed-contexts")
        async def get_allowed_contexts():
            """Get contexts where ML confirmation is allowed vs forbidden."""
            return self.service.get_allowed_contexts()

        @router.get("/language-rules")
        async def get_language_rules():
            """Get language constraints for ML confirmations."""
            return self.service.get_language_rules()

        return router
