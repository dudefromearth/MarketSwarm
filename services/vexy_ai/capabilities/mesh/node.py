"""
Mesh Node - This Vexy instance's identity in the mesh.

Handles:
- Unique node ID generation
- Node metadata
- Heartbeat broadcasting
"""

import hashlib
import os
import socket
from datetime import datetime, UTC
from typing import Any, Dict, List

from .models import MeshNode, NodeStatus


def generate_node_id(hostname: str, port: int) -> str:
    """
    Generate a unique node ID from hostname and port.

    Uses a hash of hostname:port to ensure consistency across restarts.
    """
    raw = f"{hostname}:{port}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


class LocalNode:
    """
    This Vexy instance's identity.

    Provides:
    - Node ID (stable across restarts)
    - Node metadata
    - Heartbeat generation
    """

    def __init__(self, config: Dict[str, Any], logger: Any):
        self.config = config
        self.logger = logger

        # Resolve identity
        self.hostname = socket.gethostname()
        self.port = int(config.get("VEXY_HTTP_PORT", 3005))
        self.region = config.get("mesh", {}).get("region", os.getenv("AWS_REGION", "local"))

        self.node_id = generate_node_id(self.hostname, self.port)
        self.status = NodeStatus.ONLINE
        self.started_at = datetime.now(UTC)

        # Track capabilities we have
        self._capabilities: List[str] = []

        self.logger.info(
            f"Mesh node identity: {self.node_id} ({self.hostname}:{self.port})",
            emoji="🌐"
        )

    def set_capabilities(self, capabilities: List[str]) -> None:
        """Set the list of capabilities this node has."""
        self._capabilities = capabilities

    def get_node(self) -> MeshNode:
        """Get this node's identity as a MeshNode."""
        return MeshNode(
            node_id=self.node_id,
            hostname=self.hostname,
            port=self.port,
            region=self.region,
            status=self.status,
            last_seen=datetime.now(UTC).isoformat(),
            capabilities=self._capabilities,
            version="2.0.0",
        )

    def get_heartbeat_payload(self) -> Dict[str, Any]:
        """Generate heartbeat payload for peer discovery."""
        return {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "port": self.port,
            "region": self.region,
            "status": self.status.value,
            "capabilities": self._capabilities,
            "uptime_sec": (datetime.now(UTC) - self.started_at).total_seconds(),
        }

    def set_status(self, status: NodeStatus) -> None:
        """Update node status."""
        self.status = status
