"""
MarketIntelProvider — Shared Market Intelligence Layer.

Singleton that owns the MarketReader, EconomicIndicatorRegistry,
and a sync Redis connection to market-redis. Provides:
- get_som()       → cached 4-lens SoM payload (30s TTL)
- get_raw_state() → raw spots/GEX/heatmap for Commentary
- register_routes() → /api/vexy/market-state endpoint

Consumers: Routine panel, Chat, Commentary.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, Optional

import pytz


class MarketIntelProvider:
    """Shared market intelligence with TTL-based SoM caching."""

    def __init__(self, config: Dict[str, Any], logger: Any, ttl_sec: int = 30):
        self._config = config
        self._logger = logger
        self._ttl_sec = ttl_sec

        # Shared instances (created in initialize())
        self._registry = None
        self._market_reader = None
        self._market_redis = None

        # SoM cache
        self._som_cache: Optional[Dict] = None
        self._som_cache_ts: float = 0.0

    def initialize(self) -> None:
        """Create shared Redis connection, MarketReader, and EconomicIndicatorRegistry."""
        import redis
        from services.vexy_ai.intel.market_reader import MarketReader
        from services.vexy_ai.economic_indicators import EconomicIndicatorRegistry

        buses = self._config.get("buses", {}) or {}
        market_url = buses.get("market-redis", {}).get("url", "redis://127.0.0.1:6380")

        self._market_redis = redis.from_url(market_url, decode_responses=True)
        self._market_reader = MarketReader(self._market_redis, self._logger)

        self._registry = EconomicIndicatorRegistry(self._config, self._logger)
        try:
            self._registry.load_from_db()
            self._registry.start_subscription()
            count = len(self._registry._key_index)
            self._logger.info(
                f"MarketIntelProvider initialized ({count} indicators loaded)",
                emoji="🧠",
            )
        except Exception as e:
            self._logger.warning(
                f"Indicator registry init failed (non-fatal): {e}", emoji="⚠️"
            )

    # ── SoM (cached) ────────────────────────────────────────────────

    def get_som(self) -> Dict[str, Any]:
        """Return cached SoM payload. Recomputes if cache expired (TTL)."""
        now = time.monotonic()
        if self._som_cache is not None and (now - self._som_cache_ts) < self._ttl_sec:
            return self._som_cache

        try:
            from services.vexy_ai.market_state import MarketStateEngine

            engine = MarketStateEngine(
                self._market_reader,
                self._logger,
                registry=self._registry,
                market_redis=self._market_redis,
            )
            result = engine.get_full_state()
            self._som_cache = result
            self._som_cache_ts = now
            return result
        except Exception as e:
            self._logger.error(f"MarketStateEngine failed: {e}", emoji="💥")
            # Return stale cache if available
            if self._som_cache is not None:
                return self._som_cache
            return self._degraded_envelope()

    # ── Raw market state (for Commentary) ───────────────────────────

    def get_raw_state(self) -> Dict[str, Any]:
        """Raw market state (spots, GEX, heatmap). Not cached."""
        return self._market_reader.get_market_state()

    # ── HTTP route ──────────────────────────────────────────────────

    def register_routes(self, app) -> None:
        """Register /api/vexy/market-state endpoint on the FastAPI app."""
        from fastapi import APIRouter

        router = APIRouter()

        @router.get("/api/vexy/market-state")
        async def market_state():
            """State of the Market v2 — deterministic 4-lens synthesis."""
            return self.get_som()

        app.include_router(router)

    # ── Helpers ─────────────────────────────────────────────────────

    def _degraded_envelope(self) -> Dict[str, Any]:
        """Minimal valid SoM envelope when everything fails."""
        from services.vexy_ai.market_state import ALL_HOLIDAYS
        from services.vexy_ai.routine_panel import (
            get_routine_context_phase,
            RoutineContextPhase,
        )

        et = pytz.timezone("America/New_York")
        now = datetime.now(et)
        phase = get_routine_context_phase(now=now, holidays=ALL_HOLIDAYS)

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

    def shutdown(self) -> None:
        """Clean up resources."""
        if self._market_redis:
            try:
                self._market_redis.close()
            except Exception:
                pass
        self._market_redis = None
        self._market_reader = None
        self._registry = None
        self._som_cache = None
