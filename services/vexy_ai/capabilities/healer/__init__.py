"""
Healer Capability - Self-healing for MarketSwarm services.

Subscribes to ServiceUnhealthy events and executes healing protocols
to restore service health automatically.
"""

from .capability import HealerCapability

__all__ = ["HealerCapability"]
