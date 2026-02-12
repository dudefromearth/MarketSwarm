"""
Routine Service - Business logic for Routine Mode.

Wraps the existing routine_panel and intel/routine_briefing modules
and provides a clean interface for the capability to use.

Philosophy: Help the trader arrive, not complete tasks.
Train how to begin, not what to do.

All LLM calls route through VexyKernel.reason().
"""

import uuid
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional


class RoutineService:
    """
    Routine Mode service.

    Handles all Routine-related business logic including:
    - Routine briefings — via VexyKernel.reason()
    - Market readiness aggregation
    - Log health context

    What moved to kernel: System prompt (ROUTINE_MODE_SYSTEM_PROMPT), LLM call,
    Assistants API, direct httpx calls.
    What stays here: build_routine_prompt() context formatting, orientation,
    market readiness, log health.
    """

    def __init__(self, config: Dict[str, Any], logger: Any, market_intel=None, kernel=None):
        self.config = config
        self.logger = logger
        self.market_intel = market_intel
        self.kernel = kernel
        self._log_health_cache: Dict[str, List[Dict]] = {}

    def _get_synthesizer(self):
        """
        Lazy-load the legacy routine briefing synthesizer.

        DEPRECATED: Only used as fallback if kernel is not available.
        """
        from services.vexy_ai.intel.routine_briefing import RoutineBriefingSynthesizer
        return RoutineBriefingSynthesizer(self.config, self.logger)

    def get_orientation(
        self,
        vix_level: Optional[float] = None,
        vix_regime: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get Mode A orientation message.

        May return null orientation (silence is valid).
        Adapts to RoutineContextPhase.
        """
        from services.vexy_ai.routine_panel import (
            RoutineOrientationGenerator,
            get_routine_context_phase,
        )

        phase = get_routine_context_phase()
        generator = RoutineOrientationGenerator()

        orientation = generator.generate(
            phase=phase,
            vix_level=vix_level,
            vix_regime=vix_regime,
        )

        return {
            "orientation": orientation,
            "context_phase": phase.value,
            "generated_at": datetime.now().isoformat(),
        }

    def get_market_readiness(self, user_id: int) -> Dict[str, Any]:
        """
        Get cached market readiness artifact.

        Returns read-only awareness data, not predictions.
        Enforces lexicon constraints (no POC/VAH/VAL).
        """
        from services.vexy_ai.routine_panel import MarketReadinessAggregator

        aggregator = MarketReadinessAggregator(logger=self.logger)
        payload = aggregator.aggregate(user_id)

        return {
            "success": True,
            "data": payload,
        }

    def get_market_state(self) -> Dict[str, Any]:
        """
        State of the Market v2 — delegates to shared MarketIntelProvider.
        """
        if self.market_intel:
            return self.market_intel.get_som()
        # Fallback (should not happen in normal operation)
        self.logger.warning("No market_intel provider, returning degraded envelope", emoji="⚠️")
        from services.vexy_ai.market_intel import MarketIntelProvider
        stub = MarketIntelProvider(self.config, self.logger)
        return stub._degraded_envelope()

    async def generate_briefing(
        self,
        mode: str,
        timestamp: Optional[str],
        market_context: Optional[Dict[str, Any]],
        user_context: Optional[Dict[str, Any]],
        open_loops: Optional[Dict[str, Any]],
        user_id: Optional[int],
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a Routine Mode orientation briefing.

        Called explicitly by the UI when the Routine drawer opens.
        Routes through VexyKernel.reason().
        """
        # Fetch log health signals if user_id provided
        log_health_signals = []
        if user_id:
            log_health_signals = self.get_log_health_signals(user_id)

        # If kernel is available, use it
        if self.kernel:
            return await self._generate_briefing_via_kernel(
                mode, timestamp, market_context, user_context,
                open_loops, user_id, log_health_signals,
            )

        # Fallback to legacy synthesizer (deprecated)
        self.logger.warn("Kernel not available, using legacy synthesizer", emoji="⚠️")
        synthesizer = self._get_synthesizer()
        payload = {
            "mode": mode,
            "timestamp": timestamp,
            "market_context": market_context or {},
            "user_context": user_context or {},
            "open_loops": open_loops or {},
        }
        return synthesizer.synthesize(payload, log_health_signals, user_id)

    async def _generate_briefing_via_kernel(
        self,
        mode: str,
        timestamp: Optional[str],
        market_context: Optional[Dict[str, Any]],
        user_context: Optional[Dict[str, Any]],
        open_loops: Optional[Dict[str, Any]],
        user_id: Optional[int],
        log_health_signals: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Generate briefing via VexyKernel.reason()."""
        from services.vexy_ai.intel.routine_briefing import build_routine_prompt
        from services.vexy_ai.kernel import ReasoningRequest

        payload = {
            "mode": mode,
            "timestamp": timestamp,
            "market_context": market_context or {},
            "user_context": user_context or {},
            "open_loops": open_loops or {},
        }

        # Reuse build_routine_prompt for context formatting (stays in routine_briefing)
        user_prompt = build_routine_prompt(payload, log_health_signals, user_id)

        request = ReasoningRequest(
            outlet="routine",
            user_message=user_prompt,
            user_id=user_id or 1,
            tier="navigator",  # TODO: pass actual tier
            reflection_dial=0.6,
            market_context=market_context,
            user_context=user_context,
            open_loops=open_loops,
            log_health_signals=log_health_signals,
        )

        response = await self.kernel.reason(request)

        if not response.text:
            return None

        return {
            "briefing_id": str(uuid.uuid4()),
            "mode": "routine",
            "narrative": response.text,
            "generated_at": datetime.now(UTC).isoformat(),
            "model": f"vexy-kernel-v1 ({response.provider})",
            "agent": response.agent_selected,
        }

    def ingest_log_health_context(
        self,
        user_id: int,
        routine_date: str,
        signals: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Ingest log health context for Routine Mode narratives.

        Called by the log_health_analyzer scheduled job at 05:00 ET daily.
        Context is stored per (user_id, routine_date) and is idempotent.
        """
        cache_key = f"{user_id}:{routine_date}"
        self._log_health_cache[cache_key] = signals

        self.logger.info(
            f"Ingested {len(signals)} log health signals for user {user_id} on {routine_date}",
            emoji="📋"
        )

        return {
            "success": True,
            "message": f"Ingested {len(signals)} signals",
            "signal_count": len(signals),
        }

    def get_log_health_context(self, user_id: int) -> Dict[str, Any]:
        """
        Get log health context for a user.

        Returns today's signals if available.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        cache_key = f"{user_id}:{today}"

        signals = self._log_health_cache.get(cache_key, [])

        return {
            "success": True,
            "user_id": user_id,
            "routine_date": today,
            "signals": signals,
            "signal_count": len(signals),
        }

    def get_log_health_signals(self, user_id: int) -> List[Dict[str, Any]]:
        """Get log health signals for briefing context."""
        today = datetime.now().strftime("%Y-%m-%d")
        cache_key = f"{user_id}:{today}"
        return self._log_health_cache.get(cache_key, [])

    def get_context_phase(self) -> Dict[str, Any]:
        """Get current routine context phase."""
        from services.vexy_ai.routine_panel import get_routine_context_phase

        phase = get_routine_context_phase()

        return {
            "phase": phase.value,
            "timestamp": datetime.now().isoformat(),
        }
