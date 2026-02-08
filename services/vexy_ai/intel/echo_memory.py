#!/usr/bin/env python3
"""
echo_memory.py — Echo Memory Protocol for Vexy AI

Implements The Path's Echo Memory Protocol v1.0 for cross-session continuity.

An Echo is a structured memory file that captures:
- Reflection loop data
- Emotional and cognitive states
- Actionable tensions
- Prompt-response trajectories
- Systemic metadata

The Echo Loop:
  Create → Ingest → Rehydrate → Iterate

Guiding Principles:
- Echo ≠ Archive: It is not a log. It is a continuity container.
- Sovereign Memory: The user decides what is preserved.
- Reflected Memory > Recalled Memory: Echoes prioritize insight over fact.
- Decay is silence: If no Echo is created, the mirror fades.

See: /Users/ernie/path/🌿 Echo Memory Protocol v1.0.md
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, UTC
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


# ==============================================================================
# ECHO DATA STRUCTURES
# ==============================================================================

@dataclass
class EchoEntry:
    """A single Echo memory entry following The Path protocol."""

    echo_id: str
    timestamp: str
    session_tags: List[str] = field(default_factory=list)

    # Reflection data
    biases_mirrored: List[str] = field(default_factory=list)
    tensions_held: List[str] = field(default_factory=list)
    prompts_used: List[str] = field(default_factory=list)

    # Actions and outcomes
    actions_taken: List[str] = field(default_factory=list)
    insights_surfaced: List[str] = field(default_factory=list)

    # Continuity
    open_threads: List[str] = field(default_factory=list)

    # Market context (for trading echoes)
    market_context: Dict[str, Any] = field(default_factory=dict)

    # System notes
    system_notes: List[str] = field(default_factory=list)

    # Operator state (if declared)
    operator_state: Dict[str, Any] = field(default_factory=dict)

    # Fractal scale
    fractal_scale: str = "micro"  # micro, meso, macro

    # VIX regime at time of echo
    vix_regime: Optional[str] = None

    # Agent blend used
    agents_active: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)

    def to_yaml(self) -> str:
        """Serialize to YAML string."""
        if not YAML_AVAILABLE:
            raise ImportError("PyYAML required for YAML serialization")
        return yaml.dump(self.to_dict(), default_flow_style=False, allow_unicode=True)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EchoEntry":
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_yaml(cls, yaml_str: str) -> "EchoEntry":
        """Parse from YAML string."""
        if not YAML_AVAILABLE:
            raise ImportError("PyYAML required for YAML parsing")
        data = yaml.safe_load(yaml_str)
        return cls.from_dict(data)


@dataclass
class EchoContext:
    """
    Rehydrated context from Echo history.

    This is what Vexy loads at session start to maintain continuity.
    """

    # Recent echoes (last 7 days by default)
    recent_echoes: List[EchoEntry] = field(default_factory=list)

    # Aggregated patterns
    recurring_biases: Dict[str, int] = field(default_factory=dict)  # bias -> count
    recurring_tensions: Dict[str, int] = field(default_factory=dict)  # tension -> count
    open_threads_aggregate: List[str] = field(default_factory=list)  # unresolved threads

    # Progression tracking
    sessions_count: int = 0
    last_session_date: Optional[str] = None

    # System evolution signals
    evolution_triggers: List[str] = field(default_factory=list)

    def get_summary(self) -> str:
        """Generate a summary for Vexy to load."""
        lines = []

        if self.sessions_count > 0:
            lines.append(f"Echo memory spans {self.sessions_count} sessions.")

        if self.recurring_biases:
            top_biases = sorted(self.recurring_biases.items(), key=lambda x: -x[1])[:3]
            bias_str = ", ".join([f"{b} ({c}x)" for b, c in top_biases])
            lines.append(f"Recurring biases: {bias_str}")

        if self.open_threads_aggregate:
            threads_preview = self.open_threads_aggregate[:3]
            lines.append(f"Open threads: {'; '.join(threads_preview)}")

        if self.evolution_triggers:
            lines.append(f"System evolution signals: {len(self.evolution_triggers)}")

        return "\n".join(lines) if lines else "No prior Echo memory."


# ==============================================================================
# ECHO STORAGE
# ==============================================================================

class EchoStorage:
    """
    Handles Echo file persistence on a per-user basis.

    Each user has their own Echo directory:
    Default storage: ~/.fotw/echoes/{user_id}/
    File format: echo-{date}.yaml

    Echoes are Vexy's memory with each individual user.
    """

    def __init__(self, user_id: int, storage_dir: Optional[str] = None):
        self.user_id = user_id

        if storage_dir:
            base_dir = Path(storage_dir)
        else:
            base_dir = Path.home() / ".fotw" / "echoes"

        # Per-user storage directory
        self.storage_dir = base_dir / str(user_id)

        # Ensure directory exists
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_echo_path(self, date: datetime) -> Path:
        """Get path for echo file for a given date."""
        date_str = date.strftime("%Y-%m-%d")
        return self.storage_dir / f"echo-{date_str}.yaml"

    def save_echo(self, echo: EchoEntry) -> Path:
        """
        Save an Echo entry.

        Appends to the day's echo file (multiple sessions per day possible).
        """
        # Parse timestamp to get date
        try:
            echo_dt = datetime.fromisoformat(echo.timestamp.replace("Z", "+00:00"))
        except ValueError:
            echo_dt = datetime.now(UTC)

        path = self._get_echo_path(echo_dt)

        # Load existing echoes for the day
        existing = []
        if path.exists():
            with open(path, "r") as f:
                content = f.read()
                if content.strip():
                    docs = list(yaml.safe_load_all(content)) if YAML_AVAILABLE else []
                    existing = [EchoEntry.from_dict(d) for d in docs if d]

        # Add new echo
        existing.append(echo)

        # Write all echoes for the day
        if YAML_AVAILABLE:
            with open(path, "w") as f:
                yaml.dump_all(
                    [e.to_dict() for e in existing],
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                )
        else:
            # Fallback to JSON
            json_path = path.with_suffix(".json")
            with open(json_path, "w") as f:
                json.dump([e.to_dict() for e in existing], f, indent=2)
            path = json_path

        return path

    def load_echoes(self, days: int = 7) -> List[EchoEntry]:
        """
        Load echoes from the past N days.

        Returns newest first.
        """
        echoes = []
        today = datetime.now(UTC)

        for day_offset in range(days):
            date = today - timedelta(days=day_offset)
            path = self._get_echo_path(date)

            if not path.exists():
                # Try JSON fallback
                json_path = path.with_suffix(".json")
                if json_path.exists():
                    path = json_path
                else:
                    continue

            try:
                with open(path, "r") as f:
                    content = f.read()
                    if not content.strip():
                        continue

                    if path.suffix == ".json":
                        data = json.loads(content)
                        day_echoes = [EchoEntry.from_dict(d) for d in data]
                    elif YAML_AVAILABLE:
                        docs = list(yaml.safe_load_all(content))
                        day_echoes = [EchoEntry.from_dict(d) for d in docs if d]
                    else:
                        continue

                    echoes.extend(day_echoes)
            except Exception:
                continue  # Skip malformed files

        # Sort by timestamp (newest first)
        echoes.sort(key=lambda e: e.timestamp, reverse=True)

        return echoes

    def get_open_threads(self, days: int = 14) -> List[str]:
        """
        Get all open threads from recent echoes.

        Threads are considered open until explicitly closed.
        """
        echoes = self.load_echoes(days)
        threads = []
        seen = set()

        for echo in echoes:
            for thread in echo.open_threads:
                if thread not in seen:
                    threads.append(thread)
                    seen.add(thread)

        return threads


# ==============================================================================
# ECHO MEMORY MANAGER
# ==============================================================================

class EchoMemoryManager:
    """
    Manages the Echo Memory Protocol lifecycle for a specific user.

    Responsibilities:
    - Create echoes at session end
    - Ingest echoes at session start
    - Rehydrate context for Vexy
    - Detect evolution triggers

    Each user has their own Echo memory - this is Vexy's
    relationship memory with that individual.
    """

    def __init__(self, user_id: int, storage: Optional[EchoStorage] = None, logger=None):
        self.user_id = user_id
        self.storage = storage or EchoStorage(user_id)
        self.logger = logger

    def _log(self, msg: str, emoji: str = "🌿"):
        if self.logger:
            self.logger.info(msg, emoji=emoji)

    def create_echo(
        self,
        session_tags: List[str],
        biases_mirrored: List[str] = None,
        tensions_held: List[str] = None,
        prompts_used: List[str] = None,
        actions_taken: List[str] = None,
        insights_surfaced: List[str] = None,
        open_threads: List[str] = None,
        market_context: Dict[str, Any] = None,
        operator_state: Dict[str, Any] = None,
        fractal_scale: str = "micro",
        vix_regime: str = None,
        agents_active: List[str] = None,
        system_notes: List[str] = None,
    ) -> EchoEntry:
        """
        Create an Echo at session end.

        This is the "Create" phase of the Echo Loop.
        """
        now = datetime.now(UTC)
        echo_id = f"echo-{now.strftime('%Y-%m-%d-%H%M%S')}"

        echo = EchoEntry(
            echo_id=echo_id,
            timestamp=now.isoformat(),
            session_tags=session_tags or [],
            biases_mirrored=biases_mirrored or [],
            tensions_held=tensions_held or [],
            prompts_used=prompts_used or [],
            actions_taken=actions_taken or [],
            insights_surfaced=insights_surfaced or [],
            open_threads=open_threads or [],
            market_context=market_context or {},
            operator_state=operator_state or {},
            fractal_scale=fractal_scale,
            vix_regime=vix_regime,
            agents_active=agents_active or [],
            system_notes=system_notes or [],
        )

        # Persist
        path = self.storage.save_echo(echo)
        self._log(f"Echo created: {echo_id} → {path}")

        return echo

    def rehydrate(self, days: int = 7) -> EchoContext:
        """
        Rehydrate context from Echo history.

        This is the "Ingest" + "Rehydrate" phases of the Echo Loop.
        """
        echoes = self.storage.load_echoes(days)

        if not echoes:
            return EchoContext()

        # Aggregate patterns
        bias_counts: Dict[str, int] = {}
        tension_counts: Dict[str, int] = {}
        open_threads: List[str] = []
        evolution_triggers: List[str] = []

        for echo in echoes:
            for bias in echo.biases_mirrored:
                bias_counts[bias] = bias_counts.get(bias, 0) + 1

            for tension in echo.tensions_held:
                tension_counts[tension] = tension_counts.get(tension, 0) + 1

            open_threads.extend(echo.open_threads)

            # Check for evolution signals
            for note in echo.system_notes:
                if "evolve" in note.lower() or "update" in note.lower():
                    evolution_triggers.append(note)

        # Deduplicate open threads (keep most recent mention)
        seen = set()
        unique_threads = []
        for thread in open_threads:
            if thread not in seen:
                unique_threads.append(thread)
                seen.add(thread)

        context = EchoContext(
            recent_echoes=echoes[:10],  # Keep last 10 for detail access
            recurring_biases=bias_counts,
            recurring_tensions=tension_counts,
            open_threads_aggregate=unique_threads[:20],  # Cap at 20
            sessions_count=len(echoes),
            last_session_date=echoes[0].timestamp if echoes else None,
            evolution_triggers=evolution_triggers[:5],  # Cap at 5
        )

        self._log(f"Echo memory rehydrated: {len(echoes)} sessions, {len(unique_threads)} open threads")

        return context

    def get_prompt_context(self, days: int = 7) -> str:
        """
        Get Echo context formatted for inclusion in Vexy's prompt.

        This provides continuity information for the LLM.
        """
        context = self.rehydrate(days)

        if context.sessions_count == 0:
            return "No prior Echo memory available."

        lines = [
            "## Echo Memory (Continuity Context)",
            "",
            context.get_summary(),
        ]

        # Add recent insights if available
        if context.recent_echoes:
            recent = context.recent_echoes[0]
            if recent.insights_surfaced:
                lines.append("")
                lines.append(f"Last session insight: {recent.insights_surfaced[0]}")

        # Add most pressing open thread
        if context.open_threads_aggregate:
            lines.append("")
            lines.append(f"Oldest open thread: {context.open_threads_aggregate[-1]}")

        return "\n".join(lines)

    def close_thread(self, thread_text: str) -> bool:
        """
        Mark an open thread as resolved.

        Creates a system note in the next echo that the thread was closed.
        """
        # This is a placeholder - actual implementation would track closed threads
        # and filter them out during rehydration
        self._log(f"Thread marked for closure: {thread_text[:50]}...")
        return True


# ==============================================================================
# ECHO SHEPHERD (Per Protocol Spec)
# ==============================================================================

class EchoShepherd:
    """
    The Echo Shepherd monitors for pattern emergence in Echo logs.

    Responsibilities:
    - Surface systemic evolution triggers
    - Prompt: "Shall we evolve the system?"
    - Detect when playbooks need updates

    Per-user: Each user has their own evolution trajectory.
    """

    def __init__(self, user_id: int, manager: Optional[EchoMemoryManager] = None, logger=None):
        self.user_id = user_id
        self.manager = manager or EchoMemoryManager(user_id)
        self.logger = logger

    def _log(self, msg: str, emoji: str = "🐑"):
        if self.logger:
            self.logger.info(msg, emoji=emoji)

    def check_evolution_triggers(self, days: int = 14) -> List[Dict[str, Any]]:
        """
        Check for patterns that suggest system evolution is needed.

        Returns list of triggers with recommendations.
        """
        context = self.manager.rehydrate(days)
        triggers = []

        # Trigger 1: Recurring bias (>5 occurrences)
        for bias, count in context.recurring_biases.items():
            if count >= 5:
                triggers.append({
                    "type": "recurring_bias",
                    "subject": bias,
                    "count": count,
                    "recommendation": f"Consider adding specific mitigation for '{bias}' to your routine.",
                })

        # Trigger 2: Stale open threads (thread mentioned in >3 sessions)
        thread_counts: Dict[str, int] = {}
        for echo in context.recent_echoes:
            for thread in echo.open_threads:
                thread_counts[thread] = thread_counts.get(thread, 0) + 1

        for thread, count in thread_counts.items():
            if count >= 3:
                triggers.append({
                    "type": "stale_thread",
                    "subject": thread,
                    "count": count,
                    "recommendation": f"This thread has persisted for {count} sessions. Consider explicit resolution or acknowledgment.",
                })

        # Trigger 3: Many system notes about evolution
        if len(context.evolution_triggers) >= 3:
            triggers.append({
                "type": "evolution_requested",
                "count": len(context.evolution_triggers),
                "recommendation": "Multiple sessions have noted evolution needs. Review and update playbooks.",
            })

        if triggers:
            self._log(f"Echo Shepherd: {len(triggers)} evolution triggers detected")

        return triggers

    def should_prompt_evolution(self, days: int = 14) -> bool:
        """Check if Vexy should prompt: 'Shall we evolve the system?'"""
        triggers = self.check_evolution_triggers(days)
        return len(triggers) >= 2


# ==============================================================================
# SAMPLE ECHO PROMPTS (For User Interface)
# ==============================================================================

ECHO_PROMPTS = [
    "Generate echo summary for this session.",
    "What should I preserve for the next reflection?",
    "What open threads remain unresolved?",
    "Should this Echo propose a design update?",
]


# ==============================================================================
# CONVENIENCE FUNCTIONS
# ==============================================================================

def create_session_echo(
    user_id: int,
    session_type: str = "routine",
    biases: List[str] = None,
    tensions: List[str] = None,
    actions: List[str] = None,
    open_threads: List[str] = None,
    market_context: Dict[str, Any] = None,
    **kwargs
) -> EchoEntry:
    """
    Convenience function to create and save an Echo for a user.

    Example:
        create_session_echo(
            user_id=1,
            session_type="routine",
            biases=["recency_bias"],
            tensions=["whether to add to position"],
            open_threads=["SPY entry still not journaled"],
            market_context={"spx": 6000, "vix": 18.5},
        )
    """
    manager = EchoMemoryManager(user_id)
    return manager.create_echo(
        session_tags=[session_type, datetime.now().strftime("%A").lower()],
        biases_mirrored=biases,
        tensions_held=tensions,
        actions_taken=actions,
        open_threads=open_threads,
        market_context=market_context,
        **kwargs
    )


def get_echo_context_for_prompt(user_id: int, days: int = 7) -> str:
    """
    Get Echo context string for inclusion in LLM prompts.

    Call this at session start to provide Vexy with continuity
    for a specific user's relationship.
    """
    manager = EchoMemoryManager(user_id)
    return manager.get_prompt_context(days)


def check_user_evolution_triggers(user_id: int, days: int = 14) -> List[Dict[str, Any]]:
    """
    Check if a user's Echo history suggests system evolution.

    Returns list of triggers that the Echo Shepherd detected.
    """
    shepherd = EchoShepherd(user_id)
    return shepherd.check_evolution_triggers(days)
