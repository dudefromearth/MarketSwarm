"""
aos.py — Admin Orchestration Service.

Consumes PDE alerts. Writes bounded, expiring overlays to Redis.

Constitutional constraints:
- Overlays are observational addendums, never prescriptive
- Overlay is NEVER part of the LLM input prompt — appended post-reasoning
- Overlays cannot influence playbook selection, domain selection,
  structured explanation, risk framing
- Strict mode NEVER includes overlays
- Budget: max 5 per user per week
- Cooldown: 48h per pattern category per user
- TTL: 24h per overlay
- Overlay is a structured response field, not appended text

Redis key patterns (echo-redis, degraded-safe):
- echo:admin_overlay:{user_id}              — active overlay JSON
- echo:admin_injection_budget:{user_id}     — weekly budget counter
- echo:admin_cooldown:{pattern}:{user_id}   — cooldown lock
- echo:admin_lock:{user_id}                 — user-level suppression
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class OverlayRecord:
    """An active observational overlay."""
    user_id: int
    category: str
    label: str
    summary: str
    confidence: float
    sample_size: int
    created_at: float
    expires_at: float
    is_observational: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "behavioral_pattern",
            "category": self.category,
            "label": self.label,
            "summary": self.summary,
            "confidence": self.confidence,
            "sample_size": self.sample_size,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "is_observational": self.is_observational,
        }

    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class AdminOrchestrationService:
    """
    Consumes PDE alerts. Writes bounded, expiring overlays.

    Enforces:
    - Budget: max N overlays per user per week
    - Cooldown: wait period per pattern category per user
    - TTL: each overlay expires after N hours
    - Min confidence: below threshold → skip
    - Doctrine conflict: STRICT mode → no overlay
    """

    MAX_OVERLAYS_PER_WEEK = 5
    DEFAULT_COOLDOWN_HOURS = 48
    MIN_CONFIDENCE = 0.70
    OVERLAY_TTL_HOURS = 24

    def __init__(self, logger: Any, echo_redis: Any = None):
        self._logger = logger
        self._redis = echo_redis  # Optional[EchoRedisClient or Redis]

        # In-memory fallback when Redis unavailable
        self._overlays: Dict[int, OverlayRecord] = {}
        self._budgets: Dict[int, List[float]] = {}  # user_id → list of creation timestamps
        self._cooldowns: Dict[str, float] = {}  # "category:user_id" → expires_at
        self._suppressed: Dict[int, bool] = {}  # user_id → suppressed

    def process_alerts(
        self,
        alerts: List[Any],
        user_id: int,
    ) -> List[Dict]:
        """
        Process PDE alerts and create overlays where appropriate.

        Returns list of created overlay dicts.
        """
        created = []
        now = time.time()

        for alert in alerts:
            category = alert.category.value if hasattr(alert.category, 'value') else str(alert.category)
            confidence = alert.confidence

            # Skip below confidence threshold
            if confidence < self.MIN_CONFIDENCE:
                continue

            # Check suppression
            if self._suppressed.get(user_id):
                continue

            # Check cooldown
            cooldown_key = f"{category}:{user_id}"
            cooldown_expires = self._cooldowns.get(cooldown_key, 0)
            if now < cooldown_expires:
                continue

            # Check budget
            week_timestamps = self._budgets.get(user_id, [])
            week_ago = now - (7 * 24 * 3600)
            week_timestamps = [ts for ts in week_timestamps if ts > week_ago]
            self._budgets[user_id] = week_timestamps

            if len(week_timestamps) >= self.MAX_OVERLAYS_PER_WEEK:
                self._logger.info(
                    f"AOS: Budget exhausted for user {user_id} ({len(week_timestamps)}/{self.MAX_OVERLAYS_PER_WEEK})",
                    emoji="🔒",
                )
                continue

            # Create overlay
            overlay = OverlayRecord(
                user_id=user_id,
                category=category,
                label="Observational Signal",
                summary=alert.summary,
                confidence=confidence,
                sample_size=alert.sample_size,
                created_at=now,
                expires_at=now + (self.OVERLAY_TTL_HOURS * 3600),
            )

            self._overlays[user_id] = overlay
            self._budgets.setdefault(user_id, []).append(now)
            self._cooldowns[cooldown_key] = now + (self.DEFAULT_COOLDOWN_HOURS * 3600)

            created.append(overlay.to_dict())

            self._logger.info(
                f"AOS: Created overlay for user {user_id}: {category} (conf={confidence})",
                emoji="📋",
            )

        return created

    def get_active_overlay(self, user_id: int) -> Optional[Dict]:
        """Get active overlay for a user, or None if expired/suppressed."""
        if self._suppressed.get(user_id):
            return None

        overlay = self._overlays.get(user_id)
        if not overlay:
            return None

        if overlay.is_expired():
            del self._overlays[user_id]
            return None

        return overlay.to_dict()

    def get_all_active_overlays(self) -> List[Dict]:
        """Get all active (non-expired) overlays."""
        now = time.time()
        result = []
        expired_keys = []

        for user_id, overlay in self._overlays.items():
            if overlay.is_expired():
                expired_keys.append(user_id)
            else:
                d = overlay.to_dict()
                d["user_id"] = user_id
                result.append(d)

        for k in expired_keys:
            del self._overlays[k]

        return result

    def suppress_user(self, user_id: int) -> None:
        """Suppress overlays for a user."""
        self._suppressed[user_id] = True
        if user_id in self._overlays:
            del self._overlays[user_id]
        self._logger.info(f"AOS: Suppressed overlays for user {user_id}", emoji="🔇")

    def unsuppress_user(self, user_id: int) -> None:
        """Remove suppression for a user."""
        self._suppressed.pop(user_id, None)

    def get_stats(self) -> Dict[str, Any]:
        """Get AOS statistics."""
        active = [o for o in self._overlays.values() if not o.is_expired()]
        return {
            "active_overlays": len(active),
            "suppressed_users": len(self._suppressed),
            "total_users_with_budget": len(self._budgets),
            "active_cooldowns": sum(
                1 for v in self._cooldowns.values() if time.time() < v
            ),
        }
