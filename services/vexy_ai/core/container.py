"""
Dependency Injection Container - Wires all Vexy components.

The container is responsible for:
- Creating adapter instances (implementations of ports)
- Connecting adapters to external systems
- Creating the Vexy core with all dependencies
- Loading and registering capabilities
- Providing clean shutdown

Usage:
    container = Container(config, logger)
    vexy = await container.wire()
    try:
        await vexy.start()
    finally:
        await container.shutdown()
"""

import importlib
from typing import Any, Dict, List, Optional, Type

from .vexy import Vexy
from .capability import BaseCapability


# Capability class registry - maps name to module path
CAPABILITY_REGISTRY: Dict[str, str] = {
    # Format: "capability_name": "capabilities.name.capability.ClassName"
    "ml": "capabilities.ml.capability.MLCapability",
    "routine": "capabilities.routine.capability.RoutineCapability",
    "playbook": "capabilities.playbook.capability.PlaybookCapability",
    "journal": "capabilities.journal.capability.JournalCapability",
    "chat": "capabilities.chat.capability.ChatCapability",
    "commentary": "capabilities.commentary.capability.CommentaryCapability",
    "health_monitor": "capabilities.health_monitor.capability.HealthMonitorCapability",
    "healer": "capabilities.healer.capability.HealerCapability",
    "mesh": "capabilities.mesh.capability.MeshCapability",
}


class Container:
    """
    Dependency injection container for Vexy.

    Manages the lifecycle of all dependencies and provides
    clean wiring of components.
    """

    def __init__(self, config: Dict[str, Any], logger: Any):
        """
        Initialize container with configuration.

        Args:
            config: Configuration dict from SetupBase
            logger: LogUtil instance
        """
        self.config = config
        self.logger = logger

        # Ports (will be created during wire())
        self._bus_adapter = None
        self._ai_adapter = None

        # Core
        self._vexy: Optional[Vexy] = None

        # Track what we've created for cleanup
        self._initialized = False

    async def wire(self) -> Vexy:
        """
        Wire all dependencies and create Vexy instance.

        Returns:
            Configured Vexy instance ready to start

        Raises:
            RuntimeError: If wiring fails
        """
        self.logger.info("Wiring Vexy dependencies...", emoji="🔌")

        try:
            # 1. Create and connect bus adapter
            self._bus_adapter = await self._create_bus_adapter()

            # 2. Create AI adapter
            self._ai_adapter = self._create_ai_adapter()

            # 3. Create Vexy core
            self._vexy = Vexy(
                config=self.config,
                logger=self.logger,
                buses=self._bus_adapter,
                ai=self._ai_adapter,
            )

            # 4. Register health endpoint (always available)
            self._register_health_routes()

            # 5. Load and register capabilities
            await self._load_capabilities()

            self._initialized = True
            self.logger.ok("Vexy wiring complete", emoji="✓")

            return self._vexy

        except Exception as e:
            self.logger.error(f"Failed to wire Vexy: {e}", emoji="❌")
            await self.shutdown()
            raise RuntimeError(f"Vexy wiring failed: {e}") from e

    async def _create_bus_adapter(self):
        """Create and connect the Redis bus adapter."""
        from ..adapters.redis.bus import RedisBusAdapter

        adapter = RedisBusAdapter(self.config, self.logger)
        await adapter.connect()

        self.logger.info("Connected to all Redis buses", emoji="🔴")
        return adapter

    def _create_ai_adapter(self):
        """Create the AI adapter."""
        from ..adapters.ai.client import AIAdapter

        adapter = AIAdapter(self.config, self.logger)
        self.logger.info("AI adapter ready", emoji="🤖")
        return adapter

    def _register_health_routes(self) -> None:
        """Register basic health check and admin routes."""
        from fastapi import APIRouter

        router = APIRouter()

        @router.get("/health")
        async def health():
            return {"status": "healthy", "service": "vexy_ai"}

        @router.get("/api/vexy/status")
        async def status():
            return self._vexy.get_status()

        self._vexy.app.include_router(router)

        # Register admin routes (prompt management)
        from ..adapters.http.routes.admin import create_admin_router
        admin_router = create_admin_router()
        self._vexy.app.include_router(admin_router)

    async def _load_capabilities(self) -> None:
        """Load and register capabilities based on configuration."""
        # Get enabled capabilities from config
        enabled = self.config.get("capabilities", [])

        if not enabled:
            self.logger.warn("No capabilities enabled in config", emoji="⚠️")
            return

        for name in enabled:
            try:
                capability = self._load_capability(name)
                if capability:
                    self._vexy.register(capability)
            except Exception as e:
                self.logger.error(
                    f"Failed to load capability '{name}': {e}",
                    emoji="❌"
                )
                # Continue loading other capabilities
                continue

        self.logger.info(
            f"Loaded {len(self._vexy._capabilities)} capabilities",
            emoji="📦"
        )

    def _load_capability(self, name: str) -> Optional[BaseCapability]:
        """
        Load a capability class by name.

        Args:
            name: Capability name (e.g., "chat", "journal")

        Returns:
            Instantiated capability, or None if not found
        """
        # Check registry for module path
        module_path = CAPABILITY_REGISTRY.get(name)

        if not module_path:
            self.logger.debug(f"Capability '{name}' not in registry, skipping")
            return None

        try:
            # Parse module path: "capabilities.chat.capability.ChatCapability"
            parts = module_path.rsplit(".", 1)
            module_name = f"services.vexy_ai.{parts[0]}"
            class_name = parts[1]

            # Import module
            module = importlib.import_module(module_name)

            # Get capability class
            cap_class: Type[BaseCapability] = getattr(module, class_name)

            # Instantiate with Vexy reference
            return cap_class(self._vexy)

        except (ImportError, AttributeError) as e:
            self.logger.warn(
                f"Could not load capability '{name}': {e}",
                emoji="⚠️"
            )
            return None

    async def shutdown(self) -> None:
        """
        Clean shutdown of all components.

        Closes connections and releases resources in reverse order.
        """
        self.logger.info("Container shutting down...", emoji="🔌")

        # Stop Vexy (stops all capabilities)
        if self._vexy:
            await self._vexy.stop()
            self._vexy = None

        # Close bus connections
        if self._bus_adapter:
            await self._bus_adapter.close()
            self._bus_adapter = None

        # AI adapter doesn't need cleanup (stateless)
        self._ai_adapter = None

        self._initialized = False
        self.logger.info("Container shutdown complete", emoji="✓")

    @property
    def vexy(self) -> Optional[Vexy]:
        """Get the Vexy instance (None if not wired)."""
        return self._vexy

    @property
    def is_initialized(self) -> bool:
        """Check if container has been successfully wired."""
        return self._initialized
