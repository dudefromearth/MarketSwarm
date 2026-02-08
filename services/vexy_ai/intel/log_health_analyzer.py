#!/usr/bin/env python3
"""
log_health_analyzer.py — Trade Log Health Analysis for Vexy Routine Context

Scheduled daily at 05:00 ET, this module:
- Analyzes trade log health metrics per user
- Derives signals from metrics (inactive, stale imports, ML exclusion, etc.)
- Feeds context to Vexy for Routine Mode narratives

This is advisory only - never blocks actions.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import pytz
import httpx

ET = pytz.timezone("America/New_York")

# Signal severity levels
SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"

# Thresholds for signal derivation
INACTIVE_DAYS_THRESHOLD = 14
STALE_IMPORT_DAYS_THRESHOLD = 30
ACTIVE_LOG_SOFT_CAP = 5
RETIREMENT_WARNING_DAYS = 3


class LogHealthSignal:
    """A derived signal from log health metrics."""

    def __init__(
        self,
        signal_type: str,
        severity: str,
        value: Optional[Any] = None,
        message: str = "",
    ):
        self.type = signal_type
        self.severity = severity
        self.value = value
        self.message = message

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "type": self.type,
            "severity": self.severity,
            "message": self.message,
        }
        if self.value is not None:
            result["value"] = self.value
        return result


class LogHealthMetrics:
    """Health metrics for a single trade log."""

    def __init__(self, log_data: Dict[str, Any]):
        self.log_id = log_data.get("id")
        self.log_name = log_data.get("name", "Unknown")
        self.lifecycle_state = log_data.get("lifecycle_state", "active")
        self.ml_included = log_data.get("ml_included", True)
        self.open_positions = log_data.get("open_trades", 0)
        self.pending_alerts = log_data.get("pending_alerts", 0)
        self.total_trades = log_data.get("total_trades", 0)
        self.created_at = log_data.get("created_at")
        self.retire_scheduled_at = log_data.get("retire_scheduled_at")

        # Computed fields
        self.last_trade_at = log_data.get("last_trade_at")
        self.last_import_at = log_data.get("last_import_at")
        self.days_since_last_trade = self._compute_days_ago(self.last_trade_at)
        self.days_since_last_import = self._compute_days_ago(self.last_import_at)
        self.days_until_retirement = self._compute_days_until(self.retire_scheduled_at)

    def _compute_days_ago(self, date_str: Optional[str]) -> Optional[int]:
        if not date_str:
            return None
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            now = datetime.now(ET)
            delta = now - dt.astimezone(ET)
            return max(0, delta.days)
        except (ValueError, TypeError):
            return None

    def _compute_days_until(self, date_str: Optional[str]) -> Optional[int]:
        if not date_str:
            return None
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            now = datetime.now(ET)
            delta = dt.astimezone(ET) - now
            return max(0, delta.days)
        except (ValueError, TypeError):
            return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "log_id": self.log_id,
            "log_name": self.log_name,
            "lifecycle_state": self.lifecycle_state,
            "days_since_last_trade": self.days_since_last_trade,
            "days_since_last_import": self.days_since_last_import,
            "total_trades": self.total_trades,
            "open_positions": self.open_positions,
            "pending_alerts": self.pending_alerts,
            "ml_included": self.ml_included,
            "created_at": self.created_at,
            "last_trade_at": self.last_trade_at,
        }


def derive_signals(metrics: LogHealthMetrics, active_log_count: int) -> List[LogHealthSignal]:
    """
    Derive signals from log health metrics.

    Only meaningful signals are returned - no noise.
    """
    signals = []

    # Skip retired logs
    if metrics.lifecycle_state == "retired":
        return signals

    # Signal: Log inactive
    if (
        metrics.lifecycle_state == "active"
        and metrics.days_since_last_trade is not None
        and metrics.days_since_last_trade >= INACTIVE_DAYS_THRESHOLD
    ):
        weeks = metrics.days_since_last_trade // 7
        if weeks >= 4:
            message = f"No activity in over a month ({metrics.days_since_last_trade} days)"
            severity = SEVERITY_MEDIUM
        elif weeks >= 2:
            message = f"No activity in {weeks} weeks"
            severity = SEVERITY_LOW
        else:
            message = f"No activity in {metrics.days_since_last_trade} days"
            severity = SEVERITY_LOW

        signals.append(LogHealthSignal(
            signal_type="log_inactive",
            severity=severity,
            value=metrics.days_since_last_trade,
            message=message,
        ))

    # Signal: Stale imports
    if (
        metrics.lifecycle_state == "active"
        and metrics.days_since_last_import is not None
        and metrics.days_since_last_import >= STALE_IMPORT_DAYS_THRESHOLD
    ):
        signals.append(LogHealthSignal(
            signal_type="log_stale_imports",
            severity=SEVERITY_LOW,
            value=metrics.days_since_last_import,
            message=f"No imports in {metrics.days_since_last_import} days",
        ))

    # Signal: ML excluded on active log
    if metrics.lifecycle_state == "active" and not metrics.ml_included:
        signals.append(LogHealthSignal(
            signal_type="ml_excluded_active_log",
            severity=SEVERITY_MEDIUM,
            message="Trades here are not contributing to learning",
        ))

    # Signal: Ready for archive (active log with no positions/alerts)
    if (
        metrics.lifecycle_state == "active"
        and metrics.open_positions == 0
        and metrics.pending_alerts == 0
        and metrics.days_since_last_trade is not None
        and metrics.days_since_last_trade >= 7
    ):
        signals.append(LogHealthSignal(
            signal_type="log_ready_for_archive",
            severity=SEVERITY_LOW,
            message="No open positions or alerts - can be archived",
        ))

    # Signal: Approaching active log cap (per-user, not per-log)
    if metrics.lifecycle_state == "active" and active_log_count >= ACTIVE_LOG_SOFT_CAP:
        signals.append(LogHealthSignal(
            signal_type="approaching_active_log_cap",
            severity=SEVERITY_MEDIUM if active_log_count >= 8 else SEVERITY_LOW,
            value=active_log_count,
            message=f"You have {active_log_count} active logs",
        ))

    # Signal: Retirement pending
    if (
        metrics.lifecycle_state == "archived"
        and metrics.days_until_retirement is not None
        and metrics.days_until_retirement <= RETIREMENT_WARNING_DAYS
    ):
        signals.append(LogHealthSignal(
            signal_type="retirement_pending",
            severity=SEVERITY_HIGH if metrics.days_until_retirement <= 1 else SEVERITY_MEDIUM,
            value=metrics.days_until_retirement,
            message=f"Retiring in {metrics.days_until_retirement} day{'s' if metrics.days_until_retirement != 1 else ''}",
        ))

    return signals


class LogHealthAnalyzer:
    """
    Analyzes trade log health for all users and generates Vexy context.

    Designed to run as a scheduled job at 05:00 ET daily.
    """

    def __init__(self, journal_api_base: str, logger=None):
        self.journal_api_base = journal_api_base.rstrip("/")
        self.logger = logger

    def _log(self, level: str, message: str, **kwargs):
        if self.logger:
            getattr(self.logger, level, self.logger.info)(message, **kwargs)
        else:
            print(f"[{level.upper()}] {message}")

    async def analyze_user_logs(self, user_id: int) -> Dict[str, Any]:
        """
        Analyze all logs for a single user and return context payload.

        Returns a payload ready for POST /api/vexy/context/log-health
        """
        try:
            # Fetch log health metrics from Journal API (internal endpoint)
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.journal_api_base}/api/logs/health",
                    params={"user_id": user_id},
                )
                response.raise_for_status()
                data = response.json()

            if not data.get("success"):
                self._log("error", f"Failed to fetch log health for user {user_id}")
                return {}

            logs_data = data.get("data", [])
            if not logs_data:
                return {}

            # Count active logs for cap signal
            active_log_count = sum(1 for log in logs_data if log.get("lifecycle_state") == "active")

            # Analyze each log
            logs_with_signals = []
            for log_data in logs_data:
                metrics = LogHealthMetrics(log_data)
                signals = derive_signals(metrics, active_log_count)

                # Only include logs with signals
                if signals:
                    logs_with_signals.append({
                        "log_id": metrics.log_id,
                        "log_name": metrics.log_name,
                        "signals": [s.to_dict() for s in signals],
                    })

            if not logs_with_signals:
                return {}

            # Build context payload
            today = datetime.now(ET).strftime("%Y-%m-%d")
            return {
                "user_id": user_id,
                "routine_date": today,
                "logs": logs_with_signals,
            }

        except Exception as e:
            self._log("error", f"Error analyzing logs for user {user_id}: {e}")
            return {}

    async def run_for_all_users(self, user_ids: List[int]) -> List[Dict[str, Any]]:
        """
        Run analysis for all specified users.

        Returns list of context payloads (one per user with signals).
        """
        results = []
        for user_id in user_ids:
            context = await self.analyze_user_logs(user_id)
            if context:
                results.append(context)
                self._log("info", f"Generated log health context for user {user_id} ({len(context.get('logs', []))} logs with signals)")

        return results


# Context storage (in-memory for now, could be Redis/DB)
_routine_context_store: Dict[str, Dict[str, Any]] = {}


def store_routine_context(user_id: int, routine_date: str, context: Dict[str, Any]) -> None:
    """Store routine context for a user (idempotent per user_id + date)."""
    key = f"{user_id}:{routine_date}"
    _routine_context_store[key] = context


def get_routine_context(user_id: int, routine_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve routine context for a user."""
    if routine_date is None:
        routine_date = datetime.now(ET).strftime("%Y-%m-%d")
    key = f"{user_id}:{routine_date}"
    return _routine_context_store.get(key)


def get_log_health_signals_for_briefing(user_id: int) -> List[Dict[str, Any]]:
    """
    Get log health signals formatted for inclusion in Routine briefing.

    Returns list of signals suitable for narrative generation.
    """
    context = get_routine_context(user_id)
    if not context:
        return []

    all_signals = []
    for log_entry in context.get("logs", []):
        log_name = log_entry.get("log_name", "Unknown")
        for signal in log_entry.get("signals", []):
            all_signals.append({
                "log_name": log_name,
                **signal,
            })

    return all_signals
