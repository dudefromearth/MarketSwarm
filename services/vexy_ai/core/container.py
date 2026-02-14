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

import asyncio
import importlib
import os
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
    "interaction": "capabilities.interaction.capability.InteractionCapability",
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

        # Cognitive Kernel components
        self._path_runtime = None
        self._kernel = None
        self._echo_client = None

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

            # 2.5 Create shared MarketIntelProvider
            from ..market_intel import MarketIntelProvider
            self._market_intel = MarketIntelProvider(self.config, self.logger)
            self._market_intel.initialize()

            # 2.6 Create Echo Redis client (degraded-safe)
            self._echo_client = self._create_echo_client()

            # 2.7 Create PathRuntime and VexyKernel (Cognitive Kernel v1)
            self._path_runtime, self._kernel = self._create_kernel()

            # 3. Create Vexy core
            self._vexy = Vexy(
                config=self.config,
                logger=self.logger,
                buses=self._bus_adapter,
                ai=self._ai_adapter,
                market_intel=self._market_intel,
            )

            # Attach kernel to Vexy so capabilities can access it
            self._vexy.kernel = self._kernel

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

    def _create_echo_client(self):
        """Create the Echo Redis client (degraded-safe)."""
        try:
            from ..intel.echo_redis import EchoRedisClient
            echo_redis = self._bus_adapter.echo  # Optional[Redis], None if unavailable
            client = EchoRedisClient(echo_redis, self.logger)
            if client.available:
                self.logger.info("Echo Redis client ready", emoji="🧠")
            else:
                self.logger.warn("Echo Redis client in degraded mode", emoji="⚠️")
            return client
        except Exception as e:
            self.logger.warn(f"Echo client creation failed (degraded mode): {e}", emoji="⚠️")
            from ..intel.echo_redis import EchoRedisClient
            return EchoRedisClient(None, self.logger)

    def _create_kernel(self):
        """Create PathRuntime + VexyKernel (Cognitive Kernel v1)."""
        from ..intel.path_runtime import PathRuntime
        from ..kernel import VexyKernel, ValidationMode

        # Path doctrine directory — configurable, defaults to ~/path
        path_dir = self.config.get("PATH_DOCTRINE_DIR") or str(
            os.path.expanduser("~/path")
        )

        path_runtime = PathRuntime(path_dir=path_dir, logger=self.logger)
        try:
            path_runtime.load()
        except FileNotFoundError as e:
            self.logger.warn(f"PathRuntime load failed (non-fatal): {e}", emoji="⚠️")
            # Create a minimal runtime that won't block startup
            # Capabilities can still function without full doctrine

        # Default to OBSERVE mode during rollout
        mode_str = (
            self.config.get("env", {}).get("VEXY_VALIDATION_MODE", "observe")
            if isinstance(self.config.get("env"), dict)
            else os.getenv("VEXY_VALIDATION_MODE", "observe")
        )
        validation_mode = (
            ValidationMode.ENFORCE
            if mode_str.lower() == "enforce"
            else ValidationMode.OBSERVE
        )

        kernel = VexyKernel(
            path_runtime=path_runtime,
            config=self.config,
            logger=self.logger,
            market_intel=self._market_intel,
            validation_mode=validation_mode,
            echo_client=self._echo_client,
        )

        self.logger.info(
            f"Cognitive Kernel ready (mode={validation_mode.value})",
            emoji="🧠"
        )
        return path_runtime, kernel

    def _register_health_routes(self) -> None:
        """Register basic health check, status, and market-state routes."""
        from fastapi import APIRouter

        router = APIRouter()

        @router.get("/health")
        async def health():
            return {"status": "healthy", "service": "vexy_ai"}

        @router.get("/api/vexy/status")
        async def status():
            return self._vexy.get_status()

        self._vexy.app.include_router(router)

        # Market-state route owned by MarketIntelProvider
        self._market_intel.register_routes(self._vexy.app)

        # Register admin routes (prompt management)
        from ..adapters.http.routes.admin import create_admin_router
        admin_router = create_admin_router()
        self._vexy.app.include_router(admin_router)

        # Start RSS relevance scoring background loop
        @self._vexy.app.on_event("startup")
        async def _start_rss_relevance():
            task = asyncio.create_task(self._rss_relevance_loop())
            self._vexy._background_tasks.append(task)

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

        # Clean up MarketIntelProvider
        if hasattr(self, '_market_intel') and self._market_intel:
            self._market_intel.shutdown()
            self._market_intel = None

        # AI adapter doesn't need cleanup (stateless)
        self._ai_adapter = None

        self._initialized = False
        self.logger.info("Container shutdown complete", emoji="✓")

    async def _rss_relevance_loop(self) -> None:
        """Background task: score RSS articles for SoM relevance every 60s."""
        await asyncio.sleep(10)  # Let other services start first

        while True:
            try:
                import redis as sync_redis
                from services.vexy_ai.intel.rss_relevance import RSSRelevanceEngine

                buses = self.config.get("buses", {}) or {}
                intel_url = buses.get("intel-redis", {}).get("url", "redis://127.0.0.1:6381")
                market_url = buses.get("market-redis", {}).get("url", "redis://127.0.0.1:6380")

                r_intel = sync_redis.from_url(intel_url, decode_responses=True)
                r_market = sync_redis.from_url(market_url, decode_responses=True)

                engine = RSSRelevanceEngine(r_intel, r_market, self.logger)
                engine.score_and_cache()
            except Exception as e:
                self.logger.warning(f"RSS relevance loop error: {e}", emoji="⚠️")

            await asyncio.sleep(60)

    @property
    def vexy(self) -> Optional[Vexy]:
        """Get the Vexy instance (None if not wired)."""
        return self._vexy

    @property
    def kernel(self):
        """Get the VexyKernel instance (None if not wired)."""
        return self._kernel

    @property
    def path_runtime(self):
        """Get the PathRuntime instance (None if not wired)."""
        return self._path_runtime

    @property
    def is_initialized(self) -> bool:
        """Check if container has been successfully wired."""
        return self._initialized
