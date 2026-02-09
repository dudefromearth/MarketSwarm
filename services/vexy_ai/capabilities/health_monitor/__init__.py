"""
Health Monitor Capability - Service health tracking for MarketSwarm.

Monitors heartbeats from all services via system-redis,
tracks consecutive failures, and publishes ServiceUnhealthy events.
"""

from .capability import HealthMonitorCapability

__all__ = ["HealthMonitorCapability"]
