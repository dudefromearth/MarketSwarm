"""
Healer Service - Orchestrates self-healing for MarketSwarm services.

Subscribes to ServiceUnhealthy events and executes healing protocols.
"""

import asyncio
import time
from collections import defaultdict
from datetime import datetime, UTC
from typing import Any, Callable, Dict, List, Optional

from .models import (
    HealingStrategy,
    HealingStatus,
    HealingProtocol,
    HealingAttempt,
)
from .strategies import get_strategy


# Default protocols for known services
DEFAULT_PROTOCOLS: Dict[str, HealingProtocol] = {
    "trading_engine": HealingProtocol(
        service_name="trading_engine",
        strategies=[HealingStrategy.WAIT, HealingStrategy.RESTART, HealingStrategy.ESCALATE],
        max_attempts=3,
        cooldown_sec=30,
        escalate_after=2,
    ),
    "data_feed": HealingProtocol(
        service_name="data_feed",
        strategies=[HealingStrategy.RESTART, HealingStrategy.FAILOVER, HealingStrategy.ESCALATE],
        max_attempts=3,
        cooldown_sec=15,
        escalate_after=2,
    ),
    "alert_service": HealingProtocol(
        service_name="alert_service",
        strategies=[HealingStrategy.RESTART, HealingStrategy.ESCALATE],
        max_attempts=2,
        cooldown_sec=30,
        escalate_after=1,
    ),
    "journal_service": HealingProtocol(
        service_name="journal_service",
        strategies=[HealingStrategy.WAIT, HealingStrategy.RESTART],
        max_attempts=3,
        cooldown_sec=60,
        escalate_after=3,
    ),
    "market_data": HealingProtocol(
        service_name="market_data",
        strategies=[HealingStrategy.RESTART, HealingStrategy.FAILOVER, HealingStrategy.ESCALATE],
        max_attempts=3,
        cooldown_sec=10,
        escalate_after=2,
    ),
}

# Default protocol for unknown services
FALLBACK_PROTOCOL = HealingProtocol(
    service_name="unknown",
    strategies=[HealingStrategy.WAIT, HealingStrategy.RESTART, HealingStrategy.ESCALATE],
    max_attempts=3,
    cooldown_sec=60,
    escalate_after=2,
)


class HealerService:
    """
    Orchestrates healing attempts for unhealthy services.

    Tracks:
    - Active healing attempts
    - Attempt history per service
    - Cooldowns to prevent healing storms
    """

    def __init__(
        self,
        config: Dict[str, Any],
        logger: Any,
        event_publisher: Optional[Callable] = None,
    ):
        self.config = config
        self.logger = logger
        self.event_publisher = event_publisher

        # State tracking
        self._active_healings: Dict[str, HealingAttempt] = {}
        self._attempt_history: Dict[str, List[HealingAttempt]] = defaultdict(list)
        self._last_attempt_time: Dict[str, float] = {}
        self._attempt_counts: Dict[str, int] = defaultdict(int)

        # Stats
        self.total_attempts = 0
        self.successful_healings = 0
        self.failed_healings = 0

        # Control
        self.running = False

    def get_protocol(self, service_name: str) -> HealingProtocol:
        """Get healing protocol for a service."""
        # Check config first
        config_protocols = self.config.get("healer", {}).get("protocols", {})
        if service_name in config_protocols:
            return HealingProtocol(**config_protocols[service_name])

        # Check defaults
        if service_name in DEFAULT_PROTOCOLS:
            return DEFAULT_PROTOCOLS[service_name]

        # Use fallback
        protocol = FALLBACK_PROTOCOL.model_copy()
        protocol.service_name = service_name
        return protocol

    def get_all_protocols(self) -> List[HealingProtocol]:
        """Get all configured protocols."""
        # Merge config and defaults
        protocols = dict(DEFAULT_PROTOCOLS)

        config_protocols = self.config.get("healer", {}).get("protocols", {})
        for name, data in config_protocols.items():
            protocols[name] = HealingProtocol(**data)

        return list(protocols.values())

    async def handle_unhealthy_service(
        self,
        service_name: str,
        consecutive_failures: int,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Handle a ServiceUnhealthy event.

        Checks cooldowns, selects strategy, and executes healing.
        """
        # Skip if already healing this service
        if service_name in self._active_healings:
            self.logger.debug(f"Already healing {service_name}, skipping")
            return

        # Check cooldown
        protocol = self.get_protocol(service_name)
        last_attempt = self._last_attempt_time.get(service_name, 0)
        now = time.time()

        if now - last_attempt < protocol.cooldown_sec:
            remaining = protocol.cooldown_sec - (now - last_attempt)
            self.logger.debug(f"Cooldown active for {service_name}, {remaining:.0f}s remaining")
            return

        # Check max attempts
        attempt_count = self._attempt_counts[service_name]
        if attempt_count >= protocol.max_attempts:
            self.logger.warn(
                f"Max attempts ({protocol.max_attempts}) reached for {service_name}",
                emoji="⚠️"
            )
            # Force escalation
            await self._execute_strategy(
                service_name,
                HealingStrategy.ESCALATE,
                attempt_count + 1,
                context,
            )
            return

        # Select strategy based on attempt count
        strategy_idx = min(attempt_count, len(protocol.strategies) - 1)
        strategy = protocol.strategies[strategy_idx]

        # Check if we should escalate early
        if attempt_count >= protocol.escalate_after and strategy != HealingStrategy.ESCALATE:
            strategy = HealingStrategy.ESCALATE

        # Execute healing
        await self._execute_strategy(
            service_name,
            strategy,
            attempt_count + 1,
            context,
        )

    async def _execute_strategy(
        self,
        service_name: str,
        strategy_type: HealingStrategy,
        attempt_number: int,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Execute a healing strategy."""
        self.logger.info(
            f"Healing {service_name}: {strategy_type.value} (attempt {attempt_number})",
            emoji="🏥"
        )

        # Create attempt record
        attempt = HealingAttempt(
            service_name=service_name,
            strategy=strategy_type,
            attempt_number=attempt_number,
            started_at=datetime.now(UTC).isoformat(),
            status=HealingStatus.IN_PROGRESS,
        )

        self._active_healings[service_name] = attempt
        self._last_attempt_time[service_name] = time.time()
        self.total_attempts += 1

        # Publish HealingInitiated event
        await self._publish_initiated(service_name, strategy_type, attempt_number)

        try:
            # Get and execute strategy
            strategy = get_strategy(strategy_type, self.config, self.logger)
            success = await strategy.execute(service_name, context)

            # Update attempt record
            attempt.completed_at = datetime.now(UTC).isoformat()
            attempt.status = HealingStatus.SUCCESS if success else HealingStatus.FAILED

            if success:
                self.successful_healings += 1
                self._attempt_counts[service_name] = 0  # Reset on success
            else:
                self.failed_healings += 1
                self._attempt_counts[service_name] = attempt_number

            # Publish HealingCompleted event
            await self._publish_completed(service_name, strategy_type, success, attempt)

        except Exception as e:
            attempt.completed_at = datetime.now(UTC).isoformat()
            attempt.status = HealingStatus.FAILED
            attempt.error = str(e)
            self.failed_healings += 1
            self._attempt_counts[service_name] = attempt_number

            self.logger.error(f"Healing failed for {service_name}: {e}", emoji="❌")

            await self._publish_completed(service_name, strategy_type, False, attempt, error=str(e))

        finally:
            # Store in history
            self._attempt_history[service_name].append(attempt)

            # Keep history bounded
            if len(self._attempt_history[service_name]) > 100:
                self._attempt_history[service_name] = self._attempt_history[service_name][-50:]

            # Remove from active
            self._active_healings.pop(service_name, None)

    async def _publish_initiated(
        self,
        service_name: str,
        strategy: HealingStrategy,
        attempt: int,
    ) -> None:
        """Publish HealingInitiated event."""
        if self.event_publisher:
            from ...core.events import HealingInitiated
            await self.event_publisher(HealingInitiated(
                service_name=service_name,
                action=strategy.value,
                attempt=attempt,
                protocol=self.get_protocol(service_name).service_name,
            ))

    async def _publish_completed(
        self,
        service_name: str,
        strategy: HealingStrategy,
        success: bool,
        attempt: HealingAttempt,
        error: Optional[str] = None,
    ) -> None:
        """Publish HealingCompleted event."""
        if self.event_publisher:
            from ...core.events import HealingCompleted

            # Calculate duration
            started = datetime.fromisoformat(attempt.started_at)
            completed = datetime.fromisoformat(attempt.completed_at) if attempt.completed_at else datetime.now(UTC)
            duration = (completed - started).total_seconds()

            await self.event_publisher(HealingCompleted(
                service_name=service_name,
                action=strategy.value,
                success=success,
                duration_seconds=duration,
                error=error,
            ))

    def get_status(self) -> Dict[str, Any]:
        """Get current healer status."""
        return {
            "running": self.running,
            "active_healings": len(self._active_healings),
            "total_attempts": self.total_attempts,
            "successful_healings": self.successful_healings,
            "failed_healings": self.failed_healings,
        }

    def get_history(self, service_name: str) -> List[HealingAttempt]:
        """Get healing history for a service."""
        return self._attempt_history.get(service_name, [])

    def start(self) -> None:
        """Mark healer as running."""
        self.running = True

    def stop(self) -> None:
        """Mark healer as stopped."""
        self.running = False
