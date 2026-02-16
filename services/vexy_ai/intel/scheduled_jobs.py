#!/usr/bin/env python3
"""
scheduled_jobs.py — Scheduled jobs for Vexy AI

Contains jobs that run on schedule:
- log_health_analyzer: Daily at 05:00 ET

These jobs can be invoked via cron, systemd timer, or the orchestrator.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
import pytz

from .log_health_analyzer import LogHealthAnalyzer, store_routine_context

ET = pytz.timezone("America/New_York")

# API endpoints
JOURNAL_API_BASE = os.getenv("JOURNAL_API_BASE", "http://localhost:3002")
VEXY_API_BASE = os.getenv("VEXY_API_BASE", "http://localhost:3005")


def _load_journal_db_config() -> Dict[str, str]:
    """Load journal MySQL config from env vars, falling back to truth in system-redis."""
    password = os.getenv("JOURNAL_MYSQL_PASSWORD", "")
    if password:
        # Env vars already set (running inside a service with SetupBase)
        return {
            "JOURNAL_MYSQL_HOST": os.getenv("JOURNAL_MYSQL_HOST", "localhost"),
            "JOURNAL_MYSQL_PORT": os.getenv("JOURNAL_MYSQL_PORT", "3306"),
            "JOURNAL_MYSQL_USER": os.getenv("JOURNAL_MYSQL_USER", "journal"),
            "JOURNAL_MYSQL_PASSWORD": password,
            "JOURNAL_MYSQL_DATABASE": os.getenv("JOURNAL_MYSQL_DATABASE", "journal"),
        }

    # Fallback: read from truth in system-redis (CLI / standalone usage)
    import json
    import redis as sync_redis
    try:
        r = sync_redis.from_url("redis://127.0.0.1:6379", decode_responses=True)
        raw = r.get("truth")
        r.close()
        if raw:
            truth = json.loads(raw)
            journal_env = truth.get("components", {}).get("journal", {}).get("env", {})
            return {
                "JOURNAL_MYSQL_HOST": journal_env.get("JOURNAL_MYSQL_HOST", "localhost"),
                "JOURNAL_MYSQL_PORT": journal_env.get("JOURNAL_MYSQL_PORT", "3306"),
                "JOURNAL_MYSQL_USER": journal_env.get("JOURNAL_MYSQL_USER", "journal"),
                "JOURNAL_MYSQL_PASSWORD": journal_env.get("JOURNAL_MYSQL_PASSWORD", ""),
                "JOURNAL_MYSQL_DATABASE": journal_env.get("JOURNAL_MYSQL_DATABASE", "journal"),
            }
    except Exception:
        pass

    # Last resort: defaults (will likely fail auth)
    return {
        "JOURNAL_MYSQL_HOST": "localhost",
        "JOURNAL_MYSQL_PORT": "3306",
        "JOURNAL_MYSQL_USER": "journal",
        "JOURNAL_MYSQL_PASSWORD": "",
        "JOURNAL_MYSQL_DATABASE": "journal",
    }


async def get_all_user_ids() -> List[int]:
    """
    Fetch all user IDs from the Journal API.

    In production, this would query the users table.
    For now, we fetch distinct user_ids from trade_logs.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # This endpoint should return all user IDs that have trade logs
            response = await client.get(f"{JOURNAL_API_BASE}/api/users/with-logs")
            if response.status_code == 200:
                data = response.json()
                return data.get("user_ids", [])
            else:
                # Fallback: return empty list if endpoint doesn't exist
                return []
    except Exception as e:
        print(f"[scheduled_jobs] Error fetching user IDs: {e}")
        return []


async def run_log_health_analyzer(
    logger=None,
    user_ids: Optional[List[int]] = None
) -> Dict[str, Any]:
    """
    Run the log health analyzer for all users.

    This is the main entry point for the scheduled job.

    Args:
        logger: Optional logger instance
        user_ids: Optional list of user IDs to analyze (for testing)

    Returns:
        Summary of the job execution
    """
    start_time = datetime.now(ET)

    def _log(level: str, msg: str):
        if logger:
            getattr(logger, level, logger.info)(msg, emoji="📊")
        else:
            print(f"[{level.upper()}] {msg}")

    _log("info", f"Starting log_health_analyzer at {start_time.strftime('%H:%M:%S ET')}")

    # Get user IDs if not provided
    if user_ids is None:
        user_ids = await get_all_user_ids()

    if not user_ids:
        _log("warn", "No users found to analyze")
        return {
            "success": True,
            "users_processed": 0,
            "contexts_generated": 0,
            "duration_ms": 0,
        }

    _log("info", f"Analyzing logs for {len(user_ids)} users")

    # Create analyzer
    analyzer = LogHealthAnalyzer(JOURNAL_API_BASE, logger)

    # Run analysis for all users
    contexts = await analyzer.run_for_all_users(user_ids)

    # Post contexts to Vexy API (or store directly)
    contexts_stored = 0
    for context in contexts:
        try:
            # Store locally first
            store_routine_context(
                context["user_id"],
                context["routine_date"],
                context
            )

            # Also post to Vexy API for redundancy (optional)
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{VEXY_API_BASE}/api/vexy/context/log-health",
                    json=context,
                )
                if response.status_code == 200:
                    contexts_stored += 1
        except Exception as e:
            _log("error", f"Failed to store context for user {context.get('user_id')}: {e}")

    end_time = datetime.now(ET)
    duration_ms = int((end_time - start_time).total_seconds() * 1000)

    summary = {
        "success": True,
        "users_processed": len(user_ids),
        "contexts_generated": len(contexts),
        "contexts_stored": contexts_stored,
        "duration_ms": duration_ms,
        "started_at": start_time.isoformat(),
        "finished_at": end_time.isoformat(),
    }

    _log("info", f"Completed: {len(contexts)} contexts in {duration_ms}ms")

    return summary


async def run_echo_consolidation(logger=None) -> Dict[str, Any]:
    """
    Run Hot→Warm echo consolidation for all active users.

    Creates its own async echo-redis + MySQL connections.
    Triggered daily at 17:30 ET by hydrator or manual CLI.
    """
    start_time = datetime.now(ET)

    def _log(level: str, msg: str):
        if logger:
            getattr(logger, level, logger.info)(msg, emoji="🔄")
        else:
            print(f"[{level.upper()}] {msg}")

    _log("info", f"Starting echo consolidation at {start_time.strftime('%H:%M:%S ET')}")

    # 1. Discover users via journal API
    user_ids = await get_all_user_ids()
    if not user_ids:
        _log("warn", "No users found for consolidation")
        return {
            "success": True,
            "users_processed": 0,
            "users_consolidated": 0,
            "total_conversations": 0,
            "total_activities": 0,
            "flagged_compression": 0,
            "duration_ms": 0,
        }

    _log("info", f"Consolidating echo data for {len(user_ids)} users")

    # 2. Create async echo-redis client
    import redis.asyncio as aioredis
    echo_url = os.getenv("ECHO_REDIS_URL", "redis://127.0.0.1:6382")
    async_redis = aioredis.from_url(echo_url, decode_responses=True)

    # 3. Create MySQL connection (JournalDBv2)
    #    Env vars are set by SetupBase when running inside hydrator.
    #    For CLI usage, fall back to reading truth from system-redis.
    from services.journal.intel.db_v2 import JournalDBv2
    db_config = _load_journal_db_config()
    db = JournalDBv2(db_config)

    # 4. Create EchoRedisClient + EchoConsolidator
    from services.vexy_ai.intel.echo_redis import EchoRedisClient
    from services.vexy_ai.intel.echo_consolidation import EchoConsolidator
    echo_client = EchoRedisClient(async_redis, logger or _default_logger())
    consolidator = EchoConsolidator(echo_client, db, logger or _default_logger())

    # 5. Consolidate each user
    results = []
    all_activities: Dict[int, List] = {}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for user_id in user_ids:
        try:
            result = await consolidator.consolidate_user(user_id)
            results.append(result)
            # Collect activities for system analytics
            activities = await consolidator._read_activities(user_id, today)
            if activities:
                all_activities[user_id] = activities
        except Exception as e:
            results.append({"user_id": user_id, "errors": [str(e)]})

    # 6. System analytics
    if all_activities:
        await consolidator.consolidate_system_analytics(all_activities)

    # 7. Cleanup
    await async_redis.aclose()

    # Summary
    duration_ms = int((datetime.now(ET) - start_time).total_seconds() * 1000)
    summary = {
        "success": True,
        "users_processed": len(user_ids),
        "users_consolidated": sum(1 for r in results if not r.get("errors")),
        "total_conversations": sum(r.get("conversations_promoted", 0) for r in results),
        "total_activities": sum(r.get("activities_promoted", 0) for r in results),
        "flagged_compression": sum(1 for r in results if r.get("flagged")),
        "duration_ms": duration_ms,
    }

    _log("info", f"Consolidation complete: {summary['users_consolidated']}/{summary['users_processed']} users, "
         f"{summary['total_conversations']} convs, {summary['total_activities']} acts, {duration_ms}ms")

    return summary


class _DefaultLogger:
    """Minimal fallback logger for CLI usage."""
    def info(self, msg, **kw): print(f"[INFO] {msg}")
    def warning(self, msg, **kw): print(f"[WARN] {msg}")
    def error(self, msg, **kw): print(f"[ERROR] {msg}")
    def warn(self, msg, **kw): print(f"[WARN] {msg}")

def _default_logger():
    return _DefaultLogger()


# CLI entry point for cron/systemd
if __name__ == "__main__":
    import sys
    from pathlib import Path

    # Ensure MarketSwarm root is on sys.path
    ROOT = Path(__file__).resolve().parents[3]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    async def main():
        job = sys.argv[1] if len(sys.argv) > 1 else "log_health"
        if job == "consolidate":
            result = await run_echo_consolidation()
        else:
            result = await run_log_health_analyzer()
        print(f"Job completed: {result}")

    asyncio.run(main())
