"""
Mesh Capability - Multi-node Vexy communication.

Enables multiple Vexy instances to discover each other,
share events, and provide redundancy across the mesh.
"""

from .capability import MeshCapability

__all__ = ["MeshCapability"]
