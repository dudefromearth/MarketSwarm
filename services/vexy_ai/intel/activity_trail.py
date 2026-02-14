"""
ActivityTrail — Record user actions to Echo Redis for behavioral context.

Writes to: echo:activity:{user_id}:{date} sorted set (48h TTL)

Per-event fields:
- surface: which UI surface (chat, routine, process, risk_graph, etc.)
- feature: specific feature used (chat_send, routine_check, position_open, etc.)
- action_type: verb (interact, navigate, configure, trade)
- action_detail: short description
- duration_seconds: time spent (optional, 0 if instant)
- context_tags: list of contextual tags
- tier: user tier at time of action
"""

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .echo_redis import EchoRedisClient


class ActivityTrail:
    """Records user actions to the echo hot tier."""

    def __init__(self, echo_client: EchoRedisClient, logger: Any):
        self._echo = echo_client
        self._logger = logger

    async def record(
        self,
        user_id: int,
        surface: str,
        feature: str,
        action_type: str,
        tier: str,
        action_detail: str = "",
        duration_seconds: float = 0.0,
        context_tags: Optional[List[str]] = None,
    ) -> bool:
        """
        Record a user action event.

        Returns True if recorded, False if echo unavailable or error.
        """
        if not self._echo.available:
            return False

        action = {
            "ts": time.time(),
            "surface": surface,
            "feature": feature,
            "action_type": action_type,
            "action_detail": action_detail,
            "duration_seconds": round(duration_seconds, 1),
            "context_tags": context_tags or [],
            "tier": tier,
        }

        return await self._echo.write_activity(user_id, action)
