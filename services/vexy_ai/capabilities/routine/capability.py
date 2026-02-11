"""
Routine Capability - Routine Mode orientation and presence.

Handles all Routine-related functionality including:
- Mode A orientation (context-aware, silence-valid)
- Routine briefings (The Path-aligned narratives)
- Market readiness (read-only awareness)
- Log health context integration

Philosophy: Help the trader arrive, not complete tasks.
Train how to begin, not what to do.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException

from ...core.capability import BaseCapability
from .service import RoutineService
from .models import (
    RoutineBriefingRequest,
    RoutineBriefingResponse,
    RoutineOrientationRequest,
    RoutineOrientationResponse,
    MarketReadinessResponse,
    MarketStateResponse,
    LogHealthContextRequest,
    LogHealthContextResponse,
)


class RoutineCapability(BaseCapability):
    """
    Routine Mode capability.

    Provides endpoints for:
    - GET /api/vexy/routine/context-phase - Current routine context phase
    - POST /api/vexy/routine/orientation - Mode A orientation message
    - GET /api/vexy/routine/market-readiness/{user_id} - Market readiness artifact (legacy)
    - GET /api/vexy/market-state - State of the Market v2
    - POST /api/vexy/routine-briefing - Full routine briefing
    - POST /api/vexy/context/log-health - Ingest log health context
    - GET /api/vexy/context/log-health/{user_id} - Get log health context
    """

    name = "routine"
    version = "1.0.0"
    dependencies = []  # No dependencies on other capabilities
    buses_required = []  # Routine doesn't need direct bus access

    def __init__(self, vexy):
        super().__init__(vexy)
        self.service: Optional[RoutineService] = None

    async def start(self) -> None:
        """Initialize Routine service."""
        self.service = RoutineService(self.config, self.logger)
        self.logger.info("Routine capability started", emoji="🌅")

    async def stop(self) -> None:
        """Clean up Routine service."""
        self.service = None
        self.logger.info("Routine capability stopped", emoji="🌅")

    def get_routes(self) -> APIRouter:
        """Return FastAPI router with Routine endpoints."""
        router = APIRouter(tags=["Routine"])

        @router.get("/api/vexy/routine/context-phase")
        async def get_context_phase():
            """Get current routine context phase."""
            return self.service.get_context_phase()

        @router.post("/api/vexy/routine/orientation", response_model=RoutineOrientationResponse)
        async def get_orientation(request: RoutineOrientationRequest):
            """
            Get Mode A orientation message for Routine panel.

            May return null orientation (silence is valid).
            Adapts to RoutineContextPhase (weekday/weekend/holiday, time of day).
            """
            result = self.service.get_orientation(
                vix_level=request.vix_level,
                vix_regime=request.vix_regime,
            )
            return RoutineOrientationResponse(**result)

        @router.get("/api/vexy/routine/market-readiness/{user_id}", response_model=MarketReadinessResponse)
        async def get_market_readiness(user_id: int):
            """
            Get cached market readiness artifact.

            Generated once or infrequently, not real-time.
            Returns read-only awareness data, not predictions.
            Enforces lexicon constraints (no POC/VAH/VAL).
            """
            result = self.service.get_market_readiness(user_id)
            return MarketReadinessResponse(**result)

        @router.get("/api/vexy/market-state", response_model=MarketStateResponse)
        async def get_market_state():
            """
            State of the Market v2 — deterministic 4-lens synthesis.

            No query params, no user_id. Redis reads + deterministic logic only.
            Returns: schema_version, context_phase, 4 lenses (null on weekends/holidays).
            """
            result = self.service.get_market_state()
            return MarketStateResponse(**result)

        @router.post("/api/vexy/routine-briefing", response_model=RoutineBriefingResponse)
        async def routine_briefing(request: RoutineBriefingRequest):
            """
            Generate a Routine Mode orientation briefing.

            Called explicitly by the UI when the Routine drawer opens.
            Vexy does not "watch" the UI - the UI asks for a briefing.
            """
            result = self.service.generate_briefing(
                mode=request.mode,
                timestamp=request.timestamp,
                market_context=request.market_context.model_dump() if request.market_context else None,
                user_context=request.user_context.model_dump() if request.user_context else None,
                open_loops=request.open_loops.model_dump() if request.open_loops else None,
                user_id=request.user_id,
            )

            if result is None:
                raise HTTPException(status_code=500, detail="Failed to generate briefing")

            return RoutineBriefingResponse(**result)

        @router.post("/api/vexy/context/log-health", response_model=LogHealthContextResponse)
        async def ingest_log_health_context(request: LogHealthContextRequest):
            """
            Ingest log health context for Routine Mode narratives.

            Called by the log_health_analyzer scheduled job at 05:00 ET daily.
            Context is stored per (user_id, routine_date) and is idempotent.
            """
            signals = [s.model_dump() for s in request.signals]
            result = self.service.ingest_log_health_context(
                user_id=request.user_id,
                routine_date=request.routine_date,
                signals=signals,
            )
            return LogHealthContextResponse(**result)

        @router.get("/api/vexy/context/log-health/{user_id}")
        async def get_log_health_context(user_id: int):
            """Get log health context for a user."""
            return self.service.get_log_health_context(user_id)

        return router
