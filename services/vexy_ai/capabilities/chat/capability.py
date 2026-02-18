"""
Chat Capability - Conversational interface to Vexy.

Provides direct conversational access to Vexy with:
- Tier-based access control
- Rate limiting
- Playbook awareness
- Echo Memory integration
- Real-time web search
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from ...core.capability import BaseCapability
from .service import ChatService
from .models import VexyChatRequest, VexyChatResponse


class ChatCapability(BaseCapability):
    """
    Vexy Chat capability.

    Provides endpoints for:
    - POST /api/vexy/chat - Main chat endpoint
    """

    name = "chat"
    version = "1.0.0"
    dependencies = []
    buses_required = ["system"]  # For rate limiting via Redis

    def __init__(self, vexy):
        super().__init__(vexy)
        self.service: Optional[ChatService] = None

    async def start(self) -> None:
        """Initialize Chat service."""
        buses = self.vexy.buses if hasattr(self.vexy, 'buses') else None
        market_intel = getattr(self.vexy, 'market_intel', None)
        kernel = getattr(self.vexy, 'kernel', None)
        self.service = ChatService(self.config, self.logger, buses, market_intel=market_intel, kernel=kernel)

        # Initialize playbook system
        try:
            from services.vexy_ai.playbook_loader import (
                ensure_playbook_directory,
                load_all_playbooks,
            )
            ensure_playbook_directory()
            playbooks = load_all_playbooks()
            self.logger.info(f"Loaded {len(playbooks)} playbooks", emoji="📖")
        except Exception as e:
            self.logger.warn(f"Playbook loader init failed: {e}", emoji="⚠️")

        self.logger.info("Chat capability started", emoji="🦋")

    async def stop(self) -> None:
        """Clean up Chat service."""
        self.service = None
        self.logger.info("Chat capability stopped", emoji="🦋")

    def get_routes(self) -> APIRouter:
        """Return FastAPI router with Chat endpoints."""
        router = APIRouter(tags=["Chat"])

        @router.post("/api/vexy/chat", response_model=VexyChatResponse)
        async def vexy_chat(request: VexyChatRequest, req: Request):
            """
            Handle Vexy chat messages.

            Provides direct conversational access to Vexy, the AI engine
            running on The Path OS. Access is tiered by subscription level.
            """
            # User identity from TrustBoundaryMiddleware (set by gateway headers)
            user_id = req.state.user_id
            user_tier = req.state.user_tier or request.user_tier or "observer"

            # Check rate limit
            allowed, remaining = self.service.check_rate_limit(user_id, user_tier)
            if not allowed:
                from services.vexy_ai.tier_config import get_tier_config, get_gate_value
                tier_config = get_tier_config(user_tier)
                effective_limit = get_gate_value(user_tier, "vexy_chat_rate")
                if effective_limit is None:
                    effective_limit = tier_config.rate_limit
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit reached ({effective_limit} per hour). Your limit resets in under an hour."
                )

            # Process chat
            result = await self.service.chat(
                message=request.message,
                user_id=user_id,
                user_tier=user_tier,
                reflection_dial=request.reflection_dial,
                context=request.context,
                user_profile=request.user_profile,
            )

            return VexyChatResponse(**result)

        return router
