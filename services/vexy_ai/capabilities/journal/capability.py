"""
Journal Capability - Journal Mode for noticing and reflection.

Core Doctrine:
- The Journal is not a place to perform work. It is a place to notice what occurred.
- Vexy is silent by default. Presence is assumed. Speech is earned.
- Silence is not a failure state. Silence is correct.
"""

from typing import Optional

from fastapi import APIRouter

from ...core.capability import BaseCapability
from .service import JournalService
from .models import (
    JournalSynopsisRequest,
    JournalSynopsisResponse,
    JournalPromptsResponse,
    JournalChatRequest,
    JournalChatResponse,
)


class JournalCapability(BaseCapability):
    """
    Journal Mode capability.

    Provides endpoints for:
    - POST /api/vexy/journal/synopsis - Generate Daily Synopsis
    - POST /api/vexy/journal/prompts - Generate reflective prompts
    - POST /api/vexy/journal/chat - Chat in Journal context
    """

    name = "journal"
    version = "1.0.0"
    dependencies = []
    buses_required = []

    def __init__(self, vexy):
        super().__init__(vexy)
        self.service: Optional[JournalService] = None

    async def start(self) -> None:
        """Initialize Journal service."""
        self.service = JournalService(self.config, self.logger)
        self.logger.info("Journal capability started", emoji="📓")

    async def stop(self) -> None:
        """Clean up Journal service."""
        self.service = None
        self.logger.info("Journal capability stopped", emoji="📓")

    def get_routes(self) -> APIRouter:
        """Return FastAPI router with Journal endpoints."""
        router = APIRouter(prefix="/api/vexy/journal", tags=["Journal"])

        @router.post("/synopsis", response_model=JournalSynopsisResponse)
        async def journal_synopsis(request: JournalSynopsisRequest):
            """
            Generate the Daily Synopsis for the Journal.

            The Synopsis is a weather report, not a scorecard.
            """
            result = self.service.generate_synopsis(
                trade_date=request.trade_date,
                trades=request.trades,
                market_context=request.market_context,
            )
            return JournalSynopsisResponse(**result)

        @router.post("/prompts", response_model=JournalPromptsResponse)
        async def journal_prompts(request: JournalSynopsisRequest):
            """
            Generate prepared reflective prompts for the Journal.

            Rules:
            - Maximum 2 prompts per day, often 0
            - Only if sufficient data exists
            - Silence is preferable to filler
            """
            result = self.service.generate_prompts(
                trade_date=request.trade_date,
                trades=request.trades,
                market_context=request.market_context,
            )
            return JournalPromptsResponse(**result)

        @router.post("/chat", response_model=JournalChatResponse)
        async def journal_chat(request: JournalChatRequest):
            """
            Handle Vexy chat in Journal context.

            Supports two modes:
            - Mode A: On-Demand Conversation (user asks directly)
            - Mode B: Responding to Prepared Prompts (user clicks a prompt)
            """
            result = await self.service.chat(
                message=request.message,
                trade_date=request.trade_date,
                trades=request.trades,
                market_context=request.market_context,
                is_prepared_prompt=request.is_prepared_prompt,
            )
            return JournalChatResponse(**result)

        return router
