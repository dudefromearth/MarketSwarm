"""
Domain Events - Communication between capabilities.

Events are the language capabilities use to communicate without
tight coupling. Each capability can publish and subscribe to events.

Naming convention: <noun>.<verb> (e.g., service.unhealthy, epoch.triggered)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class DomainEvent:
    """Base class for all domain events."""

    occurred_at: datetime = field(default_factory=datetime.utcnow)
    origin_capability: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event for transmission."""
        return {
            "type": self.__class__.__name__,
            "occurred_at": self.occurred_at.isoformat(),
            "origin": self.origin_capability,
            "data": {
                k: v for k, v in self.__dict__.items()
                if k not in ("occurred_at", "origin_capability")
            },
        }


# -----------------------------------------------------------------------------
# Health & Healing Events
# -----------------------------------------------------------------------------

@dataclass
class ServiceUnhealthy(DomainEvent):
    """Published when a service fails health checks."""
    service_name: str = ""
    status: str = ""  # timeout, error, degraded
    consecutive_failures: int = 0
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ServiceRecovered(DomainEvent):
    """Published when a service returns to healthy state."""
    service_name: str = ""
    downtime_seconds: float = 0.0


@dataclass
class HealingInitiated(DomainEvent):
    """Published when a healing action is started."""
    service_name: str = ""
    action: str = ""  # restart, failover, escalate
    attempt: int = 1
    protocol: str = ""


@dataclass
class HealingCompleted(DomainEvent):
    """Published when a healing action finishes."""
    service_name: str = ""
    action: str = ""
    success: bool = False
    duration_seconds: float = 0.0
    error: Optional[str] = None


# -----------------------------------------------------------------------------
# Commentary Events (Epoch/Event Engine)
# -----------------------------------------------------------------------------

@dataclass
class EpochTriggered(DomainEvent):
    """Published when a market epoch is detected."""
    epoch_name: str = ""
    epoch_type: str = ""  # premarket, open, midday, power_hour, close
    market_context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MarketEventDetected(DomainEvent):
    """Published when a market event is detected."""
    event_type: str = ""  # breakout, reversal, volume_spike, etc.
    symbol: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CommentaryGenerated(DomainEvent):
    """Published when Vexy generates commentary."""
    commentary_type: str = ""  # epoch, event, article
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


# -----------------------------------------------------------------------------
# User Interaction Events
# -----------------------------------------------------------------------------

@dataclass
class UserMessageReceived(DomainEvent):
    """Published when a user sends a chat message."""
    user_id: int = 0
    outlet: str = ""  # chat, journal, playbook, routine
    message_preview: str = ""  # First 100 chars for logging


@dataclass
class UserSessionStarted(DomainEvent):
    """Published when a user opens a session (e.g., routine panel)."""
    user_id: int = 0
    session_type: str = ""


# -----------------------------------------------------------------------------
# Mesh Events (Multi-Node Communication)
# -----------------------------------------------------------------------------

@dataclass
class PeerDiscovered(DomainEvent):
    """Published when a new peer Vexy node is discovered."""
    node_id: str = ""
    node_url: str = ""


@dataclass
class PeerLost(DomainEvent):
    """Published when a peer Vexy node becomes unreachable."""
    node_id: str = ""
    last_seen: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PeerEventReceived(DomainEvent):
    """Published when an event is received from a peer node."""
    source_node: str = ""
    event_type: str = ""
    event_data: Dict[str, Any] = field(default_factory=dict)


# -----------------------------------------------------------------------------
# System Events
# -----------------------------------------------------------------------------

@dataclass
class CapabilityStarted(DomainEvent):
    """Published when a capability finishes starting."""
    capability_name: str = ""
    capability_version: str = ""


@dataclass
class CapabilityStopped(DomainEvent):
    """Published when a capability stops."""
    capability_name: str = ""
    reason: str = ""  # shutdown, error, disabled


@dataclass
class ConfigReloaded(DomainEvent):
    """Published when configuration is reloaded from Truth."""
    changed_keys: List[str] = field(default_factory=list)
