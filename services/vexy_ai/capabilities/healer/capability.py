"""
Healer Capability - Self-healing for MarketSwarm services.

Subscribes to ServiceUnhealthy events and executes healing protocols:
- Restart: Request service restart via system bus
- Failover: Switch to backup instance
- Escalate: Alert human operators
- Wait: Wait for natural recovery
"""

from typing import Callable, Dict, List, Optional, Type

from fastapi import APIRouter

from ...core.capability import BaseCapability
from ...core.events import DomainEvent, ServiceUnhealthy
from .service import HealerService
from .models import (
    HealerStatusResponse,
    HealingHistoryResponse,
    ProtocolsResponse,
)


class HealerCapability(BaseCapability):
    """
    Self-healing capability for MarketSwarm.

    Provides:
    - Event subscription to ServiceUnhealthy
    - Healing strategy execution
    - GET /api/vexy/healer/status - Healer status
    - GET /api/vexy/healer/protocols - Configured protocols
    - GET /api/vexy/healer/history/{service} - Healing history
    """

    name = "healer"
    version = "1.0.0"
    dependencies = ["health_monitor"]  # Depends on health monitor for events
    buses_required = ["system"]

    def __init__(self, vexy):
        super().__init__(vexy)
        self.service: Optional[HealerService] = None

    async def start(self) -> None:
        """Initialize Healer service."""
        self.service = HealerService(
            self.config,
            self.logger,
            event_publisher=self.vexy.publish,
        )
        self.service.start()
        self.logger.info("Healer capability started", emoji="🏥")

    async def stop(self) -> None:
        """Stop Healer service."""
        if self.service:
            self.service.stop()
        self.service = None
        self.logger.info("Healer capability stopped", emoji="🏥")

    def get_routes(self) -> APIRouter:
        """Return FastAPI router with Healer endpoints."""
        router = APIRouter(prefix="/api/vexy/healer", tags=["Healer"])

        @router.get("/status", response_model=HealerStatusResponse)
        async def get_status():
            """Get current healer status."""
            status = self.service.get_status()
            return HealerStatusResponse(**status)

        @router.get("/protocols", response_model=ProtocolsResponse)
        async def get_protocols():
            """Get all configured healing protocols."""
            protocols = self.service.get_all_protocols()
            return ProtocolsResponse(protocols=protocols)

        @router.get("/history/{service_name}", response_model=HealingHistoryResponse)
        async def get_history(service_name: str):
            """Get healing history for a specific service."""
            history = self.service.get_history(service_name)
            return HealingHistoryResponse(
                service=service_name,
                attempts=history,
            )

        return router

    def get_event_subscriptions(self) -> Dict[Type[DomainEvent], Callable]:
        """Subscribe to ServiceUnhealthy events."""
        return {
            ServiceUnhealthy: self._handle_unhealthy,
        }

    async def _handle_unhealthy(self, event: ServiceUnhealthy) -> None:
        """Handle ServiceUnhealthy event."""
        if not self.service or not self.service.running:
            return

        # Don't heal ourselves
        if event.service_name == "vexy_ai":
            self.logger.debug("Ignoring unhealthy event for self (vexy_ai)")
            return

        await self.service.handle_unhealthy_service(
            service_name=event.service_name,
            consecutive_failures=event.consecutive_failures,
            context=event.details,
        )
