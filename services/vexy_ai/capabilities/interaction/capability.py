"""
Interaction Capability — Two-layer async interaction system.

Registers endpoints:
- POST /api/vexy/interaction          -> Dialog ACK + start async job
- POST /api/vexy/interaction/cancel/{job_id}  -> Cancel running job
- GET  /api/vexy/interaction/job/{job_id}     -> Job status (polling fallback)

Background task: cleanup_stale_jobs() every 60 seconds.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from ...core.capability import BaseCapability
from ...interaction.models import InteractionRequest, DialogResponse
from .service import InteractionService


class InteractionCapability(BaseCapability):
    name = "interaction"
    version = "1.0.0"
    dependencies = ["chat"]  # Needs kernel to be available
    buses_required = ["market"]

    async def start(self) -> None:
        kernel = getattr(self.vexy, 'kernel', None)
        if not kernel:
            self.logger.warn("Interaction capability: kernel not available", emoji="⚠️")
            return

        market_intel = getattr(self.vexy, 'market_intel', None)
        self.service = InteractionService(
            config=self.config,
            logger=self.logger,
            kernel=kernel,
            buses=self.vexy.buses,
            market_intel=market_intel,
        )
        await self.service.initialize()
        self._started = True
        self.logger.info("Interaction capability started", emoji="🔄")

    async def stop(self) -> None:
        self.service = None
        self._started = False

    def get_routes(self) -> Optional[APIRouter]:
        router = APIRouter(tags=["Interaction"])

        @router.post("/api/vexy/interaction", response_model=DialogResponse)
        async def handle_interaction(request: InteractionRequest, req: Request):
            """
            Two-layer interaction endpoint.

            Returns fast ACK (<250ms) with job_id for SSE streaming.
            """
            if not self._started or not self.service:
                raise HTTPException(status_code=503, detail="Interaction system not ready")

            # Extract user info from request headers (set by SSE gateway proxy)
            user_id_str = req.headers.get("X-User-Id", "0")
            user_email = req.headers.get("X-User-Email", "")

            try:
                user_id = int(user_id_str) if user_id_str else 0
            except ValueError:
                user_id = 0

            if not user_id:
                raise HTTPException(status_code=401, detail="Authentication required")

            # Get user profile for tier resolution
            # Roles come from the profile; created_at for trial check
            user_profile = request.user_profile or {}
            roles = user_profile.get("roles")
            created_at = user_profile.get("created_at")

            response = await self.service.handle_interaction(
                request=request,
                user_id=user_id,
                roles=roles,
                created_at=created_at,
            )
            return response

        @router.post("/api/vexy/interaction/cancel/{job_id}")
        async def cancel_interaction(job_id: str):
            """Cancel a running interaction job."""
            if not self._started or not self.service:
                raise HTTPException(status_code=503, detail="Interaction system not ready")

            cancelled = await self.service.cancel_job(job_id)
            return {"success": cancelled, "job_id": job_id}

        @router.get("/api/vexy/interaction/job/{job_id}")
        async def get_job_status(job_id: str):
            """Get job status (polling fallback)."""
            if not self._started or not self.service:
                raise HTTPException(status_code=503, detail="Interaction system not ready")

            status = await self.service.get_job_status(job_id)
            if not status:
                raise HTTPException(status_code=404, detail="Job not found")

            return {"success": True, "job": status}

        return router

    def get_background_tasks(self):
        return [self._cleanup_loop]

    async def _cleanup_loop(self):
        """Periodically clean up stale jobs."""
        while True:
            try:
                if self.service:
                    await self.service.cleanup_stale_jobs()
            except Exception as e:
                self.logger.warning(f"Job cleanup error: {e}")
            await asyncio.sleep(60)
