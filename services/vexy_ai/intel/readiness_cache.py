"""
ReadinessCache — Capture daily readiness state to Echo Redis.

Writes to: echo:readiness:{user_id}:{date} (24h TTL)

Readiness fields:
- sleep: quality (short, adequate, strong)
- focus: state (scattered, centered)
- distractions: level (low, medium, high)
- body_state: energy (tight, neutral, energized)
- friction: level (low, medium, high)
- notes: optional free-text
"""

from typing import Any, Dict, Optional

from .echo_redis import EchoRedisClient


class ReadinessCache:
    """Manages daily readiness data in the echo hot tier."""

    def __init__(self, echo_client: EchoRedisClient, logger: Any):
        self._echo = echo_client
        self._logger = logger

    async def store(
        self,
        user_id: int,
        readiness: Dict[str, Any],
    ) -> bool:
        """
        Store daily readiness data.

        Args:
            user_id: User ID
            readiness: Dict with keys: sleep, focus, distractions, body_state, friction, notes

        Returns True if stored, False if echo unavailable.
        """
        if not self._echo.available:
            return False

        return await self._echo.write_readiness(user_id, readiness)

    async def get_today(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get today's readiness data for a user."""
        return await self._echo.read_readiness(user_id)
