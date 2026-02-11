"""
Routine Service - Business logic for Routine Mode.

Wraps the existing routine_panel and intel/routine_briefing modules
and provides a clean interface for the capability to use.

Philosophy: Help the trader arrive, not complete tasks.
Train how to begin, not what to do.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional


class RoutineService:
    """
    Routine Mode service.

    Handles all Routine-related business logic including:
    - Routine briefings (Mode A orientation + full briefing)
    - Market readiness aggregation
    - Log health context
    """

    def __init__(self, config: Dict[str, Any], logger: Any):
        self.config = config
        self.logger = logger
        self._synthesizer = None
        self._log_health_cache: Dict[str, List[Dict]] = {}

    def _get_synthesizer(self):
        """Lazy-load the routine briefing synthesizer."""
        if self._synthesizer is None:
            from services.vexy_ai.intel.routine_briefing import RoutineBriefingSynthesizer
            self._synthesizer = RoutineBriefingSynthesizer(self.config, self.logger)
        return self._synthesizer

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
        State of the Market v2 — deterministic synthesis.

        Reads from market-redis (spot, GEX), returns 4-lens market state.
        No LLM, no external API. Target: < 40ms.
        """
        import redis
        from services.vexy_ai.intel.market_reader import MarketReader
        from services.vexy_ai.market_state import MarketStateEngine

        try:
            buses = self.config.get("buses", {}) or {}
            market_url = buses.get("market-redis", {}).get("url", "redis://127.0.0.1:6380")
            r_market = redis.from_url(market_url, decode_responses=True)
            reader = MarketReader(r_market, self.logger)
            engine = MarketStateEngine(reader, self.logger)
            return engine.get_full_state()
        except Exception as e:
            self.logger.error(f"MarketStateEngine failed: {e}", emoji="💥")
            # Graceful degradation — return minimal valid envelope
            from services.vexy_ai.market_state import MarketStateEngine, ALL_HOLIDAYS
            from services.vexy_ai.routine_panel import get_routine_context_phase, RoutineContextPhase
            import pytz
            et = pytz.timezone("America/New_York")
            now = datetime.now(et)
            phase = get_routine_context_phase(now=now, holidays=ALL_HOLIDAYS)
            # Use same mapping as MarketStateEngine
            weekend_phases = {
                RoutineContextPhase.FRIDAY_NIGHT,
                RoutineContextPhase.WEEKEND_MORNING,
                RoutineContextPhase.WEEKEND_AFTERNOON,
                RoutineContextPhase.WEEKEND_EVENING,
            }
            if phase == RoutineContextPhase.HOLIDAY:
                ctx = "holiday"
            elif phase in weekend_phases:
                ctx = "weekend"
            elif phase == RoutineContextPhase.WEEKDAY_INTRADAY:
                ctx = "weekday_live"
            else:
                ctx = "weekday_premarket"
            return {
                "schema_version": "som.v2",
                "generated_at": now.isoformat(),
                "context_phase": ctx,
                "big_picture_volatility": None,
                "localized_volatility": None,
                "event_energy": None,
                "convexity_temperature": None,
            }

    def generate_briefing(
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
        """
        synthesizer = self._get_synthesizer()

        payload = {
            "mode": mode,
            "timestamp": timestamp,
            "market_context": market_context or {},
            "user_context": user_context or {},
            "open_loops": open_loops or {},
        }

        # Fetch log health signals if user_id provided
        log_health_signals = []
        if user_id:
            log_health_signals = self.get_log_health_signals(user_id)

        result = synthesizer.synthesize(payload, log_health_signals, user_id)
        return result

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
