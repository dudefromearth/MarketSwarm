"""
Cognition Layer — Async kernel orchestration with observable stages.

Wraps kernel.reason() with pre-work and post-processing stages,
publishing progress events through the JobManager for SSE delivery.

The kernel itself remains unchanged — this layer adds observability around it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..kernel import ReasoningRequest, ReasoningResponse


# Stage definitions: (name, human-readable message)
STAGES = [
    ("hydrate_echo", "Gathering your context..."),
    ("select_playbooks", "Selecting relevant playbooks..."),
    ("fetch_context", "Noticing what stands out..."),
    ("reason", "Reflecting..."),
    ("validate", "Checking against doctrine..."),
    ("finalize", "Packaging response..."),
]


class CognitionLayer:
    """
    Async kernel orchestration with stage-based progress reporting.

    Stages 1-3: Pre-work (echo loading, playbook lookup, context gathering)
    Stage 4: The monolithic kernel.reason() call
    Stages 5-6: Post-processing (validation review, final packaging)

    The kernel is NOT modified — all stages wrap around it.
    """

    def __init__(self, kernel: Any, logger: Any):
        """
        Args:
            kernel: VexyKernel instance
            logger: LogUtil instance
        """
        self._kernel = kernel
        self._logger = logger

    async def execute(
        self,
        job_id: str,
        user_id: int,
        interaction_id: str,
        request: "InteractionRequest",
        tier: str,
        job_manager: Any,
        elevation_hint: Optional[str] = None,
        remaining_today: int = -1,
    ) -> None:
        """
        Execute the full cognition pipeline with stage reporting.

        This is called as a fire-and-forget coroutine via JobManager.start_job().
        Progress is published to SSE. Final result or error is published at the end.
        """
        from .models import InteractionRequest as IR

        stage_count = len(STAGES)

        try:
            # Stage 1: Hydrate echo
            await job_manager.update_stage(
                job_id, user_id, "hydrate_echo", 0, stage_count,
                "Gathering your context..."
            )
            # Echo hydration happens inside kernel, but we signal the stage
            echo_context = self._prepare_echo_context(request, tier)

            # Stage 2: Select playbooks
            await job_manager.update_stage(
                job_id, user_id, "select_playbooks", 1, stage_count,
                "Selecting relevant playbooks..."
            )
            # Playbook selection also happens inside kernel

            # Stage 3: Fetch context
            await job_manager.update_stage(
                job_id, user_id, "fetch_context", 2, stage_count,
                "Noticing what stands out..."
            )
            # Build the ReasoningRequest for the kernel
            reasoning_request = self._build_reasoning_request(request, user_id, tier)

            # Stage 4: Reason (the actual LLM call)
            await job_manager.update_stage(
                job_id, user_id, "reason", 3, stage_count,
                "Reflecting..."
            )
            response: ReasoningResponse = await self._kernel.reason(reasoning_request)

            # Stage 5: Validate
            await job_manager.update_stage(
                job_id, user_id, "validate", 4, stage_count,
                "Checking against doctrine..."
            )
            # Validation already happened inside kernel.reason() — this stage
            # signals that post-LLM checks are complete

            # Stage 6: Finalize
            await job_manager.update_stage(
                job_id, user_id, "finalize", 5, stage_count,
                "Packaging response..."
            )

            # Publish result
            await job_manager.complete_job(
                job_id=job_id,
                user_id=user_id,
                interaction_id=interaction_id,
                text=response.text,
                agent=response.agent_selected,
                agent_blend=response.agent_blend,
                tokens_used=response.tokens_used,
                elevation_hint=elevation_hint,
                remaining_today=remaining_today,
            )

            self._logger.info(
                f"Interaction {interaction_id[:8]} complete: "
                f"{response.agent_selected} | {response.tokens_used} tok",
                emoji="🧠"
            )

        except Exception as e:
            self._logger.error(
                f"Cognition failed for interaction {interaction_id[:8]}: {e}",
                emoji="❌"
            )
            await job_manager.fail_job(job_id, str(e), recoverable=True)

    def _build_reasoning_request(
        self,
        request: Any,
        user_id: int,
        tier: str,
    ) -> ReasoningRequest:
        """Convert InteractionRequest to kernel ReasoningRequest."""
        # Map surface to outlet name
        outlet_map = {
            "chat": "chat",
            "routine": "routine",
            "journal": "journal",
            "playbook": "playbook",
        }
        outlet = outlet_map.get(request.surface, "chat")

        return ReasoningRequest(
            outlet=outlet,
            user_message=request.message,
            user_id=user_id,
            tier=tier,
            reflection_dial=request.reflection_dial,
            context=request.context,
            user_profile=request.user_profile,
            market_context=request.market_context,
            user_context=request.user_context,
            open_loops=request.open_loops,
        )

    def _prepare_echo_context(self, request: Any, tier: str) -> Optional[Dict]:
        """Pre-stage for echo context. Actual injection happens in kernel."""
        # The kernel handles echo injection internally based on tier.
        # This stage exists for progress visibility.
        return None
