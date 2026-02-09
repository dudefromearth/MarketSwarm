"""
Mesh Peers - Discovery and tracking of other Vexy nodes.

Uses Redis pub/sub on system-redis for peer discovery:
- Nodes publish heartbeats to 'mesh:heartbeat' channel
- Nodes store presence in 'mesh:nodes:{node_id}' keys with TTL
- Nodes subscribe to 'mesh:events' for event propagation
"""

import asyncio
import json
from datetime import datetime, UTC
from typing import Any, Callable, Dict, List, Optional

from .models import MeshNode, NodeStatus


class PeerRegistry:
    """
    Tracks all known Vexy peer nodes.

    Discovery happens via Redis:
    - Each node publishes heartbeats to mesh:heartbeat channel
    - Each node stores its identity in mesh:nodes:{id} with TTL
    - Peers are discovered by scanning mesh:nodes:* keys
    """

    HEARTBEAT_CHANNEL = "mesh:heartbeat"
    EVENTS_CHANNEL = "mesh:events"
    NODE_KEY_PREFIX = "mesh:nodes:"
    NODE_TTL_SEC = 30  # Node considered dead if no heartbeat in 30s

    def __init__(
        self,
        local_node_id: str,
        config: Dict[str, Any],
        logger: Any,
        on_peer_discovered: Optional[Callable] = None,
        on_peer_lost: Optional[Callable] = None,
    ):
        self.local_node_id = local_node_id
        self.config = config
        self.logger = logger
        self.on_peer_discovered = on_peer_discovered
        self.on_peer_lost = on_peer_lost

        # Known peers (excluding self)
        self._peers: Dict[str, MeshNode] = {}
        self._last_seen: Dict[str, datetime] = {}

        # Control
        self.running = False
        self._pubsub = None

    def _get_redis_client(self):
        """Get Redis client for system bus."""
        import redis

        buses = self.config.get("buses", {}) or {}
        system_url = buses.get("system-redis", {}).get("url", "redis://127.0.0.1:6379")
        return redis.Redis.from_url(system_url, decode_responses=True)

    async def start(self) -> None:
        """Start peer discovery."""
        self.running = True
        self.logger.info("Peer registry starting", emoji="🌐")

    async def stop(self) -> None:
        """Stop peer discovery."""
        self.running = False
        if self._pubsub:
            try:
                self._pubsub.close()
            except Exception:
                pass
        self._pubsub = None
        self.logger.info("Peer registry stopped", emoji="🌐")

    async def publish_heartbeat(self, payload: Dict[str, Any]) -> None:
        """Publish heartbeat to mesh."""
        try:
            r = self._get_redis_client()

            # Store in key with TTL
            node_key = f"{self.NODE_KEY_PREFIX}{self.local_node_id}"
            r.set(node_key, json.dumps(payload), ex=self.NODE_TTL_SEC)

            # Also publish to channel for immediate discovery
            r.publish(self.HEARTBEAT_CHANNEL, json.dumps(payload))

        except Exception as e:
            self.logger.debug(f"Heartbeat publish failed: {e}")

    async def discover_peers(self) -> List[MeshNode]:
        """Scan for all mesh nodes."""
        try:
            r = self._get_redis_client()

            # Scan for all node keys
            peers = []
            for key in r.scan_iter(f"{self.NODE_KEY_PREFIX}*"):
                if isinstance(key, bytes):
                    key = key.decode('utf-8')

                # Skip self
                node_id = key.replace(self.NODE_KEY_PREFIX, "")
                if node_id == self.local_node_id:
                    continue

                # Get node data
                data = r.get(key)
                if data:
                    try:
                        payload = json.loads(data)
                        node = MeshNode(
                            node_id=payload.get("node_id", node_id),
                            hostname=payload.get("hostname", "unknown"),
                            port=payload.get("port", 3005),
                            region=payload.get("region"),
                            status=NodeStatus(payload.get("status", "online")),
                            last_seen=datetime.now(UTC).isoformat(),
                            capabilities=payload.get("capabilities", []),
                        )
                        peers.append(node)

                        # Track in registry
                        if node_id not in self._peers:
                            self._peers[node_id] = node
                            self._last_seen[node_id] = datetime.now(UTC)
                            if self.on_peer_discovered:
                                await self.on_peer_discovered(node)
                        else:
                            self._peers[node_id] = node
                            self._last_seen[node_id] = datetime.now(UTC)

                    except (json.JSONDecodeError, KeyError) as e:
                        self.logger.debug(f"Invalid peer data for {key}: {e}")

            # Check for lost peers
            now = datetime.now(UTC)
            lost = []
            for node_id, last_seen in list(self._last_seen.items()):
                if (now - last_seen).total_seconds() > self.NODE_TTL_SEC * 2:
                    lost.append(node_id)

            for node_id in lost:
                peer = self._peers.pop(node_id, None)
                self._last_seen.pop(node_id, None)
                if peer and self.on_peer_lost:
                    await self.on_peer_lost(peer)

            return peers

        except Exception as e:
            self.logger.debug(f"Peer discovery failed: {e}")
            return []

    def get_peers(self) -> List[MeshNode]:
        """Get current list of known peers."""
        return list(self._peers.values())

    def get_peer(self, node_id: str) -> Optional[MeshNode]:
        """Get a specific peer by ID."""
        return self._peers.get(node_id)

    async def broadcast_event(self, event_type: str, payload: Dict[str, Any]) -> int:
        """
        Broadcast an event to all peers.

        Returns number of peers the message was sent to.
        """
        try:
            r = self._get_redis_client()

            message = json.dumps({
                "source_node": self.local_node_id,
                "event_type": event_type,
                "payload": payload,
                "timestamp": datetime.now(UTC).isoformat(),
            })

            # Publish to events channel
            subscribers = r.publish(self.EVENTS_CHANNEL, message)
            return subscribers

        except Exception as e:
            self.logger.debug(f"Event broadcast failed: {e}")
            return 0
