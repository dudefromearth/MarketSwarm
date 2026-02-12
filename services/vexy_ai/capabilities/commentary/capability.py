"""
Commentary Capability - Vexy Play-by-Play commentary engine.

Handles:
- Epoch-based scheduled commentary (market segments)
- Event-driven market commentary (gamma squeezes, volume spikes)
- Intel article processing
- Publishing to market-redis for real-time subscribers

This capability runs a background task that continuously monitors
and publishes commentary based on market conditions and schedules.
"""

from typing import Callable, List, Optional

from fastapi import APIRouter

from ...core.capability import BaseCapability
from .service import CommentaryService
from .models import CommentaryStatusResponse, TodayMessagesResponse


class CommentaryCapability(BaseCapability):
    """
    Vexy Play-by-Play commentary capability.

    Provides:
    - Background task for epoch/event monitoring
    - GET /api/vexy/commentary/status - Current status
    - GET /api/vexy/commentary/messages - Today's messages
    """

    name = "commentary"
    version = "1.0.0"
    dependencies = []
    buses_required = ["system", "market", "intel"]

    def __init__(self, vexy):
        super().__init__(vexy)
        self.service: Optional[CommentaryService] = None

    async def start(self) -> None:
        """Initialize Commentary service."""
        buses = self.vexy.buses if hasattr(self.vexy, 'buses') else None
        market_intel = getattr(self.vexy, 'market_intel', None)
        kernel = getattr(self.vexy, 'kernel', None)
        self.service = CommentaryService(self.config, self.logger, buses, market_intel=market_intel, kernel=kernel)
        self.logger.info("Commentary capability started", emoji="🎙️")

    async def stop(self) -> None:
        """Stop Commentary service."""
        if self.service:
            self.service.stop()
        self.service = None
        self.logger.info("Commentary capability stopped", emoji="🎙️")

    def get_routes(self) -> APIRouter:
        """Return FastAPI router with Commentary endpoints."""
        router = APIRouter(prefix="/api/vexy/commentary", tags=["Commentary"])

        @router.get("/status", response_model=CommentaryStatusResponse)
        async def get_status():
            """Get current commentary status."""
            status = self.service.get_status()
            return CommentaryStatusResponse(
                running=status["running"],
                last_epoch=status.get("last_epoch"),
                schedule_type=status.get("schedule_type", "unknown"),
                epochs_enabled=True,  # TODO: Get from service
                events_enabled=True,
                intel_enabled=True,
                next_epoch=None,  # TODO: Calculate next epoch
            )

        @router.get("/messages", response_model=TodayMessagesResponse)
        async def get_today_messages():
            """Get all commentary messages published today."""
            messages = self.service.get_today_messages()
            return TodayMessagesResponse(
                messages=messages,
                count=len(messages),
            )

        return router

    def get_background_tasks(self) -> List[Callable]:
        """Return background tasks to run."""
        return [self._run_commentary_loop]

    async def _run_commentary_loop(self) -> None:
        """Background task wrapper for the commentary loop."""
        if self.service:
            await self.service.run_loop()
