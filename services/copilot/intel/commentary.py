"""
Commentary Orchestrator - One-way AI market commentary.

Coordinates trigger detection, AI generation, and message delivery.
The AI observes and comments, users do not interact.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from collections import deque

from .commentary_models import (
    CommentaryMessage,
    CommentaryTrigger,
    CommentaryConfig,
    CommentaryCategory,
    TriggerType,
)
from .commentary_triggers import TriggerDetector, PeriodicTriggerScheduler
from .commentary_prompts import (
    SYSTEM_PROMPT,
    FOTW_CONTEXT,
    build_full_prompt,
    get_category_for_trigger,
)
from .mel_models import MELSnapshot
from .ai_providers import AIProviderManager, AIProviderConfig


class CommentaryOrchestrator:
    """
    Orchestrates AI commentary generation.

    Responsibilities:
    - Listen for triggers from TriggerDetector
    - Generate commentary via AI provider
    - Rate limit and queue management
    - Deliver messages to subscribers
    """

    def __init__(
        self,
        config: CommentaryConfig,
        ai_manager: AIProviderManager,
        logger: Optional[logging.Logger] = None,
    ):
        self.config = config
        self.ai_manager = ai_manager
        self.logger = logger or logging.getLogger("CommentaryOrchestrator")

        # Trigger detection
        self.trigger_detector = TriggerDetector(
            debounce_seconds=config.debounce_seconds,
            max_queue_size=config.max_queue_size,
            logger=self.logger,
        )
        self.trigger_detector.set_callback(self._on_trigger)

        # Periodic triggers (optional)
        self._periodic_scheduler: Optional[PeriodicTriggerScheduler] = None

        # Message history
        self._messages: deque[CommentaryMessage] = deque(maxlen=100)

        # Rate limiting
        self._last_generation_time: Optional[datetime] = None
        self._generation_count_minute = 0
        self._minute_start: Optional[datetime] = None

        # Processing queue
        self._pending_triggers: asyncio.Queue[CommentaryTrigger] = asyncio.Queue()
        self._processing_task: Optional[asyncio.Task] = None

        # Current MEL state
        self._current_mel: Optional[MELSnapshot] = None

        # Subscribers
        self._subscribers: List[Callable[[CommentaryMessage], None]] = []

        # State
        self._running = False

    async def start(self) -> None:
        """Start the commentary service."""
        if self._running:
            return

        self._running = True

        # Start processing loop
        self._processing_task = asyncio.create_task(self._process_loop())

        self.logger.info("Commentary orchestrator started")

    async def stop(self) -> None:
        """Stop the commentary service."""
        self._running = False

        if self._periodic_scheduler:
            await self._periodic_scheduler.stop()

        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass

        self.logger.info("Commentary orchestrator stopped")

    def enable_periodic_commentary(self, interval_seconds: float = 300.0) -> None:
        """Enable periodic commentary generation."""
        self._periodic_scheduler = PeriodicTriggerScheduler(
            detector=self.trigger_detector,
            interval_seconds=interval_seconds,
            logger=self.logger,
        )

    async def start_periodic(self) -> None:
        """Start periodic commentary if enabled."""
        if self._periodic_scheduler:
            await self._periodic_scheduler.start()

    def subscribe(self, callback: Callable[[CommentaryMessage], None]) -> None:
        """Subscribe to commentary messages."""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[CommentaryMessage], None]) -> None:
        """Unsubscribe from commentary messages."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def update_mel_snapshot(self, snapshot: MELSnapshot) -> None:
        """
        Update current MEL snapshot and check for triggers.

        This should be called whenever MEL state changes.
        """
        # Detect triggers from MEL changes
        self.trigger_detector.process_mel_snapshot(snapshot)

        # Store current snapshot for context
        self._current_mel = snapshot

    def update_spot(self, spot: float) -> None:
        """Update spot price and check for level crossings."""
        self.trigger_detector.process_spot_update(spot)

    def set_tracked_levels(self, levels: Dict[str, float]) -> None:
        """Set levels to track for crossing detection."""
        self.trigger_detector.set_tracked_levels(levels)

    def on_tile_selected(self, tile_data: Dict[str, Any]) -> None:
        """Handle tile selection event."""
        self.trigger_detector.process_tile_selection(tile_data)

    def on_trade_opened(self, trade_data: Dict[str, Any]) -> None:
        """Handle trade opened event."""
        self.trigger_detector.process_trade_event("opened", trade_data)

    def on_trade_closed(self, trade_data: Dict[str, Any]) -> None:
        """Handle trade closed event."""
        self.trigger_detector.process_trade_event("closed", trade_data)

    def get_recent_messages(self, limit: int = 20) -> List[CommentaryMessage]:
        """Get recent commentary messages."""
        messages = list(self._messages)
        return messages[-limit:] if len(messages) > limit else messages

    def get_message_count(self) -> int:
        """Get total message count in history."""
        return len(self._messages)

    # ========== Internal Methods ==========

    def _on_trigger(self, trigger: CommentaryTrigger) -> None:
        """Callback when trigger is detected."""
        if not self.config.enabled:
            return

        # Add to processing queue
        try:
            self._pending_triggers.put_nowait(trigger)
        except asyncio.QueueFull:
            self.logger.warning("Trigger queue full, dropping trigger")

    async def _process_loop(self) -> None:
        """Main processing loop for commentary generation."""
        while self._running:
            try:
                # Wait for trigger with timeout
                try:
                    trigger = await asyncio.wait_for(
                        self._pending_triggers.get(),
                        timeout=1.0,
                    )
                except asyncio.TimeoutError:
                    continue

                # Check rate limits
                if not self._can_generate():
                    self.logger.debug("Rate limited, skipping generation")
                    continue

                # Generate commentary
                message = await self._generate_commentary(trigger)

                if message:
                    self._messages.append(message)
                    self._notify_subscribers(message)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Processing error: {e}")

    def _can_generate(self) -> bool:
        """Check if we can generate (rate limiting)."""
        now = datetime.utcnow()

        # Check minimum interval
        if self._last_generation_time:
            elapsed = (now - self._last_generation_time).total_seconds()
            if elapsed < self.config.min_interval_seconds:
                return False

        # Check per-minute rate limit
        if self._minute_start is None or (now - self._minute_start).total_seconds() >= 60:
            self._minute_start = now
            self._generation_count_minute = 0

        if self._generation_count_minute >= self.config.rate_limit_per_minute:
            return False

        return True

    async def _generate_commentary(
        self,
        trigger: CommentaryTrigger,
    ) -> Optional[CommentaryMessage]:
        """Generate commentary for a trigger."""
        try:
            # Build prompt
            prompt = build_full_prompt(
                trigger_type=trigger.type,
                trigger_data=trigger.data,
                mel_snapshot=self._current_mel,
            )

            # Build system prompt with FOTW context
            system = f"{SYSTEM_PROMPT}\n\n{FOTW_CONTEXT}"

            # Generate via AI
            messages = [{"role": "user", "content": prompt}]

            response = await self.ai_manager.generate(
                messages=messages,
                system_prompt=system,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
            )

            if not response.content:
                self.logger.warning("Empty response from AI provider")
                return None

            # Update rate limiting
            self._last_generation_time = datetime.utcnow()
            self._generation_count_minute += 1

            # Create message
            category = get_category_for_trigger(trigger.type)

            message = CommentaryMessage.create(
                category=category,
                text=response.content,
                trigger=trigger,
                mel_context=self._current_mel.to_dict() if self._current_mel else None,
                provider=response.provider,
                model=response.model,
                tokens_used=response.tokens_used,
            )

            self.logger.debug(f"Generated commentary: {message.id}")
            return message

        except Exception as e:
            self.logger.error(f"Generation error: {e}")
            return None

    def _notify_subscribers(self, message: CommentaryMessage) -> None:
        """Notify all subscribers of new message."""
        for callback in self._subscribers:
            try:
                callback(message)
            except Exception as e:
                self.logger.error(f"Subscriber callback error: {e}")


class CommentaryService:
    """
    High-level commentary service combining orchestration with MEL integration.

    This is the main entry point for the commentary system.
    """

    def __init__(
        self,
        config: CommentaryConfig,
        ai_config: AIProviderConfig,
        logger: Optional[logging.Logger] = None,
    ):
        self.config = config
        self.logger = logger or logging.getLogger("CommentaryService")

        # AI provider
        self.ai_manager = AIProviderManager(ai_config, logger=self.logger)

        # Orchestrator
        self.orchestrator = CommentaryOrchestrator(
            config=config,
            ai_manager=self.ai_manager,
            logger=self.logger,
        )

    async def start(self) -> None:
        """Start commentary service."""
        await self.orchestrator.start()
        self.logger.info("Commentary service started")

    async def stop(self) -> None:
        """Stop commentary service."""
        await self.orchestrator.stop()
        self.logger.info("Commentary service stopped")

    def subscribe(self, callback: Callable[[CommentaryMessage], None]) -> None:
        """Subscribe to commentary messages."""
        self.orchestrator.subscribe(callback)

    def unsubscribe(self, callback: Callable[[CommentaryMessage], None]) -> None:
        """Unsubscribe from commentary messages."""
        self.orchestrator.unsubscribe(callback)

    def update_mel(self, snapshot: MELSnapshot) -> None:
        """Update MEL snapshot."""
        self.orchestrator.update_mel_snapshot(snapshot)

    def update_spot(self, spot: float) -> None:
        """Update spot price."""
        self.orchestrator.update_spot(spot)

    def set_levels(self, levels: Dict[str, float]) -> None:
        """Set tracked levels."""
        self.orchestrator.set_tracked_levels(levels)

    def on_tile_selected(self, tile_data: Dict[str, Any]) -> None:
        """Handle tile selection."""
        self.orchestrator.on_tile_selected(tile_data)

    def on_trade_event(self, event_type: str, trade_data: Dict[str, Any]) -> None:
        """Handle trade event."""
        if event_type == "opened":
            self.orchestrator.on_trade_opened(trade_data)
        elif event_type == "closed":
            self.orchestrator.on_trade_closed(trade_data)

    def get_messages(self, limit: int = 20) -> List[CommentaryMessage]:
        """Get recent messages."""
        return self.orchestrator.get_recent_messages(limit)

    @property
    def enabled(self) -> bool:
        """Check if commentary is enabled."""
        return self.config.enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Enable/disable commentary."""
        self.config.enabled = value
