"""
Redis Bus Adapter - Implementation of BusPort for Redis.

Provides Vexy's unique full-visibility access to all three
MarketSwarm Redis buses.
"""

import json
from typing import Any, Dict, Optional

from redis.asyncio import Redis

from ...ports.bus import BusPort


class RedisBusAdapter(BusPort):
    """
    Redis implementation of the BusPort.

    Connects to all three MarketSwarm buses:
    - System (heartbeats, control)
    - Market (quotes, positions, alerts)
    - Intel (articles, analysis)
    """

    def __init__(self, config: Dict[str, Any], logger: Any):
        """
        Initialize adapter with configuration.

        Args:
            config: Configuration dict containing bus URLs
            logger: LogUtil instance
        """
        self.config = config
        self.logger = logger

        # Extract bus URLs from config
        buses = config.get("buses", {})
        self._system_url = buses.get("system-redis", {}).get("url", "redis://127.0.0.1:6379")
        self._market_url = buses.get("market-redis", {}).get("url", "redis://127.0.0.1:6380")
        self._intel_url = buses.get("intel-redis", {}).get("url", "redis://127.0.0.1:6381")

        # Redis clients (created during connect)
        self._system: Optional[Redis] = None
        self._market: Optional[Redis] = None
        self._intel: Optional[Redis] = None

        self._connected = False

    async def connect(self) -> None:
        """Connect to all Redis buses."""
        try:
            self._system = Redis.from_url(
                self._system_url,
                decode_responses=True,
            )
            await self._system.ping()
            self.logger.debug(f"Connected to system bus: {self._system_url}")

            self._market = Redis.from_url(
                self._market_url,
                decode_responses=True,
            )
            await self._market.ping()
            self.logger.debug(f"Connected to market bus: {self._market_url}")

            self._intel = Redis.from_url(
                self._intel_url,
                decode_responses=True,
            )
            await self._intel.ping()
            self.logger.debug(f"Connected to intel bus: {self._intel_url}")

            self._connected = True
            self.logger.info("All Redis buses connected", emoji="🔴")

        except Exception as e:
            self.logger.error(f"Failed to connect to Redis buses: {e}", emoji="❌")
            await self.close()
            raise ConnectionError(f"Redis connection failed: {e}") from e

    async def close(self) -> None:
        """Close all Redis connections."""
        if self._system:
            await self._system.close()
            self._system = None

        if self._market:
            await self._market.close()
            self._market = None

        if self._intel:
            await self._intel.close()
            self._intel = None

        self._connected = False
        self.logger.debug("Redis connections closed")

    @property
    def system(self) -> Redis:
        """System Redis bus."""
        if not self._system:
            raise RuntimeError("Bus adapter not connected")
        return self._system

    @property
    def market(self) -> Redis:
        """Market Redis bus."""
        if not self._market:
            raise RuntimeError("Bus adapter not connected")
        return self._market

    @property
    def intel(self) -> Redis:
        """Intel Redis bus."""
        if not self._intel:
            raise RuntimeError("Bus adapter not connected")
        return self._intel

    def _get_bus(self, bus: str) -> Redis:
        """Get Redis client by bus name."""
        if bus == "system":
            return self.system
        elif bus == "market":
            return self.market
        elif bus == "intel":
            return self.intel
        else:
            raise ValueError(f"Unknown bus: {bus}")

    async def publish(self, bus: str, channel: str, message: Any) -> None:
        """Publish a message to a channel on a specific bus."""
        client = self._get_bus(bus)

        if isinstance(message, (dict, list)):
            message = json.dumps(message)

        await client.publish(channel, message)

    async def get(self, bus: str, key: str) -> Optional[str]:
        """Get a value from a specific bus."""
        client = self._get_bus(bus)
        return await client.get(key)

    async def set(
        self,
        bus: str,
        key: str,
        value: Any,
        ex: Optional[int] = None
    ) -> None:
        """Set a value on a specific bus."""
        client = self._get_bus(bus)

        if isinstance(value, (dict, list)):
            value = json.dumps(value)

        if ex:
            await client.set(key, value, ex=ex)
        else:
            await client.set(key, value)

    @property
    def is_connected(self) -> bool:
        """Check if all buses are connected."""
        return self._connected
