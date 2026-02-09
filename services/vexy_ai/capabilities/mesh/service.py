"""
Mesh Service - Orchestrates multi-node Vexy mesh.

Handles:
- Node identity and heartbeats
- Peer discovery and tracking
- Event broadcasting between nodes
- State synchronization
"""

import asyncio
from datetime import datetime, UTC
from typing import Any, Callable, Dict, List, Optional

from .models import MeshNode, NodeStatus, PeerMessage
from .node import LocalNode
from .peers import PeerRegistry


class MeshService:
    """
    Mesh orchestration service.

    Runs background tasks for:
    - Publishing heartbeats
    - Discovering peers
    - Receiving and forwarding events
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

        # Node identity
        self.local_node = LocalNode(config, logger)

        # Peer registry
        self.peers = PeerRegistry(
            local_node_id=self.local_node.node_id,
            config=config,
            logger=logger,
            on_peer_discovered=self._on_peer_discovered,
            on_peer_lost=self._on_peer_lost,
        )

        # State
        self.running = False
        self.last_sync: Optional[datetime] = None

        # Stats
        self.events_sent = 0
        self.events_received = 0

    async def start(self) -> None:
        """Start mesh service."""
        self.running = True
        await self.peers.start()
        self.logger.info("Mesh service started", emoji="🌐")

    async def stop(self) -> None:
        """Stop mesh service."""
        self.running = False
        await self.peers.stop()
        self.logger.info("Mesh service stopped", emoji="🌐")

    def set_capabilities(self, capabilities: List[str]) -> None:
        """Set capabilities for this node."""
        self.local_node.set_capabilities(capabilities)

    async def run_heartbeat_loop(self) -> None:
        """Background task for publishing heartbeats."""
        heartbeat_interval = self.config.get("mesh", {}).get("heartbeat_interval_sec", 10)

        try:
            while self.running:
                await self.peers.publish_heartbeat(
                    self.local_node.get_heartbeat_payload()
                )
                await asyncio.sleep(heartbeat_interval)

        except asyncio.CancelledError:
            self.logger.debug("Heartbeat loop cancelled")
            raise

    async def run_discovery_loop(self) -> None:
        """Background task for discovering peers."""
        discovery_interval = self.config.get("mesh", {}).get("discovery_interval_sec", 30)

        try:
            while self.running:
                peers = await self.peers.discover_peers()
                self.last_sync = datetime.now(UTC)

                if peers:
                    self.logger.debug(f"Discovered {len(peers)} mesh peer(s)")

                await asyncio.sleep(discovery_interval)

        except asyncio.CancelledError:
            self.logger.debug("Discovery loop cancelled")
            raise

    async def _on_peer_discovered(self, peer: MeshNode) -> None:
        """Called when a new peer is discovered."""
        self.logger.info(
            f"Peer discovered: {peer.node_id} ({peer.hostname}:{peer.port})",
            emoji="🌐"
        )

        # Publish domain event
        if self.event_publisher:
            from ...core.events import PeerDiscovered
            await self.event_publisher(PeerDiscovered(
                node_id=peer.node_id,
                node_url=f"http://{peer.hostname}:{peer.port}",
            ))

    async def _on_peer_lost(self, peer: MeshNode) -> None:
        """Called when a peer is lost."""
        self.logger.warn(
            f"Peer lost: {peer.node_id} ({peer.hostname}:{peer.port})",
            emoji="🌐"
        )

        # Publish domain event
        if self.event_publisher:
            from ...core.events import PeerLost
            await self.event_publisher(PeerLost(
                node_id=peer.node_id,
                last_seen=datetime.now(UTC),
            ))

    async def broadcast_event(self, event_type: str, payload: Dict[str, Any]) -> int:
        """Broadcast an event to all mesh peers."""
        count = await self.peers.broadcast_event(event_type, payload)
        self.events_sent += 1
        return count

    def get_status(self) -> Dict[str, Any]:
        """Get mesh status."""
        peers = self.peers.get_peers()
        online = sum(1 for p in peers if p.status == NodeStatus.ONLINE)

        return {
            "node_id": self.local_node.node_id,
            "status": self.local_node.status.value,
            "peers_online": online,
            "peers_total": len(peers),
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "events_sent": self.events_sent,
            "events_received": self.events_received,
        }

    def get_peers(self) -> List[MeshNode]:
        """Get list of known peers."""
        return self.peers.get_peers()

    def get_local_node(self) -> MeshNode:
        """Get this node's identity."""
        return self.local_node.get_node()
