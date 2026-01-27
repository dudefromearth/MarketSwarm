"""
Normalizer Registry

Defines the ordered fan-out of chain snapshot normalizers.

Each normalizer:
- consumes a raw chain snapshot
- writes model-specific input artifacts
- does NOT compute models
"""

from typing import List, Callable

from .heatmap import normalize_chain_snapshot_for_heatmap
from .gex import normalize_chain_snapshot_for_gex


# Ordered list matters only for logging / observability.
# There are no data dependencies between normalizers.
NORMALIZERS: List[Callable] = [
    normalize_chain_snapshot_for_heatmap,
    normalize_chain_snapshot_for_gex,
]