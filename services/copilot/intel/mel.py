"""
MEL Orchestrator - Model Effectiveness Layer coordination.

The MEL orchestrator:
1. Coordinates individual model calculators
2. Calculates cross-model coherence
3. Computes global structure integrity
4. Maintains snapshot history
5. Detects event overrides

Based on TraderDH's MEL specification.
"""

import logging
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from collections import deque
import asyncio

from .mel_models import (
    MELSnapshot,
    MELModelScore,
    MELDelta,
    MELConfig,
    ModelState,
    CoherenceState,
    Session,
    EventFlag,
    generate_snapshot_id,
)
from .mel_calculator import MELCalculator, DummyCalculator
from .mel_gamma import GammaEffectivenessCalculator
from .mel_volume_profile import VolumeProfileEffectivenessCalculator
from .mel_liquidity import LiquidityEffectivenessCalculator
from .mel_volatility import VolatilityEffectivenessCalculator
from .mel_session import SessionEffectivenessCalculator
from .mel_coherence import CoherenceCalculator, get_coherence_multiplier


class MELOrchestrator:
    """
    Model Effectiveness Layer orchestrator.

    Coordinates all MEL calculators and produces unified snapshots
    that answer: "Are market models valid right now?"
    """

    def __init__(
        self,
        config: Optional[MELConfig] = None,
        logger: Optional[logging.Logger] = None,
        market_data_provider: Optional[Callable[[], Dict[str, Any]]] = None,
        event_calendar: Optional[Callable[[datetime], List[str]]] = None,
    ):
        self.config = config or MELConfig()
        self.logger = logger or logging.getLogger("MEL")
        self.market_data_provider = market_data_provider
        self.event_calendar = event_calendar

        # Calculators - will be registered
        self._calculators: Dict[str, MELCalculator] = {}

        # Snapshot history
        self._history: deque = deque(maxlen=1000)
        self._last_snapshot: Optional[MELSnapshot] = None

        # Coherence calculator
        self._coherence_calc = CoherenceCalculator(config=self.config, logger=self.logger)

        # Subscribers for real-time updates
        self._subscribers: List[Callable[[MELSnapshot], None]] = []

        # Running state
        self._running = False
        self._calculation_task: Optional[asyncio.Task] = None

        self._register_default_calculators()

    def _register_default_calculators(self) -> None:
        """Register real MEL calculators for all models."""
        self._calculators["gamma"] = GammaEffectivenessCalculator(
            config=self.config,
            logger=self.logger,
        )
        self._calculators["volume_profile"] = VolumeProfileEffectivenessCalculator(
            config=self.config,
            logger=self.logger,
        )
        self._calculators["liquidity"] = LiquidityEffectivenessCalculator(
            config=self.config,
            logger=self.logger,
        )
        self._calculators["volatility"] = VolatilityEffectivenessCalculator(
            config=self.config,
            logger=self.logger,
        )
        self._calculators["session"] = SessionEffectivenessCalculator(
            config=self.config,
            logger=self.logger,
        )

    def register_calculator(self, calculator: MELCalculator) -> None:
        """Register a model calculator."""
        self._calculators[calculator.model_name] = calculator
        self.logger.info(f"Registered {calculator.model_name} calculator")

    def subscribe(self, callback: Callable[[MELSnapshot], None]) -> None:
        """Subscribe to MEL snapshot updates."""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[MELSnapshot], None]) -> None:
        """Unsubscribe from MEL snapshot updates."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    async def start(self) -> None:
        """Start periodic MEL calculation."""
        if self._running:
            self.logger.warning("MEL orchestrator already running")
            return

        self._running = True
        self._calculation_task = asyncio.create_task(self._calculation_loop())
        self.logger.info("MEL orchestrator started")

    async def stop(self) -> None:
        """Stop periodic MEL calculation."""
        self._running = False
        if self._calculation_task:
            self._calculation_task.cancel()
            try:
                await self._calculation_task
            except asyncio.CancelledError:
                pass
        self.logger.info("MEL orchestrator stopped")

    async def _calculation_loop(self) -> None:
        """Main calculation loop."""
        interval_seconds = self.config.snapshot_interval_ms / 1000

        while self._running:
            try:
                snapshot = await self.calculate_snapshot()

                # Notify subscribers
                for subscriber in self._subscribers:
                    try:
                        subscriber(snapshot)
                    except Exception as e:
                        self.logger.error(f"Subscriber error: {e}")

                await asyncio.sleep(interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"MEL calculation error: {e}")
                await asyncio.sleep(interval_seconds)

    async def calculate_snapshot(self) -> MELSnapshot:
        """
        Calculate current MEL snapshot.

        This is the main entry point for snapshot generation.
        """
        now = datetime.utcnow()

        # Get market data
        market_data = {}
        if self.market_data_provider:
            market_data = self.market_data_provider()

        # Calculate individual model scores
        gamma = self._calculators["gamma"].calculate_score(market_data)
        volume_profile = self._calculators["volume_profile"].calculate_score(market_data)
        liquidity = self._calculators["liquidity"].calculate_score(market_data)
        volatility = self._calculators["volatility"].calculate_score(market_data)
        session_score = self._calculators["session"].calculate_score(market_data)

        # Calculate cross-model coherence
        coherence, coherence_state, coherence_detail = self._calculate_coherence(
            gamma, volume_profile, liquidity, volatility, session_score, market_data
        )

        # Calculate global structure integrity
        global_integrity = self._calculate_global_integrity(
            gamma, volume_profile, liquidity, volatility, session_score,
            coherence_state
        )

        # Calculate delta from last snapshot
        delta = self._calculate_delta(
            gamma, volume_profile, liquidity, volatility, session_score,
            global_integrity
        )

        # Check for event overrides
        event_flags = self._check_event_flags(now)

        # Create snapshot
        snapshot = MELSnapshot(
            timestamp_utc=now,
            snapshot_id=generate_snapshot_id(),
            session=self._determine_session(now),
            event_flags=event_flags,
            gamma=gamma,
            volume_profile=volume_profile,
            liquidity=liquidity,
            volatility=volatility,
            session_structure=session_score,
            cross_model_coherence=coherence,
            coherence_state=coherence_state,
            global_structure_integrity=global_integrity,
            delta=delta,
        )

        # Update history
        self._history.append(snapshot)
        self._last_snapshot = snapshot

        # Log state changes
        self._log_state_changes(snapshot)

        return snapshot

    def _calculate_coherence(
        self,
        gamma: MELModelScore,
        volume_profile: MELModelScore,
        liquidity: MELModelScore,
        volatility: MELModelScore,
        session: MELModelScore,
        market_data: Optional[Dict[str, Any]] = None,
    ) -> tuple[float, CoherenceState, Dict[str, Any]]:
        """
        Calculate cross-model coherence using the CoherenceCalculator.

        Returns:
            Tuple of (coherence_score, coherence_state, coherence_detail)
        """
        return self._coherence_calc.calculate_coherence(
            gamma=gamma,
            volume_profile=volume_profile,
            liquidity=liquidity,
            volatility=volatility,
            session=session,
            market_data=market_data,
        )

    def _calculate_global_integrity(
        self,
        gamma: MELModelScore,
        volume_profile: MELModelScore,
        liquidity: MELModelScore,
        volatility: MELModelScore,
        session: MELModelScore,
        coherence_state: CoherenceState,
    ) -> float:
        """
        Calculate Global Structure Integrity score.

        Weighted average of model effectiveness × coherence multiplier.
        """
        weights = self.config.weights
        multipliers = self.config.coherence_multipliers

        weighted_sum = (
            weights["gamma"] * gamma.effectiveness +
            weights["volume_profile"] * volume_profile.effectiveness +
            weights["liquidity"] * liquidity.effectiveness +
            weights["volatility"] * volatility.effectiveness +
            weights["session"] * session.effectiveness
        )

        multiplier = multipliers.get(coherence_state.value, 1.0)

        return weighted_sum * multiplier

    def _calculate_delta(
        self,
        gamma: MELModelScore,
        volume_profile: MELModelScore,
        liquidity: MELModelScore,
        volatility: MELModelScore,
        session: MELModelScore,
        global_integrity: float,
    ) -> Optional[MELDelta]:
        """Calculate delta from previous snapshot."""
        if not self._last_snapshot:
            return None

        last = self._last_snapshot

        return MELDelta(
            gamma_effectiveness=gamma.effectiveness - last.gamma.effectiveness,
            volume_profile_effectiveness=volume_profile.effectiveness - last.volume_profile.effectiveness,
            liquidity_effectiveness=liquidity.effectiveness - last.liquidity.effectiveness,
            volatility_effectiveness=volatility.effectiveness - last.volatility.effectiveness,
            session_effectiveness=session.effectiveness - last.session_structure.effectiveness,
            global_integrity=global_integrity - last.global_structure_integrity,
        )

    def _check_event_flags(self, now: datetime) -> List[str]:
        """Check for events that might override model validity."""
        flags = []

        if self.event_calendar:
            flags = self.event_calendar(now)

        return flags

    def _determine_session(self, now: datetime) -> Session:
        """Determine current market session."""
        # Simple implementation - override for proper logic
        hour = now.hour

        # Assuming Eastern time for US markets
        # RTH: 9:30 AM - 4:00 PM ET
        # This is a simplified check - proper implementation would use timezone-aware logic

        if 9 <= hour <= 16:
            return Session.RTH
        elif 4 <= hour <= 9 or 16 <= hour <= 20:
            return Session.ETH
        else:
            return Session.GLOBEX

    def _log_state_changes(self, snapshot: MELSnapshot) -> None:
        """Log significant state changes."""
        if not self._last_snapshot:
            return

        last = self._last_snapshot
        models = [
            ("gamma", snapshot.gamma, last.gamma),
            ("volume_profile", snapshot.volume_profile, last.volume_profile),
            ("liquidity", snapshot.liquidity, last.liquidity),
            ("volatility", snapshot.volatility, last.volatility),
            ("session", snapshot.session_structure, last.session_structure),
        ]

        for name, current, previous in models:
            if current.state != previous.state:
                self.logger.warning(
                    f"MEL state change: {name} {previous.state.value} -> {current.state.value} "
                    f"({current.effectiveness:.1f}%)"
                )

        # Log global integrity warnings
        if snapshot.global_structure_integrity < 50:
            self.logger.warning(
                f"MEL ALERT: Global Structure Integrity at {snapshot.global_structure_integrity:.1f}% - "
                f"Structure may be absent"
            )

    # ========== Query Methods ==========

    def get_current_snapshot(self) -> Optional[MELSnapshot]:
        """Get most recent snapshot."""
        return self._last_snapshot

    def get_history(
        self,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[MELSnapshot]:
        """Get snapshot history."""
        snapshots = list(self._history)

        if since:
            snapshots = [s for s in snapshots if s.timestamp_utc >= since]

        return snapshots[-limit:]

    def get_model_state(self, model_name: str) -> Optional[ModelState]:
        """Get current state for a specific model."""
        if not self._last_snapshot:
            return None

        model_map = {
            "gamma": self._last_snapshot.gamma,
            "volume_profile": self._last_snapshot.volume_profile,
            "liquidity": self._last_snapshot.liquidity,
            "volatility": self._last_snapshot.volatility,
            "session": self._last_snapshot.session_structure,
        }

        score = model_map.get(model_name)
        return score.state if score else None

    def is_model_valid(self, model_name: str) -> bool:
        """Check if a model is currently VALID."""
        state = self.get_model_state(model_name)
        return state == ModelState.VALID if state else False

    def is_structure_present(self) -> bool:
        """Check if overall market structure is present (global integrity >= 50%)."""
        if not self._last_snapshot:
            return False
        return self._last_snapshot.global_structure_integrity >= 50

    def get_state_summary(self) -> str:
        """Get compact state summary string."""
        if not self._last_snapshot:
            return "MEL: No data"
        return self._last_snapshot.get_state_summary()
