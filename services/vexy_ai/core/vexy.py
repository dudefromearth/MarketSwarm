"""
Vexy - The Central Nervous System of MarketSwarm.

Vexy is the brain that:
- Loads and orchestrates capabilities
- Routes events between capabilities
- Manages the HTTP API
- Maintains connections to all Redis buses
- Coordinates background tasks

Vexy is the ONLY service with connections to all three buses,
giving it full visibility across the entire system.
"""

import asyncio
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Type

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .events import DomainEvent, CapabilityStarted, CapabilityStopped

if TYPE_CHECKING:
    from .capability import BaseCapability
    from ..ports.bus import BusPort
    from ..ports.ai import AIPort


class Vexy:
    """
    The Vexy brain - orchestrates all capabilities.

    Responsibilities:
    - Load capabilities based on configuration
    - Start/stop capabilities in dependency order
    - Route domain events between capabilities
    - Manage the FastAPI application
    - Provide access to Redis buses
    - Schedule and manage background tasks
    """

    def __init__(
        self,
        config: Dict[str, Any],
        logger: Any,
        buses: "BusPort",
        ai: Optional["AIPort"] = None,
        market_intel=None,
    ):
        """
        Initialize Vexy core.

        Args:
            config: Configuration dict from SetupBase
            logger: LogUtil instance
            buses: Bus port providing access to all Redis buses
            ai: AI port for LLM calls (optional, some capabilities don't need it)
            market_intel: Shared MarketIntelProvider instance
        """
        self.config = config
        self.logger = logger
        self.buses = buses
        self.ai = ai
        self.market_intel = market_intel

        # Capability registry
        self._capabilities: Dict[str, "BaseCapability"] = {}
        self._started_capabilities: List[str] = []

        # Event bus
        self._event_handlers: Dict[Type[DomainEvent], List[Callable]] = defaultdict(list)

        # Background tasks
        self._background_tasks: List[asyncio.Task] = []

        # FastAPI application
        self.app = FastAPI(
            title="Vexy AI",
            description="Central Nervous System of MarketSwarm",
            version="2.0.0",
        )
        self._setup_middleware()

    def _setup_middleware(self) -> None:
        """Configure FastAPI middleware."""
        from ..middleware.auth import TrustBoundaryMiddleware

        # Trust boundary: reject requests without X-User-Id from gateway
        # Added before CORS — Starlette runs LIFO, so CORS (last) handles
        # preflight first, then TrustBoundaryMiddleware runs on real requests.
        self.app.add_middleware(TrustBoundaryMiddleware)

        # CORS for development
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # -------------------------------------------------------------------------
    # Capability Management
    # -------------------------------------------------------------------------

    def register(self, capability: "BaseCapability") -> None:
        """
        Register a capability with Vexy.

        Args:
            capability: Capability instance to register

        Raises:
            ValueError: If capability with same name already registered
        """
        if capability.name in self._capabilities:
            raise ValueError(f"Capability '{capability.name}' already registered")

        self._capabilities[capability.name] = capability

        # Register HTTP routes if capability provides them
        if router := capability.get_routes():
            self.app.include_router(router)
            self.logger.debug(
                f"Registered routes for capability '{capability.name}'",
                emoji="🛤️"
            )

        # Register event subscriptions
        for event_type, handler in capability.get_event_subscriptions().items():
            self.subscribe(event_type, handler)

        self.logger.info(
            f"Registered capability: {capability.name} v{capability.version}",
            emoji="📦"
        )

    def get_capability(self, name: str) -> Optional["BaseCapability"]:
        """Get a registered capability by name."""
        return self._capabilities.get(name)

    def _sort_by_dependencies(self) -> List["BaseCapability"]:
        """
        Sort capabilities by dependencies (topological sort).

        Returns capabilities in order such that dependencies come before
        dependents.
        """
        # Build dependency graph
        visited = set()
        result = []

        def visit(name: str) -> None:
            if name in visited:
                return
            visited.add(name)

            cap = self._capabilities.get(name)
            if cap:
                for dep in cap.dependencies:
                    if dep in self._capabilities:
                        visit(dep)
                result.append(cap)

        for name in self._capabilities:
            visit(name)

        return result

    # -------------------------------------------------------------------------
    # Event Bus
    # -------------------------------------------------------------------------

    def subscribe(self, event_type: Type[DomainEvent], handler: Callable) -> None:
        """
        Subscribe to a domain event type.

        Args:
            event_type: The event class to subscribe to
            handler: Async function to call when event is published
        """
        self._event_handlers[event_type].append(handler)

    async def publish(self, event: DomainEvent) -> None:
        """
        Publish a domain event to all subscribers.

        Events are delivered asynchronously. Handler failures are logged
        but don't affect other handlers (fault isolation).

        Args:
            event: The domain event to publish
        """
        handlers = self._event_handlers.get(type(event), [])

        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                self.logger.error(
                    f"Event handler failed for {type(event).__name__}: {e}",
                    emoji="💥"
                )
                # Continue to other handlers - fault isolation

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    async def start(self) -> None:
        """
        Start Vexy and all registered capabilities.

        Capabilities are started in dependency order.
        Background tasks are started after all capabilities are up.
        HTTP server is started last.
        """
        self.logger.info("Vexy starting...", emoji="🦋")

        # Start capabilities in dependency order
        for capability in self._sort_by_dependencies():
            try:
                await capability.start()
                capability._started = True
                self._started_capabilities.append(capability.name)

                await self.publish(CapabilityStarted(
                    capability_name=capability.name,
                    capability_version=capability.version,
                ))

                self.logger.ok(
                    f"Started capability: {capability.name}",
                    emoji="✓"
                )
            except Exception as e:
                self.logger.error(
                    f"Failed to start capability '{capability.name}': {e}",
                    emoji="❌"
                )
                raise

        # Start background tasks from all capabilities
        for capability in self._capabilities.values():
            for task_fn in capability.get_background_tasks():
                task = asyncio.create_task(
                    self._run_background_task(capability.name, task_fn),
                    name=f"{capability.name}-background"
                )
                self._background_tasks.append(task)

        self.logger.info(
            f"Vexy started with {len(self._capabilities)} capabilities",
            emoji="🦋"
        )

        # Start HTTP server (blocks until shutdown)
        await self._run_http_server()

    async def _run_background_task(self, capability_name: str, task_fn: Callable) -> None:
        """Run a background task with error handling."""
        try:
            await task_fn()
        except asyncio.CancelledError:
            self.logger.debug(f"Background task cancelled: {capability_name}")
            raise
        except Exception as e:
            self.logger.error(
                f"Background task failed in '{capability_name}': {e}",
                emoji="💥"
            )

    async def _run_http_server(self) -> None:
        """Run the FastAPI HTTP server."""
        import uvicorn

        port = int(self.config.get("VEXY_HTTP_PORT", "3005"))

        config = uvicorn.Config(
            self.app,
            host="0.0.0.0",
            port=port,
            log_level="info",
        )
        server = uvicorn.Server(config)

        self.logger.info(f"HTTP server starting on port {port}", emoji="🌐")
        await server.serve()

    async def stop(self) -> None:
        """
        Stop Vexy and all capabilities.

        Capabilities are stopped in reverse dependency order.
        Background tasks are cancelled first.
        """
        self.logger.info("Vexy stopping...", emoji="🦋")

        # Cancel all background tasks
        for task in self._background_tasks:
            task.cancel()

        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
            self._background_tasks.clear()

        # Stop capabilities in reverse order
        for name in reversed(self._started_capabilities):
            capability = self._capabilities.get(name)
            if capability:
                try:
                    await capability.stop()
                    capability._started = False

                    await self.publish(CapabilityStopped(
                        capability_name=name,
                        reason="shutdown",
                    ))

                    self.logger.info(f"Stopped capability: {name}", emoji="⏹️")
                except Exception as e:
                    self.logger.error(
                        f"Error stopping capability '{name}': {e}",
                        emoji="⚠️"
                    )

        self._started_capabilities.clear()
        self.logger.info("Vexy stopped", emoji="🦋")

    # -------------------------------------------------------------------------
    # Health & Status
    # -------------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Get current status of Vexy and all capabilities."""
        return {
            "status": "running" if self._started_capabilities else "stopped",
            "capabilities": {
                name: {
                    "version": cap.version,
                    "started": cap._started,
                    "dependencies": cap.dependencies,
                    "buses": cap.buses_required,
                }
                for name, cap in self._capabilities.items()
            },
            "background_tasks": len(self._background_tasks),
            "event_subscriptions": {
                event_type.__name__: len(handlers)
                for event_type, handlers in self._event_handlers.items()
            },
        }
