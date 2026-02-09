"""
Base Capability - Contract for all Vexy capabilities.

A capability is a self-contained domain that provides:
- HTTP routes (optional)
- Background tasks (optional)
- Event subscriptions (optional)
- Event publishing

Capabilities are loaded and orchestrated by the Vexy core.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Dict, List, Optional

from fastapi import APIRouter

if TYPE_CHECKING:
    from .vexy import Vexy
    from redis.asyncio import Redis


class BaseCapability(ABC):
    """
    Base class for all Vexy capabilities.

    Subclasses must define:
    - name: Unique identifier for the capability
    - version: Semantic version string

    Subclasses may define:
    - dependencies: List of capability names that must start first
    - buses_required: List of buses this capability needs ("system", "market", "intel")
    """

    # Must be overridden by subclasses
    name: str = "unnamed"
    version: str = "0.0.0"

    # Optional - capabilities this one depends on
    dependencies: List[str] = []

    # Optional - which Redis buses this capability needs access to
    # Valid values: "system", "market", "intel"
    buses_required: List[str] = []

    def __init__(self, vexy: "Vexy"):
        """
        Initialize capability with reference to Vexy core.

        Args:
            vexy: The Vexy core instance (provides config, logger, buses, events)
        """
        self.vexy = vexy
        self.config = vexy.config
        self.logger = vexy.logger
        self._started = False

    # -------------------------------------------------------------------------
    # Bus Access (only available if declared in buses_required)
    # -------------------------------------------------------------------------

    @property
    def system(self) -> "Redis":
        """Access to system Redis bus (heartbeats, control)."""
        if "system" not in self.buses_required:
            raise RuntimeError(
                f"Capability '{self.name}' did not declare 'system' in buses_required"
            )
        return self.vexy.buses.system

    @property
    def market(self) -> "Redis":
        """Access to market Redis bus (quotes, positions, alerts)."""
        if "market" not in self.buses_required:
            raise RuntimeError(
                f"Capability '{self.name}' did not declare 'market' in buses_required"
            )
        return self.vexy.buses.market

    @property
    def intel(self) -> "Redis":
        """Access to intel Redis bus (articles, analysis)."""
        if "intel" not in self.buses_required:
            raise RuntimeError(
                f"Capability '{self.name}' did not declare 'intel' in buses_required"
            )
        return self.vexy.buses.intel

    # -------------------------------------------------------------------------
    # Event System Shortcuts
    # -------------------------------------------------------------------------

    async def publish(self, event: Any) -> None:
        """Publish a domain event to the event bus."""
        event.origin_capability = self.name
        await self.vexy.publish(event)

    def subscribe(self, event_type: type, handler: Callable) -> None:
        """Subscribe to a domain event type."""
        self.vexy.subscribe(event_type, handler)

    # -------------------------------------------------------------------------
    # Lifecycle Methods (override in subclasses)
    # -------------------------------------------------------------------------

    @abstractmethod
    async def start(self) -> None:
        """
        Called when the capability is started.

        Use this to:
        - Initialize connections
        - Load initial state
        - Subscribe to events
        - Start any internal state machines
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """
        Called when the capability is stopped.

        Use this to:
        - Close connections
        - Save state
        - Cancel pending operations
        - Clean up resources
        """
        pass

    # -------------------------------------------------------------------------
    # Extension Points (override if needed)
    # -------------------------------------------------------------------------

    def get_routes(self) -> Optional[APIRouter]:
        """
        Return a FastAPI router with HTTP endpoints for this capability.

        Returns:
            APIRouter with routes, or None if this capability has no HTTP endpoints.

        Example:
            def get_routes(self) -> APIRouter:
                router = APIRouter(prefix="/api/vexy/my-capability")
                router.get("/status")(self.get_status)
                router.post("/action")(self.do_action)
                return router
        """
        return None

    def get_background_tasks(self) -> List[Callable[[], Coroutine]]:
        """
        Return async functions to run as background tasks.

        These will be started after start() completes and run until
        the capability is stopped.

        Returns:
            List of async functions (no arguments, run forever or until cancelled)

        Example:
            def get_background_tasks(self):
                return [self._poll_loop, self._cleanup_loop]

            async def _poll_loop(self):
                while True:
                    await self._do_poll()
                    await asyncio.sleep(60)
        """
        return []

    def get_event_subscriptions(self) -> Dict[type, Callable]:
        """
        Return event types and their handlers.

        This is an alternative to calling self.subscribe() in start().
        Events are automatically subscribed before start() is called.

        Returns:
            Dict mapping event type to async handler function

        Example:
            def get_event_subscriptions(self):
                return {
                    ServiceUnhealthy: self.handle_unhealthy,
                    EpochTriggered: self.handle_epoch,
                }
        """
        return {}

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------

    def get_config(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value, with optional capability-specific override.

        Looks for:
        1. config[capability_name][key]
        2. config[key]
        3. default

        Args:
            key: Configuration key to look up
            default: Default value if not found

        Returns:
            Configuration value
        """
        # Check capability-specific config first
        cap_config = self.config.get(self.name, {})
        if isinstance(cap_config, dict) and key in cap_config:
            return cap_config[key]

        # Fall back to global config
        return self.config.get(key, default)

    def __repr__(self) -> str:
        status = "started" if self._started else "stopped"
        return f"<{self.__class__.__name__} name='{self.name}' version='{self.version}' {status}>"
