"""
Job Manager — Async job lifecycle using asyncio.Task + Redis.

Manages job creation, progress publishing, completion, and cleanup.
Jobs are in-memory asyncio.Tasks with Redis metadata for observability.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, Callable, Coroutine, Dict, Optional

from .models import (
    InteractionProgressEvent,
    InteractionResultEvent,
    InteractionErrorEvent,
)


# Concurrency limits per tier
CONCURRENCY_LIMITS: Dict[str, int] = {
    "observer": 1,
    "observer_restricted": 1,
    "activator": 2,
    "navigator": 3,
    "coaching": 3,
    "administrator": 5,
}

JOB_TTL_SECONDS = 3600  # 1 hour after completion


class JobManager:
    """
    Manages async interaction jobs.

    Jobs are asyncio.Tasks with Redis state for observability.
    Progress events are published to Redis pub/sub for SSE delivery.
    """

    def __init__(self, buses: Any, logger: Any):
        """
        Args:
            buses: RedisBusAdapter (has .market property for Redis client)
            logger: LogUtil instance
        """
        self._buses = buses
        self._logger = logger
        self._active_tasks: Dict[str, asyncio.Task] = {}      # job_id -> Task
        self._user_jobs: Dict[int, Dict[str, str]] = {}        # user_id -> {surface: job_id}

    async def create_job(
        self,
        interaction_id: str,
        user_id: int,
        surface: str,
        tier: str,
    ) -> str:
        """
        Create a new job record in Redis and register in-memory tracking.

        Returns:
            job_id (UUID string)
        """
        job_id = str(uuid.uuid4())

        # Store job metadata in Redis
        job_key = f"vexy:job:{job_id}"
        job_data = {
            "job_id": job_id,
            "interaction_id": interaction_id,
            "user_id": str(user_id),
            "surface": surface,
            "tier": tier,
            "status": "created",
            "stage": "",
            "created_at": int(time.time() * 1000),
            "updated_at": int(time.time() * 1000),
        }

        await self._buses.market.hset(job_key, mapping=job_data)
        await self._buses.market.expire(job_key, JOB_TTL_SECONDS)

        # Track user -> surface -> job_id for dedup
        if user_id not in self._user_jobs:
            self._user_jobs[user_id] = {}
        self._user_jobs[user_id][surface] = job_id

        return job_id

    async def start_job(
        self,
        job_id: str,
        coro: Coroutine,
    ) -> None:
        """
        Start an async job as a fire-and-forget task.

        The coroutine should call update_stage / complete_job / fail_job
        during its execution.
        """
        async def _wrapper():
            try:
                await coro
            except asyncio.CancelledError:
                self._logger.info(f"Job {job_id[:8]} cancelled")
            except Exception as e:
                self._logger.error(f"Job {job_id[:8]} failed: {e}")
                await self.fail_job(job_id, str(e))
            finally:
                self._active_tasks.pop(job_id, None)

        task = asyncio.create_task(_wrapper())
        self._active_tasks[job_id] = task

        # Update Redis status
        job_key = f"vexy:job:{job_id}"
        await self._buses.market.hset(job_key, mapping={
            "status": "running",
            "updated_at": str(int(time.time() * 1000)),
        })

    async def update_stage(
        self,
        job_id: str,
        user_id: int,
        stage: str,
        stage_index: int,
        stage_count: int,
        message: str,
    ) -> None:
        """Publish a progress event to SSE via Redis pub/sub."""
        event = InteractionProgressEvent(
            job_id=job_id,
            stage=stage,
            stage_index=stage_index,
            stage_count=stage_count,
            message=message,
        )

        # Update Redis job record
        job_key = f"vexy:job:{job_id}"
        await self._buses.market.hset(job_key, mapping={
            "stage": stage,
            "status": "running",
            "updated_at": str(int(time.time() * 1000)),
        })

        # Publish to user's channel
        channel = f"vexy_interaction:{user_id}"
        await self._buses.market.publish(channel, event.model_dump_json())

    async def complete_job(
        self,
        job_id: str,
        user_id: int,
        interaction_id: str,
        text: str,
        agent: str,
        agent_blend: list,
        tokens_used: int = 0,
        elevation_hint: Optional[str] = None,
        remaining_today: int = -1,
    ) -> None:
        """Publish result event and clean up job tracking."""
        event = InteractionResultEvent(
            job_id=job_id,
            interaction_id=interaction_id,
            text=text,
            agent=agent,
            agent_blend=agent_blend,
            tokens_used=tokens_used,
            elevation_hint=elevation_hint,
            remaining_today=remaining_today,
        )

        # Update Redis job record
        job_key = f"vexy:job:{job_id}"
        await self._buses.market.hset(job_key, mapping={
            "status": "completed",
            "stage": "done",
            "updated_at": str(int(time.time() * 1000)),
        })
        await self._buses.market.expire(job_key, JOB_TTL_SECONDS)

        # Publish result to user's channel
        channel = f"vexy_interaction:{user_id}"
        await self._buses.market.publish(channel, event.model_dump_json())

        # Remove from user's active jobs
        self._remove_user_job(user_id, job_id)

    async def fail_job(
        self,
        job_id: str,
        error: str,
        recoverable: bool = True,
    ) -> None:
        """Publish error event and clean up job tracking."""
        # Get job metadata from Redis to find user_id and interaction_id
        job_key = f"vexy:job:{job_id}"
        job_data = await self._buses.market.hgetall(job_key)

        user_id = int(job_data.get("user_id", 0))
        interaction_id = job_data.get("interaction_id", "")

        event = InteractionErrorEvent(
            job_id=job_id,
            interaction_id=interaction_id,
            error=error,
            recoverable=recoverable,
        )

        # Update Redis
        await self._buses.market.hset(job_key, mapping={
            "status": "failed",
            "error": error,
            "updated_at": str(int(time.time() * 1000)),
        })
        await self._buses.market.expire(job_key, JOB_TTL_SECONDS)

        # Publish error to user's channel
        if user_id:
            channel = f"vexy_interaction:{user_id}"
            await self._buses.market.publish(channel, event.model_dump_json())

        # Remove from user's active jobs
        if user_id:
            self._remove_user_job(user_id, job_id)

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job. Returns True if cancelled."""
        task = self._active_tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            # fail_job is called from the wrapper's except CancelledError
            await self.fail_job(job_id, "Cancelled by user", recoverable=False)
            return True
        return False

    def get_active_job(self, user_id: int, surface: str) -> Optional[str]:
        """Check if user has an active job for this surface (dedup check)."""
        user_jobs = self._user_jobs.get(user_id, {})
        job_id = user_jobs.get(surface)
        if job_id and job_id in self._active_tasks:
            task = self._active_tasks[job_id]
            if not task.done():
                return job_id
            # Task finished, clean up stale reference
            self._remove_user_job(user_id, job_id)
        return None

    def enforce_concurrency(self, user_id: int, tier: str) -> bool:
        """Check if user can start a new job (within concurrency limit)."""
        limit = CONCURRENCY_LIMITS.get(tier, 1)
        user_jobs = self._user_jobs.get(user_id, {})

        # Count only active (non-done) jobs
        active_count = 0
        for job_id in user_jobs.values():
            task = self._active_tasks.get(job_id)
            if task and not task.done():
                active_count += 1

        return active_count < limit

    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job status from Redis (polling fallback)."""
        job_key = f"vexy:job:{job_id}"
        data = await self._buses.market.hgetall(job_key)
        return data if data else None

    async def list_active_jobs(self) -> list:
        """List all active jobs (for admin)."""
        jobs = []
        for job_id, task in self._active_tasks.items():
            if not task.done():
                status = await self.get_job_status(job_id)
                if status:
                    jobs.append(status)
        return jobs

    async def cleanup_stale_jobs(self) -> int:
        """Clean up finished tasks from in-memory tracking. Run periodically."""
        cleaned = 0
        stale_job_ids = []

        for job_id, task in self._active_tasks.items():
            if task.done():
                stale_job_ids.append(job_id)

        for job_id in stale_job_ids:
            self._active_tasks.pop(job_id, None)
            cleaned += 1

        # Clean up stale user job references
        for user_id in list(self._user_jobs.keys()):
            for surface in list(self._user_jobs[user_id].keys()):
                job_id = self._user_jobs[user_id][surface]
                if job_id not in self._active_tasks:
                    del self._user_jobs[user_id][surface]
            if not self._user_jobs[user_id]:
                del self._user_jobs[user_id]

        if cleaned:
            self._logger.debug(f"Cleaned {cleaned} stale jobs")
        return cleaned

    def _remove_user_job(self, user_id: int, job_id: str) -> None:
        """Remove a specific job from user tracking."""
        user_jobs = self._user_jobs.get(user_id, {})
        for surface, jid in list(user_jobs.items()):
            if jid == job_id:
                del user_jobs[surface]
                break
        if not user_jobs and user_id in self._user_jobs:
            del self._user_jobs[user_id]
