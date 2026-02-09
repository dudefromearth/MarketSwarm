"""
Vexy Core - The brain of MarketSwarm.

This package contains the core domain logic, capability orchestration,
and event system that powers Vexy's central nervous system.
"""

from .vexy import Vexy
from .capability import BaseCapability
from .events import DomainEvent
from .container import Container

__all__ = ["Vexy", "BaseCapability", "DomainEvent", "Container"]
