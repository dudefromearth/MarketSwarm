"""
EchoRedisClient — Domain-specific API for all Echo Redis operations.

Handles degraded mode gracefully: returns None/empty when echo-redis
is unavailable. All operations are non-blocking to the caller.

Key patterns:
- echo:hot:{user_id}:conversations      — sorted set of trimmed conversation exchanges
- echo:hot:{user_id}:session             — current session echo state
- echo:hot:{user_id}:surface_state       — latest surface context
- echo:hot:{user_id}:micro_signals       — sorted set of micro signals
- echo:activity:{user_id}:{date}         — sorted set of user actions (48h TTL)
- echo:readiness:{user_id}:{date}        — hash of daily readiness (24h TTL)
- echo:warm_snapshot:{user_id}           — hydrator-built cognition snapshot (read-only)
- echo:system:routine_data:{category}    — system-level market data summaries
"""

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from redis.asyncio import Redis


SESSION_ECHO_TTL = 86400       # 24h
CONVERSATION_TTL = 86400 * 2   # 48h
SURFACE_STATE_TTL = 3600       # 1h
MICRO_SIGNAL_TTL = 86400       # 24h


class EchoRedisClient:
    """Domain-specific Echo Redis API with degraded-mode safety."""

    def __init__(self, echo_redis: Optional[Redis], logger: Any):
        """
        Args:
            echo_redis: Async Redis client for echo bus, or None if unavailable.
            logger: LogUtil instance.
        """
        self._redis = echo_redis
        self._logger = logger

    @property
    def available(self) -> bool:
        """Whether echo-redis is connected."""
        return self._redis is not None

    # ── Session Echo ─────────────────────────────────────────────

    async def write_session_echo(self, user_id: int, echo_data: Dict[str, Any]) -> bool:
        """Write session echo state (biases, tensions, threads, signals)."""
        if not self._redis:
            return False
        try:
            key = f"echo:hot:{user_id}:session"
            await self._redis.set(key, json.dumps(echo_data), ex=SESSION_ECHO_TTL)
            return True
        except Exception as e:
            self._logger.warning(f"Echo write_session_echo failed: {e}")
            return False

    async def read_session_echo(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Read current session echo state."""
        if not self._redis:
            return None
        try:
            key = f"echo:hot:{user_id}:session"
            raw = await self._redis.get(key)
            return json.loads(raw) if raw else None
        except Exception as e:
            self._logger.warning(f"Echo read_session_echo failed: {e}")
            return None

    # ── Conversations ────────────────────────────────────────────

    async def write_conversation(
        self,
        user_id: int,
        exchange: Dict[str, Any],
        max_conversations: int = 15,
    ) -> bool:
        """
        Add a trimmed conversation exchange to the sorted set.

        Args:
            user_id: User ID
            exchange: Dict with keys: ts, surface, user_message, vexy_response, tags
            max_conversations: Max exchanges to keep (tier-dependent)
        """
        if not self._redis:
            return False
        try:
            key = f"echo:hot:{user_id}:conversations"
            score = exchange.get("ts", time.time())
            await self._redis.zadd(key, {json.dumps(exchange): score})
            await self._redis.expire(key, CONVERSATION_TTL)

            # Trim to max
            count = await self._redis.zcard(key)
            if count > max_conversations:
                await self._redis.zremrangebyrank(key, 0, count - max_conversations - 1)

            return True
        except Exception as e:
            self._logger.warning(f"Echo write_conversation failed: {e}")
            return False

    async def read_conversations(self, user_id: int, limit: int = 15) -> List[Dict[str, Any]]:
        """Read recent conversation exchanges (newest first)."""
        if not self._redis:
            return []
        try:
            key = f"echo:hot:{user_id}:conversations"
            raw_list = await self._redis.zrevrange(key, 0, limit - 1)
            return [json.loads(item) for item in raw_list]
        except Exception as e:
            self._logger.warning(f"Echo read_conversations failed: {e}")
            return []

    # ── Surface State ────────────────────────────────────────────

    async def write_surface_state(self, user_id: int, surface_data: Dict[str, Any]) -> bool:
        """Write latest surface context (what UI surface user is on)."""
        if not self._redis:
            return False
        try:
            key = f"echo:hot:{user_id}:surface_state"
            await self._redis.set(key, json.dumps(surface_data), ex=SURFACE_STATE_TTL)
            return True
        except Exception as e:
            self._logger.warning(f"Echo write_surface_state failed: {e}")
            return False

    # ── Micro Signals ────────────────────────────────────────────

    async def write_micro_signal(self, user_id: int, signal: Dict[str, Any]) -> bool:
        """Write a micro signal (bias detected, tension surfaced, etc.)."""
        if not self._redis:
            return False
        try:
            key = f"echo:hot:{user_id}:micro_signals"
            score = signal.get("ts", time.time())
            await self._redis.zadd(key, {json.dumps(signal): score})
            await self._redis.expire(key, MICRO_SIGNAL_TTL)

            # Cap at 100 micro signals
            count = await self._redis.zcard(key)
            if count > 100:
                await self._redis.zremrangebyrank(key, 0, count - 101)

            return True
        except Exception as e:
            self._logger.warning(f"Echo write_micro_signal failed: {e}")
            return False

    # ── Activity Trail ───────────────────────────────────────────

    async def write_activity(
        self,
        user_id: int,
        action: Dict[str, Any],
    ) -> bool:
        """Write an activity trail entry."""
        if not self._redis:
            return False
        try:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            key = f"echo:activity:{user_id}:{date_str}"
            score = action.get("ts", time.time())
            await self._redis.zadd(key, {json.dumps(action): score})
            await self._redis.expire(key, 86400 * 2)  # 48h TTL
            return True
        except Exception as e:
            self._logger.warning(f"Echo write_activity failed: {e}")
            return False

    # ── Readiness ────────────────────────────────────────────────

    async def write_readiness(self, user_id: int, readiness: Dict[str, Any]) -> bool:
        """Write daily readiness data."""
        if not self._redis:
            return False
        try:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            key = f"echo:readiness:{user_id}:{date_str}"
            await self._redis.set(key, json.dumps(readiness), ex=86400)
            return True
        except Exception as e:
            self._logger.warning(f"Echo write_readiness failed: {e}")
            return False

    async def read_readiness(self, user_id: int, date_str: str = None) -> Optional[Dict[str, Any]]:
        """Read daily readiness data."""
        if not self._redis:
            return None
        try:
            if not date_str:
                date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            key = f"echo:readiness:{user_id}:{date_str}"
            raw = await self._redis.get(key)
            return json.loads(raw) if raw else None
        except Exception as e:
            self._logger.warning(f"Echo read_readiness failed: {e}")
            return None

    # ── Hot-Tier Flush (post-consolidation cleanup) ──────────────

    async def flush_user_hot_data(self, user_id: int, date_str: str) -> int:
        """Delete processed hot-tier keys after consolidation.

        Returns number of keys deleted.
        """
        if not self._redis:
            return 0
        keys_to_delete = [
            f"echo:hot:{user_id}:conversations",
            f"echo:hot:{user_id}:session",
            f"echo:hot:{user_id}:micro_signals",
            f"echo:activity:{user_id}:{date_str}",
            f"echo:readiness:{user_id}:{date_str}",
        ]
        deleted = 0
        for key in keys_to_delete:
            try:
                deleted += await self._redis.delete(key)
            except Exception:
                pass
        return deleted

    # ── Warm Snapshot (read-only — written by hydrator) ──────────

    async def read_warm_snapshot(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Read the hydrator-built cognition snapshot."""
        if not self._redis:
            return None
        try:
            key = f"echo:warm_snapshot:{user_id}"
            raw = await self._redis.get(key)
            return json.loads(raw) if raw else None
        except Exception as e:
            self._logger.warning(f"Echo read_warm_snapshot failed: {e}")
            return None

    # ── Routine Data (read-only — written by hydrator) ───────────

    async def read_routine_data(self, category: str) -> Optional[Dict[str, Any]]:
        """Read system-level routine data by category."""
        if not self._redis:
            return None
        try:
            key = f"echo:system:routine_data:{category}"
            raw = await self._redis.get(key)
            return json.loads(raw) if raw else None
        except Exception as e:
            self._logger.warning(f"Echo read_routine_data failed: {e}")
            return None
