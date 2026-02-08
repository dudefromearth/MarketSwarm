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
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
import pytz

from .log_health_analyzer import LogHealthAnalyzer, store_routine_context

ET = pytz.timezone("America/New_York")

# API endpoints
JOURNAL_API_BASE = os.getenv("JOURNAL_API_BASE", "http://localhost:3001")
VEXY_API_BASE = os.getenv("VEXY_API_BASE", "http://localhost:3005")


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


# CLI entry point for cron/systemd
if __name__ == "__main__":
    import sys
    from pathlib import Path

    # Ensure MarketSwarm root is on sys.path
    ROOT = Path(__file__).resolve().parents[3]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    async def main():
        result = await run_log_health_analyzer()
        print(f"Job completed: {result}")

    asyncio.run(main())
