"""
Bus Port - Abstract interface for Redis bus access.

Vexy is the ONLY service with connections to all three buses:
- System: Heartbeats, service control, system state
- Market: Quotes, positions, alerts, GEX
- Intel: Articles, analysis, synthesis

This port abstracts the bus connections so they can be
mocked for testing.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from redis.asyncio import Redis


class BusPort(ABC):
    """
    Abstract interface for Redis bus access.

    Provides access to all three MarketSwarm buses.
    Vexy's unique privilege - full system visibility.
    """

    @abstractmethod
    async def connect(self) -> None:
        """
        Connect to all Redis buses.

        Raises:
            ConnectionError: If any bus connection fails
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close all Redis connections."""
        pass

    @property
    @abstractmethod
    def system(self) -> "Redis":
        """
        System Redis bus.

        Contains:
        - Service heartbeats ({service}:heartbeat)
        - Control commands ({service}:control)
        - System configuration
        - Truth data
        """
        pass

    @property
    @abstractmethod
    def market(self) -> "Redis":
        """
        Market Redis bus.

        Contains:
        - Real-time quotes
        - Position data
        - Alert state
        - GEX/volatility data
        - Epoch markers
        """
        pass

    @property
    @abstractmethod
    def intel(self) -> "Redis":
        """
        Intel Redis bus.

        Contains:
        - RSS articles
        - Analysis results
        - Synthesized intelligence
        - Vexy commentary
        """
        pass

    @abstractmethod
    async def publish(self, bus: str, channel: str, message: Any) -> None:
        """
        Publish a message to a channel on a specific bus.

        Args:
            bus: Which bus ("system", "market", "intel")
            channel: Channel name to publish to
            message: Message to publish (will be JSON serialized)
        """
        pass

    @abstractmethod
    async def get(self, bus: str, key: str) -> Optional[str]:
        """
        Get a value from a specific bus.

        Args:
            bus: Which bus ("system", "market", "intel")
            key: Key to retrieve

        Returns:
            Value as string, or None if not found
        """
        pass

    @abstractmethod
    async def set(self, bus: str, key: str, value: Any, ex: Optional[int] = None) -> None:
        """
        Set a value on a specific bus.

        Args:
            bus: Which bus ("system", "market", "intel")
            key: Key to set
            value: Value to store (will be JSON serialized if not string)
            ex: Optional expiration in seconds
        """
        pass
