"""
EchoConsolidator — Hot → Warm daily consolidation job.

Triggered post market close + buffer (17:30 ET):
1. Per user: read hot-tier Redis data
2. Filter noise, consolidate (4:1 min compression)
3. Write to warm MySQL tables
4. Flush processed hot-tier data
5. Feed anonymous aggregates to system_echo + analytics tables

Entropy contract: if compression ratio < 4:1, flag for review.
"""

import json
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .echo_redis import EchoRedisClient


class EchoConsolidator:
    """Consolidates hot-tier Echo Redis data to warm MySQL tier."""

    def __init__(
        self,
        echo_client: EchoRedisClient,
        db: Any,  # JournalDBv2 instance
        logger: Any,
    ):
        self._echo = echo_client
        self._db = db
        self._logger = logger

    async def consolidate_user(self, user_id: int) -> Dict[str, Any]:
        """
        Consolidate a single user's hot-tier data to warm MySQL.

        Returns dict with:
        - conversations_promoted: int
        - activities_promoted: int
        - readiness_stored: bool
        - compression_ratio: float
        - flagged: bool (True if compression < 4:1)
        """
        result = {
            "user_id": user_id,
            "conversations_promoted": 0,
            "activities_promoted": 0,
            "readiness_stored": False,
            "compression_ratio": 0.0,
            "flagged": False,
            "keys_flushed": 0,
            "errors": [],
        }

        if not self._echo.available:
            result["errors"].append("echo_unavailable")
            return result

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        total_hot_items = 0
        total_warm_items = 0

        # 1. Promote conversations
        try:
            conversations = await self._echo.read_conversations(user_id, limit=100)
            total_hot_items += len(conversations)

            consolidated = self._consolidate_conversations(conversations)
            total_warm_items += len(consolidated)

            for conv in consolidated:
                self._write_conversation_to_mysql(user_id, conv)

            result["conversations_promoted"] = len(consolidated)
        except Exception as e:
            result["errors"].append(f"conversations: {e}")

        # 2. Promote activity trail
        try:
            # Read today's activities from echo Redis
            activities = await self._read_activities(user_id, today)
            total_hot_items += len(activities)

            consolidated_activities = self._consolidate_activities(activities)
            total_warm_items += len(consolidated_activities)

            for act in consolidated_activities:
                self._write_activity_to_mysql(user_id, act)

            result["activities_promoted"] = len(consolidated_activities)
        except Exception as e:
            result["errors"].append(f"activities: {e}")

        # 3. Promote readiness
        try:
            readiness = await self._echo.read_readiness(user_id, today)
            if readiness:
                total_hot_items += 1
                total_warm_items += 1
                self._write_readiness_to_mysql(user_id, today, readiness)
                result["readiness_stored"] = True
        except Exception as e:
            result["errors"].append(f"readiness: {e}")

        # 4. Flush processed hot-tier keys
        if not result["errors"]:
            try:
                flushed = await self._echo.flush_user_hot_data(user_id, today)
                result["keys_flushed"] = flushed
            except Exception as e:
                result["errors"].append(f"flush: {e}")

        # 5. Compute compression ratio
        if total_warm_items > 0 and total_hot_items > 0:
            result["compression_ratio"] = round(total_hot_items / total_warm_items, 1)
            if result["compression_ratio"] < 4.0:
                result["flagged"] = True

        self._logger.info(
            f"Consolidated user {user_id}: "
            f"{result['conversations_promoted']} convs, "
            f"{result['activities_promoted']} acts, "
            f"ratio={result['compression_ratio']}"
        )

        return result

    async def consolidate_system_analytics(self, user_activities: Dict[int, List]) -> None:
        """
        Build anonymous system-level analytics from all users' activities.

        Writes to system_activity_analytics and system_flow_analytics tables.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        surface_stats: Dict[Tuple[str, str], Dict] = {}
        flow_patterns: Dict[Tuple[str, str], int] = {}

        for user_id, activities in user_activities.items():
            prev_surface = None
            for act in activities:
                surface = act.get("surface", "unknown")
                feature = act.get("feature", "unknown")
                key = (surface, feature)

                if key not in surface_stats:
                    surface_stats[key] = {
                        "count": 0,
                        "users": set(),
                        "total_duration": 0.0,
                    }

                surface_stats[key]["count"] += 1
                surface_stats[key]["users"].add(user_id)
                surface_stats[key]["total_duration"] += act.get("duration_seconds", 0.0)

                # Track flows
                if prev_surface and prev_surface != surface:
                    flow_key = (prev_surface, surface)
                    flow_patterns[flow_key] = flow_patterns.get(flow_key, 0) + 1
                prev_surface = surface

        # Write surface analytics
        for (surface, feature), stats in surface_stats.items():
            try:
                self._write_surface_analytics(
                    today, surface, feature,
                    stats["count"],
                    len(stats["users"]),
                    stats["total_duration"] / max(stats["count"], 1),
                )
            except Exception as e:
                self._logger.warning(f"Surface analytics write failed: {e}")

        # Write flow analytics (only patterns with >= 3 occurrences)
        for (from_s, to_s), count in flow_patterns.items():
            if count >= 3:
                try:
                    self._write_flow_analytics(today, from_s, to_s, count)
                except Exception as e:
                    self._logger.warning(f"Flow analytics write failed: {e}")

    # ── Consolidation helpers ────────────────────────────────────

    def _consolidate_conversations(self, conversations: List[Dict]) -> List[Dict]:
        """Merge same-surface conversations within short time windows."""
        if not conversations:
            return []
        # For Phase 2, pass through (future: merge same-surface within 5min windows)
        return conversations

    def _consolidate_activities(self, activities: List[Dict]) -> List[Dict]:
        """Deduplicate rapid-fire actions (same surface+feature within 5s)."""
        if not activities:
            return []

        consolidated = []
        prev = None
        for act in sorted(activities, key=lambda a: a.get("ts", 0)):
            if prev and (
                prev.get("surface") == act.get("surface")
                and prev.get("feature") == act.get("feature")
                and act.get("ts", 0) - prev.get("ts", 0) < 5.0
            ):
                # Merge: add duration
                prev["duration_seconds"] = prev.get("duration_seconds", 0) + act.get("duration_seconds", 0)
                continue
            consolidated.append(act)
            prev = act

        return consolidated

    async def _read_activities(self, user_id: int, date_str: str) -> List[Dict]:
        """Read activity trail from echo Redis for a given date."""
        if not self._echo._redis:
            return []
        try:
            key = f"echo:activity:{user_id}:{date_str}"
            raw_list = await self._echo._redis.zrange(key, 0, -1)
            return [json.loads(item) for item in raw_list]
        except Exception:
            return []

    # ── MySQL write helpers ──────────────────────────────────────

    def _write_conversation_to_mysql(self, user_id: int, conv: Dict) -> None:
        """Write a conversation to conversation_echo table."""
        conn = self._db._get_conn()
        cursor = conn.cursor()
        try:
            ts = conv.get("ts", time.time())
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            cursor.execute("""
                INSERT INTO conversation_echo
                    (user_id, conversation_ts, surface, outlet, user_message, vexy_response, context_tags)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                user_id,
                dt.strftime("%Y-%m-%d %H:%M:%S"),
                conv.get("surface", "chat"),
                conv.get("outlet", "chat"),
                conv.get("user_message", ""),
                conv.get("vexy_response", ""),
                json.dumps(conv.get("tags", [])),
            ))
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    def _write_activity_to_mysql(self, user_id: int, act: Dict) -> None:
        """Write an activity to user_activity_trail table."""
        conn = self._db._get_conn()
        cursor = conn.cursor()
        try:
            ts = act.get("ts", time.time())
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            cursor.execute("""
                INSERT INTO user_activity_trail
                    (user_id, activity_ts, surface, feature, action_type, action_detail,
                     duration_seconds, context_tags, tier)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                user_id,
                dt.strftime("%Y-%m-%d %H:%M:%S"),
                act.get("surface", ""),
                act.get("feature", ""),
                act.get("action_type", ""),
                act.get("action_detail", ""),
                act.get("duration_seconds", 0.0),
                json.dumps(act.get("context_tags", [])),
                act.get("tier", "observer"),
            ))
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    def _write_readiness_to_mysql(self, user_id: int, date_str: str, readiness: Dict) -> None:
        """Write readiness data to user_readiness_log table (upsert)."""
        conn = self._db._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO user_readiness_log
                    (user_id, readiness_date, sleep, focus, distractions, body_state, friction, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    sleep = VALUES(sleep),
                    focus = VALUES(focus),
                    distractions = VALUES(distractions),
                    body_state = VALUES(body_state),
                    friction = VALUES(friction),
                    notes = VALUES(notes)
            """, (
                user_id,
                date_str,
                readiness.get("sleep", ""),
                readiness.get("focus", ""),
                readiness.get("distractions", ""),
                readiness.get("body_state", ""),
                readiness.get("friction", ""),
                readiness.get("notes", ""),
            ))
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    def _write_surface_analytics(
        self, date_str: str, surface: str, feature: str,
        count: int, unique_users: int, avg_duration: float,
    ) -> None:
        """Write or update system_activity_analytics."""
        conn = self._db._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO system_activity_analytics
                    (analytics_date, surface, feature, action_count, unique_users, avg_duration_seconds)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    action_count = VALUES(action_count),
                    unique_users = VALUES(unique_users),
                    avg_duration_seconds = VALUES(avg_duration_seconds)
            """, (date_str, surface, feature, count, unique_users, round(avg_duration, 1)))
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    def _write_flow_analytics(
        self, date_str: str, from_surface: str, to_surface: str, count: int,
    ) -> None:
        """Write or update system_flow_analytics."""
        conn = self._db._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO system_flow_analytics
                    (flow_date, from_surface, to_surface, occurrence_count)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    occurrence_count = VALUES(occurrence_count)
            """, (date_str, from_surface, to_surface, count))
            conn.commit()
        finally:
            cursor.close()
            conn.close()
