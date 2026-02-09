"""
Commentary Capability - Vexy Play-by-Play commentary engine.

Handles epoch-based and event-driven market commentary,
publishing to market-redis for real-time subscribers.
"""

from .capability import CommentaryCapability

__all__ = ["CommentaryCapability"]
