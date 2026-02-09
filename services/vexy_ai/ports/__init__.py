"""
Ports - Abstract interfaces for external systems.

Ports define the contracts that adapters must implement.
This allows swapping implementations (e.g., Redis for mock in tests).
"""

from .bus import BusPort
from .ai import AIPort

__all__ = ["BusPort", "AIPort"]
