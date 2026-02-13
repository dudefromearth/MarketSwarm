"""
Interaction Service — Orchestrates Dialog Layer + Cognition Layer.

Handles the full interaction lifecycle:
1. Dedup check (existing active job)
2. Tier resolution with trial check
3. Rate limit check
4. Dialog Layer classification (fast ACK)
5. If PROCEED: create job, start async cognition task
6. Return DialogResponse immediately (<250ms)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ...interaction.models import InteractionRequest, DialogResponse
from ...interaction.dialog_layer import DialogLayer
from ...interaction.cognition_layer import CognitionLayer
from ...interaction.job_manager import JobManager
from ...interaction.elevation import ElevationEngine
from ...interaction.settings import InteractionSettings
from ...tier_config import (
    get_tier_config,
    tier_from_roles_with_trial_check,
    validate_reflection_dial,
)


class InteractionService:
    """
    Orchestrates the two-layer interaction system.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        logger: Any,
        kernel: Any,
        buses: Any,
        market_intel: Any = None,
    ):
        self.config = config
        self.logger = logger
        self.kernel = kernel
        self.buses = buses

        self.dialog_layer = DialogLayer()
        self.cognition_layer = CognitionLayer(kernel, logger)
        self.job_manager = JobManager(buses, logger)
        self.elevation = ElevationEngine(buses, logger)
        self.settings = InteractionSettings(buses, logger)

    async def initialize(self) -> None:
        """Load settings from Redis."""
        await self.settings.load()

    async def handle_interaction(
        self,
        request: InteractionRequest,
        user_id: int,
        roles: Optional[list] = None,
        created_at: Optional[str] = None,
    ) -> DialogResponse:
        """
        Handle an interaction request through the two-layer system.

        Returns DialogResponse in <250ms. Cognition runs async if PROCEED.
        """
        # Resolve tier with trial check
        resolved_tier = request.user_tier or tier_from_roles_with_trial_check(
            roles, created_at
        )

        # Clamp reflection dial to tier limits
        request.reflection_dial = validate_reflection_dial(
            resolved_tier, request.reflection_dial
        )

        # Check rate limits
        tier_config = get_tier_config(resolved_tier)
        remaining = await self._check_rate_limit(user_id, tier_config)

        # Check for existing active job (dedup)
        active_job_id = self.job_manager.get_active_job(user_id, request.surface)

        # Get admin settings
        settings_dict = self.settings.get_all()

        # Dialog Layer: fast classification
        dialog_response = self.dialog_layer.classify(
            request=request,
            user_id=user_id,
            resolved_tier=resolved_tier,
            remaining_today=remaining,
            active_job_id=active_job_id,
            settings=settings_dict,
        )

        # If PROCEED and no existing job, create job and start cognition
        if dialog_response.status == "proceed" and not active_job_id:
            # Concurrency check
            if not self.job_manager.enforce_concurrency(user_id, resolved_tier):
                dialog_response.status = "refuse"
                dialog_response.message = "A reflection is already in progress."
                dialog_response.next = None
                return dialog_response

            # Create job
            job_id = await self.job_manager.create_job(
                interaction_id=dialog_response.interaction_id,
                user_id=user_id,
                surface=request.surface,
                tier=resolved_tier,
            )

            # Update dialog response with job_id
            if dialog_response.next:
                dialog_response.next.job_id = job_id

            # Get elevation hint (async, non-blocking)
            elevation_hint = None
            if resolved_tier in ("observer", "observer_restricted", "activator"):
                elevation_hint = await self.elevation.get_hint(user_id, resolved_tier)

            # Decrement rate limit
            await self._decrement_rate_limit(user_id, tier_config)
            new_remaining = remaining - 1 if remaining > 0 else remaining
            dialog_response.remaining_today = new_remaining

            # Start async cognition (fire-and-forget)
            coro = self.cognition_layer.execute(
                job_id=job_id,
                user_id=user_id,
                interaction_id=dialog_response.interaction_id,
                request=request,
                tier=resolved_tier,
                job_manager=self.job_manager,
                elevation_hint=elevation_hint,
                remaining_today=new_remaining,
            )
            await self.job_manager.start_job(job_id, coro)

        return dialog_response

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job."""
        return await self.job_manager.cancel_job(job_id)

    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job status (polling fallback)."""
        return await self.job_manager.get_job_status(job_id)

    async def list_active_jobs(self) -> list:
        """List all active jobs (admin)."""
        return await self.job_manager.list_active_jobs()

    async def cleanup_stale_jobs(self) -> int:
        """Periodic stale job cleanup."""
        return await self.job_manager.cleanup_stale_jobs()

    async def _check_rate_limit(self, user_id: int, tier_config: Any) -> int:
        """
        Check hourly rate limit for user. Returns remaining (-1 = unlimited).
        """
        if tier_config.rate_limit < 0:
            return -1

        rate_key = f"vexy:interaction:rate:{user_id}"
        count_str = await self.buses.market.get(rate_key)

        if count_str is None:
            return tier_config.rate_limit

        count = int(count_str)
        return max(0, tier_config.rate_limit - count)

    async def _decrement_rate_limit(self, user_id: int, tier_config: Any) -> None:
        """Increment usage counter for this hour."""
        if tier_config.rate_limit < 0:
            return

        rate_key = f"vexy:interaction:rate:{user_id}"
        pipe = self.buses.market.pipeline()
        pipe.incr(rate_key)
        # 1-hour sliding window from first use
        pipe.expire(rate_key, 3600)
        await pipe.execute()
