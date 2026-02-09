"""
Mesh Models - Data structures for multi-node communication.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class NodeStatus(str, Enum):
    """Status of a mesh node."""
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    SYNCING = "syncing"


class MeshNode(BaseModel):
    """Identity of a Vexy mesh node."""
    node_id: str
    hostname: str
    port: int
    region: Optional[str] = None
    status: NodeStatus = NodeStatus.ONLINE
    last_seen: Optional[str] = None
    capabilities: List[str] = []
    version: str = "1.0.0"


class PeerMessage(BaseModel):
    """Message sent between mesh peers."""
    source_node: str
    target_node: Optional[str] = None  # None = broadcast
    message_type: str  # event, sync, heartbeat, query
    payload: Dict[str, Any]
    timestamp: str


class MeshStatusResponse(BaseModel):
    """Response for mesh status endpoint."""
    node_id: str
    status: NodeStatus
    peers_online: int
    peers_total: int
    last_sync: Optional[str] = None


class PeersResponse(BaseModel):
    """Response for peers list endpoint."""
    peers: List[MeshNode]


class BroadcastRequest(BaseModel):
    """Request to broadcast a message to peers."""
    message_type: str
    payload: Dict[str, Any]


class BroadcastResponse(BaseModel):
    """Response from broadcast."""
    delivered_to: int
    failed: int
