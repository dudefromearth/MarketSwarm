"""
Health Monitor Service - Business logic for service health tracking.

Monitors heartbeats from all MarketSwarm services via system-redis.
Tracks consecutive failures and publishes ServiceUnhealthy events.
"""

import asyncio
import json
import time
from collections import defaultdict
from datetime import datetime, UTC
from typing import Any, Callable, Dict, List, Optional, Set

from .models import ServiceStatus, ServiceHealth, HealthEvent


class HealthMonitorService:
    """
    Service health monitoring via Redis heartbeats.

    Runs a background loop that:
    - Scans for *:heartbeat keys on system-redis
    - Tracks which services are alive vs dead
    - Counts consecutive failures
    - Publishes events on state changes
    """

    # Known MarketSwarm services to monitor
    KNOWN_SERVICES = [
        "vexy_ai",
        "trading_engine",
        "data_feed",
        "alert_service",
        "journal_service",
        "market_data",
        "healer",
    ]

    # Thresholds
    DEGRADED_THRESHOLD = 1  # 1 missed heartbeat = degraded
    UNHEALTHY_THRESHOLD = 3  # 3 consecutive misses = unhealthy

    def __init__(
        self,
        config: Dict[str, Any],
        logger: Any,
        buses: Any = None,
        event_publisher: Optional[Callable] = None,
    ):
        self.config = config
        self.logger = logger
        self.buses = buses
        self.event_publisher = event_publisher

        # State tracking
        self._service_states: Dict[str, ServiceHealth] = {}
        self._consecutive_failures: Dict[str, int] = defaultdict(int)
        self._history: Dict[str, List[HealthEvent]] = defaultdict(list)

        # Control
        self.running = False
        self.last_check: Optional[datetime] = None

    def _get_redis_client(self):
        """Get Redis client for system bus."""
        if self.buses and hasattr(self.buses, 'system'):
            return self.buses.system

        # Fallback to direct connection
        import redis
        buses = self.config.get("buses", {}) or {}
        system_url = buses.get("system-redis", {}).get("url", "redis://127.0.0.1:6379")
        return redis.Redis.from_url(system_url, decode_responses=True)

    async def run_loop(self) -> None:
        """
        Main monitoring loop.

        Checks heartbeats periodically and updates service states.
        """
        self.running = True
        self.logger.info("Health monitor loop starting", emoji="🏥")

        check_interval = float(self.config.get("health_monitor", {}).get(
            "check_interval_sec", 10
        ))

        try:
            while self.running:
                try:
                    await self._check_all_services()
                except Exception as e:
                    self.logger.error(f"Health check error: {e}", emoji="❌")

                await asyncio.sleep(check_interval)

        except asyncio.CancelledError:
            self.logger.info("Health monitor loop cancelled", emoji="🛑")
            raise
        finally:
            self.running = False
            self.logger.info("Health monitor loop stopped", emoji="✓")

    async def _check_all_services(self) -> None:
        """Check health of all known services."""
        r = self._get_redis_client()
        self.last_check = datetime.now(UTC)

        # Track which services we found
        found_services: Set[str] = set()

        # Check known services directly (more reliable than scanning)
        for service_name in self.KNOWN_SERVICES:
            key = f"{service_name}:heartbeat"
            try:
                # Handle both sync and async Redis
                if hasattr(r, '__aenter__'):  # Async Redis
                    data = await r.get(key)
                    ttl = await r.ttl(key)
                else:  # Sync Redis
                    data = r.get(key)
                    ttl = r.ttl(key)

                if data:
                    found_services.add(service_name)
                    payload = json.loads(data) if isinstance(data, str) else json.loads(data.decode('utf-8'))
                    await self._update_service_health(
                        service_name,
                        ServiceStatus.HEALTHY,
                        payload=payload,
                        ttl_remaining=ttl if ttl > 0 else None,
                    )
                else:
                    # No heartbeat data - service may be down
                    await self._increment_failure(service_name)

            except Exception as e:
                self.logger.debug(f"Error reading heartbeat for {service_name}: {e}")
                await self._increment_failure(service_name)

    async def _update_service_health(
        self,
        service_name: str,
        status: ServiceStatus,
        payload: Optional[Dict[str, Any]] = None,
        ttl_remaining: Optional[int] = None,
    ) -> None:
        """Update health state for a service."""
        previous_state = self._service_states.get(service_name)
        previous_status = previous_state.status if previous_state else ServiceStatus.UNKNOWN

        # Reset failure counter on healthy
        if status == ServiceStatus.HEALTHY:
            self._consecutive_failures[service_name] = 0

        # Create new state
        new_state = ServiceHealth(
            name=service_name,
            status=status,
            last_heartbeat=datetime.now(UTC).isoformat(),
            consecutive_failures=self._consecutive_failures[service_name],
            payload=payload,
            ttl_remaining=ttl_remaining,
        )
        self._service_states[service_name] = new_state

        # Publish event on status change
        if previous_status != status:
            event = HealthEvent(
                service=service_name,
                previous_status=previous_status,
                new_status=status,
                timestamp=datetime.now(UTC).isoformat(),
                reason=f"Consecutive failures: {self._consecutive_failures[service_name]}"
                if status != ServiceStatus.HEALTHY else "Heartbeat received",
            )
            self._history[service_name].append(event)

            # Keep history bounded
            if len(self._history[service_name]) > 100:
                self._history[service_name] = self._history[service_name][-50:]

            # Log and publish
            if status == ServiceStatus.UNHEALTHY:
                self.logger.warn(
                    f"Service unhealthy: {service_name}",
                    emoji="🔴"
                )
                await self._publish_unhealthy_event(service_name, event)
            elif status == ServiceStatus.HEALTHY and previous_status == ServiceStatus.UNHEALTHY:
                self.logger.info(
                    f"Service recovered: {service_name}",
                    emoji="🟢"
                )

    async def _increment_failure(self, service_name: str) -> None:
        """Increment failure count and update status accordingly."""
        self._consecutive_failures[service_name] += 1
        failures = self._consecutive_failures[service_name]

        if failures >= self.UNHEALTHY_THRESHOLD:
            status = ServiceStatus.UNHEALTHY
        elif failures >= self.DEGRADED_THRESHOLD:
            status = ServiceStatus.DEGRADED
        else:
            status = ServiceStatus.UNKNOWN

        await self._update_service_health(service_name, status)

    async def _publish_unhealthy_event(
        self,
        service_name: str,
        event: HealthEvent,
    ) -> None:
        """Publish ServiceUnhealthy domain event."""
        if self.event_publisher:
            from ...core.events import ServiceUnhealthy
            state = self._service_states.get(service_name)
            await self.event_publisher(ServiceUnhealthy(
                service_name=service_name,
                status=event.new_status.value,
                consecutive_failures=self._consecutive_failures[service_name],
                details={
                    "last_heartbeat": state.last_heartbeat if state else None,
                    "reason": event.reason,
                },
            ))

    def stop(self) -> None:
        """Signal the loop to stop."""
        self.running = False

    def get_status(self) -> Dict[str, Any]:
        """Get overall health monitor status."""
        healthy = sum(
            1 for s in self._service_states.values()
            if s.status == ServiceStatus.HEALTHY
        )
        unhealthy = sum(
            1 for s in self._service_states.values()
            if s.status == ServiceStatus.UNHEALTHY
        )

        return {
            "running": self.running,
            "services_monitored": len(self._service_states),
            "healthy_count": healthy,
            "unhealthy_count": unhealthy,
            "last_check": self.last_check.isoformat() if self.last_check else None,
        }

    def get_all_services(self) -> List[ServiceHealth]:
        """Get health status of all tracked services."""
        return list(self._service_states.values())

    def get_service_history(self, service_name: str) -> List[HealthEvent]:
        """Get health event history for a service."""
        return self._history.get(service_name, [])
