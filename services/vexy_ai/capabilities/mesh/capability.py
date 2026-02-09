"""
Mesh Capability - Multi-node Vexy communication.

Enables multiple Vexy instances to:
- Discover each other via Redis
- Share events across nodes
- Provide redundancy and scaling
"""

from typing import Callable, List, Optional

from fastapi import APIRouter

from ...core.capability import BaseCapability
from .service import MeshService
from .models import (
    MeshStatusResponse,
    PeersResponse,
    BroadcastRequest,
    BroadcastResponse,
)


class MeshCapability(BaseCapability):
    """
    Multi-node mesh capability.

    Provides:
    - Peer discovery via Redis
    - Event broadcasting
    - GET /api/vexy/mesh/status - Mesh status
    - GET /api/vexy/mesh/peers - List of peers
    - GET /api/vexy/mesh/node - This node's identity
    - POST /api/vexy/mesh/broadcast - Broadcast event to peers
    """

    name = "mesh"
    version = "1.0.0"
    dependencies = []
    buses_required = ["system", "market", "intel"]  # Full bus access

    def __init__(self, vexy):
        super().__init__(vexy)
        self.service: Optional[MeshService] = None

    async def start(self) -> None:
        """Initialize Mesh service."""
        self.service = MeshService(
            self.config,
            self.logger,
            event_publisher=self.vexy.publish,
        )

        # Set capabilities this node has
        capabilities = list(self.vexy._capabilities.keys())
        self.service.set_capabilities(capabilities)

        await self.service.start()
        self.logger.info("Mesh capability started", emoji="🌐")

    async def stop(self) -> None:
        """Stop Mesh service."""
        if self.service:
            await self.service.stop()
        self.service = None
        self.logger.info("Mesh capability stopped", emoji="🌐")

    def get_routes(self) -> APIRouter:
        """Return FastAPI router with Mesh endpoints."""
        router = APIRouter(prefix="/api/vexy/mesh", tags=["Mesh"])

        @router.get("/status", response_model=MeshStatusResponse)
        async def get_status():
            """Get mesh status for this node."""
            status = self.service.get_status()
            return MeshStatusResponse(**status)

        @router.get("/peers", response_model=PeersResponse)
        async def get_peers():
            """Get list of known mesh peers."""
            peers = self.service.get_peers()
            return PeersResponse(peers=peers)

        @router.get("/node")
        async def get_node():
            """Get this node's identity."""
            node = self.service.get_local_node()
            return node.model_dump()

        @router.post("/broadcast", response_model=BroadcastResponse)
        async def broadcast(request: BroadcastRequest):
            """Broadcast an event to all mesh peers."""
            count = await self.service.broadcast_event(
                request.message_type,
                request.payload,
            )
            return BroadcastResponse(
                delivered_to=count,
                failed=0,
            )

        return router

    def get_background_tasks(self) -> List[Callable]:
        """Return background tasks to run."""
        return [
            self._run_heartbeat_loop,
            self._run_discovery_loop,
        ]

    async def _run_heartbeat_loop(self) -> None:
        """Background task for publishing heartbeats."""
        if self.service:
            await self.service.run_heartbeat_loop()

    async def _run_discovery_loop(self) -> None:
        """Background task for discovering peers."""
        if self.service:
            await self.service.run_discovery_loop()
