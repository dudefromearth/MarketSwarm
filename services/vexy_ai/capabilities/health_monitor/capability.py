"""
Health Monitor Capability - Service health tracking for MarketSwarm.

Monitors heartbeats from all services via system-redis:
- Tracks consecutive failures
- Publishes ServiceUnhealthy events
- Provides API routes for status queries
"""

from datetime import datetime, UTC
from typing import Callable, List, Optional

from fastapi import APIRouter

from ...core.capability import BaseCapability
from .service import HealthMonitorService
from .models import (
    HealthMonitorStatusResponse,
    ServicesHealthResponse,
    ServiceHistoryResponse,
    ServiceStatus,
)


class HealthMonitorCapability(BaseCapability):
    """
    Service health monitoring capability.

    Provides:
    - Background task for heartbeat monitoring
    - GET /api/vexy/health-monitor/status - Overall status
    - GET /api/vexy/health-monitor/services - All services health
    - GET /api/vexy/health-monitor/history/{service} - Service history
    """

    name = "health_monitor"
    version = "1.0.0"
    dependencies = []
    buses_required = ["system"]

    def __init__(self, vexy):
        super().__init__(vexy)
        self.service: Optional[HealthMonitorService] = None

    async def start(self) -> None:
        """Initialize Health Monitor service."""
        buses = self.vexy.buses if hasattr(self.vexy, 'buses') else None
        self.service = HealthMonitorService(
            self.config,
            self.logger,
            buses,
            event_publisher=self.vexy.publish,
        )
        self.logger.info("Health Monitor capability started", emoji="🏥")

    async def stop(self) -> None:
        """Stop Health Monitor service."""
        if self.service:
            self.service.stop()
        self.service = None
        self.logger.info("Health Monitor capability stopped", emoji="🏥")

    def get_routes(self) -> APIRouter:
        """Return FastAPI router with Health Monitor endpoints."""
        router = APIRouter(prefix="/api/vexy/health-monitor", tags=["HealthMonitor"])

        @router.get("/status", response_model=HealthMonitorStatusResponse)
        async def get_status():
            """Get overall health monitor status."""
            status = self.service.get_status()
            return HealthMonitorStatusResponse(**status)

        @router.get("/services", response_model=ServicesHealthResponse)
        async def get_services():
            """Get health status of all monitored services."""
            services = self.service.get_all_services()
            return ServicesHealthResponse(
                services=services,
                checked_at=datetime.now(UTC).isoformat(),
            )

        @router.get("/history/{service_name}", response_model=ServiceHistoryResponse)
        async def get_history(service_name: str):
            """Get health event history for a specific service."""
            history = self.service.get_service_history(service_name)

            # Get current status
            services = self.service.get_all_services()
            current = next(
                (s for s in services if s.name == service_name),
                None
            )
            current_status = current.status if current else ServiceStatus.UNKNOWN

            return ServiceHistoryResponse(
                service=service_name,
                current_status=current_status,
                events=history,
            )

        return router

    def get_background_tasks(self) -> List[Callable]:
        """Return background tasks to run."""
        return [self._run_monitor_loop]

    async def _run_monitor_loop(self) -> None:
        """Background task wrapper for the monitoring loop."""
        if self.service:
            await self.service.run_loop()
