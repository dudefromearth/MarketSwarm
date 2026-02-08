#!/usr/bin/env python3
"""
process_echo.py — Process-Level Echo for Vexy AI

Lightweight narrative reflection that creates continuity between
Routine and Process phases. Read-only, no new infrastructure.

Per spec:
- Observe → Compare → Echo (gently)
- Never blocks, interrupts, or persists
- Maximum 1-2 echoes per session
- Follows strict language rules

See: echo-spec-vexy-rules.md
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
import pytz

from .log_health_analyzer import get_routine_context

ET = pytz.timezone("America/New_York")


# Echo types with templates following language rules
ECHO_TEMPLATES = {
    "log_reactivated": (
        "This morning you noted {log_name} was inactive. "
        "Today's trade reactivated it."
    ),
    "log_archived": (
        "This morning you flagged {log_name} as ready to archive. "
        "It was archived during the session."
    ),
    "ml_included": (
        "This morning {log_name} was excluded from ML learning. "
        "It was re-included today."
    ),
    "alerts_cleared": (
        "The alerts you noted this morning were cleared before session end."
    ),
    "stability": (
        "Nothing materially changed from your morning setup — steady execution."
    ),
    "traded_in_flagged_log": (
        "You traded in {log_name}, which you noted this morning."
    ),
}


class ProcessEchoDelta:
    """A single meaningful delta between Routine and current state."""

    def __init__(
        self,
        delta_type: str,
        log_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.delta_type = delta_type
        self.log_name = log_name
        self.details = details or {}

    def to_echo_message(self) -> str:
        """Generate the echo message following language rules."""
        template = ECHO_TEMPLATES.get(self.delta_type)
        if not template:
            return ""

        return template.format(
            log_name=self.log_name or "a log",
            **self.details
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "process_echo",
            "category": "continuity",
            "delta_type": self.delta_type,
            "log_name": self.log_name,
            "message": self.to_echo_message(),
            "source": ["routine_context", "current_log_state"],
            "confidence": "high",
        }


def _extract_routine_log_signals(routine_context: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Extract log-level signals from Routine context.

    Returns dict keyed by log_name with signal types as values.
    """
    signals_by_log = {}

    for log_entry in routine_context.get("logs", []):
        log_name = log_entry.get("log_name", "Unknown")
        signals = log_entry.get("signals", [])

        signals_by_log[log_name] = {
            "signal_types": [s.get("type") for s in signals],
            "signals": signals,
        }

    return signals_by_log


def compute_deltas(
    routine_context: Dict[str, Any],
    current_logs: List[Dict[str, Any]],
) -> List[ProcessEchoDelta]:
    """
    Compute meaningful deltas between Routine context and current state.

    Per spec, meaningful deltas represent:
    - User action
    - Operational posture change
    - Matters for retrospective reflection

    Not meaningful:
    - Timestamp changes
    - Incremental trade counts
    - Background imports
    """
    deltas = []

    # Extract what Routine surfaced
    routine_signals = _extract_routine_log_signals(routine_context)

    # Build current state lookup
    current_by_name = {log.get("name"): log for log in current_logs}

    for log_name, routine_data in routine_signals.items():
        signal_types = set(routine_data.get("signal_types", []))
        current_log = current_by_name.get(log_name)

        if not current_log:
            continue

        # Check: Was inactive log reactivated?
        if "log_inactive" in signal_types:
            # Check if there's been activity since morning
            last_trade = current_log.get("last_trade_at")
            if last_trade:
                try:
                    trade_dt = datetime.fromisoformat(last_trade.replace("Z", "+00:00"))
                    today = datetime.now(ET).date()
                    if trade_dt.astimezone(ET).date() == today:
                        deltas.append(ProcessEchoDelta(
                            delta_type="log_reactivated",
                            log_name=log_name,
                        ))
                except (ValueError, TypeError):
                    pass

        # Check: Was ML-excluded log re-included?
        if "ml_excluded_active_log" in signal_types:
            if current_log.get("ml_included"):
                deltas.append(ProcessEchoDelta(
                    delta_type="ml_included",
                    log_name=log_name,
                ))

        # Check: Was archive-ready log archived?
        if "log_ready_for_archive" in signal_types:
            if current_log.get("lifecycle_state") == "archived":
                deltas.append(ProcessEchoDelta(
                    delta_type="log_archived",
                    log_name=log_name,
                ))

        # Check: Did user trade in a flagged log?
        if signal_types:  # Any signal was present
            open_trades = current_log.get("open_trades", 0)
            last_trade = current_log.get("last_trade_at")
            if open_trades > 0 and last_trade:
                try:
                    trade_dt = datetime.fromisoformat(last_trade.replace("Z", "+00:00"))
                    today = datetime.now(ET).date()
                    if trade_dt.astimezone(ET).date() == today:
                        # Only add if we haven't already added a more specific delta
                        if not any(d.log_name == log_name for d in deltas):
                            deltas.append(ProcessEchoDelta(
                                delta_type="traded_in_flagged_log",
                                log_name=log_name,
                            ))
                except (ValueError, TypeError):
                    pass

    # If no deltas but Routine was opened, emit stability echo
    if not deltas and routine_context:
        deltas.append(ProcessEchoDelta(delta_type="stability"))

    return deltas


def select_echoes(deltas: List[ProcessEchoDelta], max_echoes: int = 2) -> List[ProcessEchoDelta]:
    """
    Select the most meaningful echoes to emit.

    Per spec: Maximum 1-2 echoes per Process session.
    Prioritizes action-based deltas over stability.
    """
    if not deltas:
        return []

    # Priority order (lower = higher priority)
    priority = {
        "log_reactivated": 1,
        "log_archived": 2,
        "ml_included": 3,
        "alerts_cleared": 4,
        "traded_in_flagged_log": 5,
        "stability": 99,  # Lowest priority
    }

    # Sort by priority
    sorted_deltas = sorted(deltas, key=lambda d: priority.get(d.delta_type, 50))

    # Filter out stability if we have meaningful deltas
    if len(sorted_deltas) > 1:
        sorted_deltas = [d for d in sorted_deltas if d.delta_type != "stability"]

    return sorted_deltas[:max_echoes]


class ProcessEchoGenerator:
    """
    Generates Process-Level Echo narrative fragments.

    Read-only, stateless. Uses existing Routine context and
    fetches current log state from Journal API.
    """

    def __init__(self, journal_api_base: str, logger=None):
        self.journal_api_base = journal_api_base.rstrip("/")
        self.logger = logger

    def _log(self, level: str, message: str, **kwargs):
        if self.logger:
            getattr(self.logger, level, self.logger.info)(message, **kwargs)

    async def fetch_current_log_state(self, user_id: int) -> List[Dict[str, Any]]:
        """Fetch current log state from Journal API."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.journal_api_base}/api/logs/health",
                    params={"user_id": user_id},
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("data", [])
                return []
        except Exception as e:
            self._log("error", f"Failed to fetch log state: {e}")
            return []

    async def generate_echoes(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Generate Process-Level Echo fragments for a user.

        Returns list of echo dicts ready for inclusion in Process narrative.
        Returns empty list if:
        - Routine was not opened (no context)
        - No meaningful deltas
        - Already echoed (caller should track)
        """
        # Get Routine context (stored earlier today)
        routine_context = get_routine_context(user_id)

        if not routine_context:
            # Routine wasn't opened or no signals were surfaced
            return []

        # Fetch current log state
        current_logs = await self.fetch_current_log_state(user_id)

        if not current_logs:
            return []

        # Compute deltas
        deltas = compute_deltas(routine_context, current_logs)

        # Select echoes (max 2)
        selected = select_echoes(deltas)

        return [echo.to_dict() for echo in selected]


def format_echoes_for_narrative(echoes: List[Dict[str, Any]]) -> str:
    """
    Format echo fragments for inclusion in Process narrative.

    Returns a paragraph suitable for appending to Process output.
    Returns empty string if no echoes.
    """
    if not echoes:
        return ""

    messages = [echo.get("message", "") for echo in echoes if echo.get("message")]

    if not messages:
        return ""

    # Join with space (each message is already a complete thought)
    return " ".join(messages)
