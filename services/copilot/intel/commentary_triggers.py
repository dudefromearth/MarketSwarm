"""
Commentary Triggers - Detect events that should trigger AI commentary.

Triggers are events in the market or UI that warrant AI observation.
This module handles detection, debouncing, and prioritization.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable, Set
from datetime import datetime, timedelta
from collections import deque

from .commentary_models import (
    CommentaryTrigger,
    TriggerType,
    MELStateChangeTrigger,
    GlobalIntegrityWarningTrigger,
    CoherenceChangeTrigger,
    SpotCrossedLevelTrigger,
    TileSelectedTrigger,
    TradeEventTrigger,
)
from .mel_models import MELSnapshot, ModelState


class TriggerDetector:
    """
    Detects and manages commentary triggers.

    Responsibilities:
    - Monitor MEL snapshots for state changes
    - Track level crossings
    - Debounce rapid-fire triggers
    - Prioritize important triggers
    """

    def __init__(
        self,
        debounce_seconds: float = 2.0,
        max_queue_size: int = 50,
        logger: Optional[logging.Logger] = None,
    ):
        self.debounce_seconds = debounce_seconds
        self.max_queue_size = max_queue_size
        self.logger = logger or logging.getLogger("TriggerDetector")

        # Trigger queue
        self._queue: deque[CommentaryTrigger] = deque(maxlen=max_queue_size)

        # Debounce tracking
        self._last_trigger_time: Dict[str, datetime] = {}
        self._suppressed_types: Set[TriggerType] = set()

        # State tracking for change detection
        self._last_mel_snapshot: Optional[MELSnapshot] = None
        self._last_spot: Optional[float] = None
        self._tracked_levels: Dict[str, float] = {}

        # Callbacks
        self._on_trigger: Optional[Callable[[CommentaryTrigger], None]] = None

    def set_callback(self, callback: Callable[[CommentaryTrigger], None]) -> None:
        """Set callback for when triggers are detected."""
        self._on_trigger = callback

    def suppress_trigger_type(self, trigger_type: TriggerType) -> None:
        """Temporarily suppress a trigger type."""
        self._suppressed_types.add(trigger_type)

    def unsuppress_trigger_type(self, trigger_type: TriggerType) -> None:
        """Remove suppression for a trigger type."""
        self._suppressed_types.discard(trigger_type)

    def set_tracked_levels(self, levels: Dict[str, float]) -> None:
        """
        Set levels to track for crossing detection.

        Args:
            levels: Dict mapping level name to price (e.g., {"zero_gamma": 6045.0})
        """
        self._tracked_levels = levels

    def process_mel_snapshot(self, snapshot: MELSnapshot) -> List[CommentaryTrigger]:
        """
        Process a MEL snapshot and detect any triggers.

        Returns list of triggers detected.
        """
        triggers = []

        if self._last_mel_snapshot is None:
            self._last_mel_snapshot = snapshot
            return triggers

        last = self._last_mel_snapshot

        # Check for model state changes
        models = [
            ("gamma", snapshot.gamma, last.gamma),
            ("volume_profile", snapshot.volume_profile, last.volume_profile),
            ("liquidity", snapshot.liquidity, last.liquidity),
            ("volatility", snapshot.volatility, last.volatility),
            ("session", snapshot.session_structure, last.session_structure),
        ]

        for name, current, previous in models:
            if current.state != previous.state:
                trigger = MELStateChangeTrigger(
                    model=name,
                    from_state=previous.state.value,
                    to_state=current.state.value,
                    score=current.effectiveness,
                )
                if self._should_emit(trigger):
                    triggers.append(trigger)

        # Check for global integrity warning
        if snapshot.global_structure_integrity < 50:
            if last.global_structure_integrity >= 50:
                # Just crossed below threshold
                trigger = GlobalIntegrityWarningTrigger(
                    score=snapshot.global_structure_integrity,
                )
                if self._should_emit(trigger):
                    triggers.append(trigger)

        # Check for coherence state change
        if snapshot.coherence_state != last.coherence_state:
            trigger = CoherenceChangeTrigger(
                from_state=last.coherence_state.value,
                to_state=snapshot.coherence_state.value,
            )
            if self._should_emit(trigger):
                triggers.append(trigger)

        self._last_mel_snapshot = snapshot

        # Emit triggers
        for trigger in triggers:
            self._emit(trigger)

        return triggers

    def process_spot_update(self, spot: float) -> List[CommentaryTrigger]:
        """
        Process a spot price update and detect level crossings.

        Returns list of triggers detected.
        """
        triggers = []

        if self._last_spot is None:
            self._last_spot = spot
            return triggers

        last_spot = self._last_spot

        # Check each tracked level
        for level_name, level_price in self._tracked_levels.items():
            # Did we cross this level?
            crossed_up = last_spot < level_price <= spot
            crossed_down = last_spot > level_price >= spot

            if crossed_up or crossed_down:
                trigger = SpotCrossedLevelTrigger(
                    level_type=level_name,
                    level=level_price,
                    direction="above" if crossed_up else "below",
                    spot=spot,
                )
                if self._should_emit(trigger):
                    triggers.append(trigger)

        self._last_spot = spot

        for trigger in triggers:
            self._emit(trigger)

        return triggers

    def process_tile_selection(self, tile_data: Dict[str, Any]) -> Optional[CommentaryTrigger]:
        """Process a tile selection event."""
        trigger = TileSelectedTrigger(tile_data)

        if self._should_emit(trigger):
            self._emit(trigger)
            return trigger

        return None

    def process_trade_event(
        self,
        event_type: str,
        trade_data: Dict[str, Any],
    ) -> Optional[CommentaryTrigger]:
        """Process a trade open/close event."""
        trigger = TradeEventTrigger(event_type, trade_data)

        if self._should_emit(trigger):
            self._emit(trigger)
            return trigger

        return None

    def _should_emit(self, trigger: CommentaryTrigger) -> bool:
        """Check if trigger should be emitted (not suppressed or debounced)."""
        # Check if type is suppressed
        if trigger.type in self._suppressed_types:
            return False

        # Check debounce
        key = f"{trigger.type.value}:{hash(str(trigger.data))}"
        last_time = self._last_trigger_time.get(key)

        if last_time:
            elapsed = (trigger.timestamp - last_time).total_seconds()
            if elapsed < self.debounce_seconds:
                self.logger.debug(f"Debounced trigger: {trigger.type.value}")
                return False

        self._last_trigger_time[key] = trigger.timestamp
        return True

    def _emit(self, trigger: CommentaryTrigger) -> None:
        """Emit a trigger."""
        self._queue.append(trigger)

        if self._on_trigger:
            try:
                self._on_trigger(trigger)
            except Exception as e:
                self.logger.error(f"Trigger callback error: {e}")

    def get_pending_triggers(self) -> List[CommentaryTrigger]:
        """Get all pending triggers, sorted by priority (highest first)."""
        triggers = list(self._queue)
        self._queue.clear()
        return sorted(triggers, key=lambda t: t.priority, reverse=True)

    def get_highest_priority_trigger(self) -> Optional[CommentaryTrigger]:
        """Get the highest priority pending trigger."""
        if not self._queue:
            return None

        # Find highest priority
        highest = max(self._queue, key=lambda t: t.priority)
        self._queue.remove(highest)
        return highest


class PeriodicTriggerScheduler:
    """
    Schedules periodic commentary triggers.

    Used for time-based observations like session phase changes.
    """

    def __init__(
        self,
        detector: TriggerDetector,
        interval_seconds: float = 300.0,  # 5 minutes
        logger: Optional[logging.Logger] = None,
    ):
        self.detector = detector
        self.interval_seconds = interval_seconds
        self.logger = logger or logging.getLogger("PeriodicTrigger")

        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start periodic trigger scheduling."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._schedule_loop())
        self.logger.info(f"Periodic triggers started (interval: {self.interval_seconds}s)")

    async def stop(self) -> None:
        """Stop periodic trigger scheduling."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _schedule_loop(self) -> None:
        """Main scheduling loop."""
        while self._running:
            try:
                await asyncio.sleep(self.interval_seconds)

                if self._running:
                    trigger = CommentaryTrigger(
                        type=TriggerType.PERIODIC,
                        timestamp=datetime.utcnow(),
                        data={"interval": self.interval_seconds},
                        priority=2,
                    )
                    self.detector._emit(trigger)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Periodic trigger error: {e}")
