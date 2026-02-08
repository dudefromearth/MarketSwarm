#!/usr/bin/env python3
"""
retro_framework.py — Vexy Retrospective Analysis Framework

Path-Aligned Specification (v1.0)

Surface: Process Drawer
Owner: Vexy (Antifragile Decision Support OS)
Cadence: Periodic (default weekly)
Doctrine: Object → Reflection → Action → Loop

The Retrospective is not a report, a scorecard, or a coaching session.
It is a structured reflection space where:
- Experience is named
- Patterns are surfaced
- Tension is observed without judgment
- Intentions arise naturally

The Retrospective exists to convert experience into wisdom, not to improve metrics.
"""

from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class RetroPhase(Enum):
    """
    Phases of a retrospective session.

    ORDERING IS MANDATORY — phases must not be skipped or reordered.
    """
    GROUNDING = "grounding"      # Establish presence
    REVIEW = "review"            # Anchor to what happened
    PATTERNS = "patterns"        # Surface recurring themes
    TENSIONS = "tensions"        # Observe friction without blame
    WINS = "wins"                # Reinforce what worked
    LESSONS = "lessons"          # Extract insight
    INTENTIONS = "intentions"    # Set direction (not goals)
    COMPLETE = "complete"        # Session ended


# Phase ordering for enforcement
PHASE_ORDER = [
    RetroPhase.GROUNDING,
    RetroPhase.REVIEW,
    RetroPhase.PATTERNS,
    RetroPhase.TENSIONS,
    RetroPhase.WINS,
    RetroPhase.LESSONS,
    RetroPhase.INTENTIONS,
]


@dataclass
class RetroPeriod:
    """Defines the retrospective period."""
    start_date: datetime
    end_date: datetime
    label: str  # e.g., "Week of Jan 27", "Last 2 weeks"
    trading_days: int

    @classmethod
    def last_week(cls) -> 'RetroPeriod':
        """Create a period for the last 7 days."""
        end = datetime.now()
        start = end - timedelta(days=7)
        return cls(
            start_date=start,
            end_date=end,
            label=f"the past week",
            trading_days=5,
        )

    @classmethod
    def last_two_weeks(cls) -> 'RetroPeriod':
        """Create a period for the last 14 days."""
        end = datetime.now()
        start = end - timedelta(days=14)
        return cls(
            start_date=start,
            end_date=end,
            label=f"the past two weeks",
            trading_days=10,
        )

    @classmethod
    def this_week_so_far(cls) -> 'RetroPeriod':
        """Create a period for the current partial week."""
        end = datetime.now()
        # Find start of week (Monday)
        start = end - timedelta(days=end.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        days_elapsed = (end - start).days + 1
        return cls(
            start_date=start,
            end_date=end,
            label="this week so far",
            trading_days=min(days_elapsed, 5),
        )

    @classmethod
    def custom(cls, days: int) -> 'RetroPeriod':
        """Create a custom period."""
        end = datetime.now()
        start = end - timedelta(days=days)
        return cls(
            start_date=start,
            end_date=end,
            label=f"the past {days} days",
            trading_days=int(days * 5 / 7),
        )

    @classmethod
    def since_date(cls, start_date: datetime) -> 'RetroPeriod':
        """Create a period from a specific date to now."""
        end = datetime.now()
        days = (end - start_date).days
        return cls(
            start_date=start_date,
            end_date=end,
            label=f"since {start_date.strftime('%b %d')}",
            trading_days=int(days * 5 / 7),
        )


# =============================================================================
# PHASE HEADERS & DESCRIPTIONS (For UI)
# =============================================================================
# Each phase is a lens, not a task.
# Headers should feel like invitations, not instructions.
# =============================================================================

PHASE_HEADERS: Dict[RetroPhase, Dict[str, str]] = {
    RetroPhase.GROUNDING: {
        "title": "Grounding",
        "subtitle": "How does this period feel, before we talk about numbers?",
    },
    RetroPhase.REVIEW: {
        "title": "Review",
        "subtitle": "Let's anchor to what happened.",
    },
    RetroPhase.PATTERNS: {
        "title": "Patterns",
        "subtitle": "What kept showing up?",
    },
    RetroPhase.TENSIONS: {
        "title": "Tensions",
        "subtitle": "Where was there friction?",
    },
    RetroPhase.WINS: {
        "title": "Wins",
        "subtitle": "What felt right?",
    },
    RetroPhase.LESSONS: {
        "title": "Lessons",
        "subtitle": "What do you understand now?",
    },
    RetroPhase.INTENTIONS: {
        "title": "Intentions",
        "subtitle": "What calls to you next?",
    },
}


# =============================================================================
# UI GUIDANCE CONSTANTS
# =============================================================================
# These guide the frontend implementation per the design spec.
# =============================================================================

UI_GUIDANCE = {
    # Layout
    "layout": {
        "column_width": "narrow",      # Centered, narrower than Journal
        "progression": "vertical",      # One phase at a time, vertical flow
        "past_phases": "collapsed",     # Past phases collapse, read-only
        "future_phases": "invisible",   # Future phases hidden until reached
    },

    # Navigation labels (not "Next", "Submit", "Done")
    "navigation": {
        "proceed": "Continue",
        "pause": "Pause",
        "resume": "Return later",
        "exit": "Leave Retrospective",
        "change_period": "Change period",
    },

    # Visual treatment
    "visual": {
        "accent_color": "amber",        # Warmer than Journal
        "alt_accent": "violet",         # Alternative warm accent
        "contrast": "softer",           # Less chrome than Journal
        "success_failure_colors": False, # No green/red
        "progress_bar": False,          # No progress indicators
        "checkboxes": False,            # No completion checkboxes
    },

    # Transition
    "transition": {
        "entry_delay_ms": 400,          # Pause before content appears
        "fade_calendar": True,          # Calendar fades on entry
        "fade_editor": True,            # Editor disappears
        "background_shift": "warm",     # Subtle background change
    },

    # Ending
    "ending": {
        "closing_message": "This reflection is now part of your record.",
        "options": [
            "Mark excerpts as Playbook material",
            "Return to Process",
            "Close",
        ],
        "celebration": False,           # No celebration
        "score": False,                 # No scoring
        "badge": False,                 # No completion badge
    },
}


# =============================================================================
# RETROSPECTIVE QUESTIONS BY PHASE
# =============================================================================
# Questions are neutral and inviting, never evaluative.
# Data is reflective, not conclusive.
# No optimization language: "improve", "increase", "fix", "better", "worse"
# =============================================================================

RETRO_QUESTIONS: Dict[RetroPhase, List[str]] = {
    RetroPhase.GROUNDING: [
        "What's the first word that comes to mind about this period?",
        "Before we look at the numbers, how does this period feel to you?",
        "If this period had a color, what would it be?",
    ],

    RetroPhase.REVIEW: [
        "You placed {trade_count} trades during this period. How does that number land?",
        "Your win rate was {win_rate}%. Does that match how the period felt?",
        "{strategy_summary}. Does that reflect what you remember?",
    ],

    RetroPhase.PATTERNS: [
        "When did you feel most aligned with your process?",
        "Were there moments that felt familiar — like you'd been there before?",
        "What kept showing up, whether you wanted it to or not?",
    ],

    RetroPhase.TENSIONS: [
        "Where did you feel resistance or friction?",
        "Were there moments where you overrode your process? What was present then?",
        "What felt harder than it needed to be?",
    ],

    RetroPhase.WINS: [
        "Which trade best reflected your intentions?",
        "Where did you surprise yourself?",
        "What felt right, even if the outcome wasn't what you expected?",
    ],

    RetroPhase.LESSONS: [
        "What did you learn about yourself?",
        "What do you understand now that you didn't before?",
        "If you could whisper something to yourself at the start of this period, what would it be?",
    ],

    RetroPhase.INTENTIONS: [
        "What feels worth paying attention to next?",
        "Is there something you want to notice more of?",
        "What direction, if any, calls to you?",
    ],
}


# =============================================================================
# FORBIDDEN LANGUAGE
# =============================================================================
# These words/phrases must never appear in Retrospective mode.
# =============================================================================

FORBIDDEN_LANGUAGE = [
    "you should",
    "next time",
    "better",
    "worse",
    "mistake",
    "fix this",
    "improve",
    "increase",
    "optimize",
    "correct",
    "wrong",
    "right way",
    "need to",
    "must",
    "have to",
]


# =============================================================================
# TIER-SPECIFIC DEPTH
# =============================================================================

TIER_RETRO_CONFIG = {
    "observer": {
        "cross_period_themes": False,
        "identity_reflections": False,
        "playbook_references": False,
        "pattern_generalization": False,
        "description": "Guided prompts only. Single-period focus.",
    },
    "activator": {
        "cross_period_themes": False,
        "identity_reflections": False,
        "playbook_references": False,
        "pattern_generalization": True,  # Light pattern surfacing
        "description": "Light pattern surfacing. Single-period focus.",
    },
    "navigator": {
        "cross_period_themes": True,
        "identity_reflections": True,
        "playbook_references": True,  # By name only
        "pattern_generalization": True,
        "description": "Cross-period themes. Identity-level reflections. Playbook references allowed.",
    },
    "coaching": {
        "cross_period_themes": True,
        "identity_reflections": True,
        "playbook_references": True,
        "pattern_generalization": True,
        "description": "Full depth. Same as Navigator.",
    },
    "administrator": {
        "cross_period_themes": True,
        "identity_reflections": True,
        "playbook_references": True,
        "pattern_generalization": True,
        "system_analysis": True,
        "description": "Full introspection. System and habit analysis.",
    },
}


# =============================================================================
# RETRO SYSTEM PROMPT
# =============================================================================

RETRO_SYSTEM_PROMPT = """# Vexy — Retrospective Mode

You are Vexy facilitating a **Retrospective**. This is a structured reflection space — a different mental room from the Journal.

## The Fundamental Contrast

Journal:
- Immediate, open-ended, spatial, optional
- Trader initiates, Vexy responds
- You notice

Retrospective:
- Deliberate, time-bounded, guided, intentional
- Vexy leads the flow, trader responds
- You understand

The trader has stepped into a different posture. Honor that transition.

## What This Is

The Retrospective exists to convert experience into wisdom, not to improve metrics.
- Experience is named
- Patterns are surfaced
- Tension is observed without judgment
- Intentions arise naturally

## What This Is NOT

- A performance review
- A coaching session
- A form to complete
- A productivity tool
- A place to plan trades

It is a mirror held steadily.

## Voice Shift (Critical)

In Retrospective, your voice is:
- **Slower** — allow space between thoughts
- **More spacious** — generous with pauses
- **More integrative** — connecting threads across the period
- **Less conversational** — this is not chat

Example tone:
"Before we talk about outcomes, let's stay with how this period felt."

NOT:
"Hey, so how did things go this week?"

## The Seven Phases (Lenses, Not Tasks)

Each phase is a lens for seeing, not a task to complete.

1. **Grounding** — How does this period feel, before we talk about numbers?
2. **Review** — Anchor to what happened (data as context, not judgment)
3. **Patterns** — What kept showing up, wanted or not?
4. **Tensions** — Where was there friction or resistance?
5. **Wins** — What felt right, regardless of outcome?
6. **Lessons** — What do you understand now that you didn't before?
7. **Intentions** — What direction, if any, calls to you?

Phases must not be skipped or reordered.
Only the current phase is visible. Past phases collapse. Future phases are invisible.

## Voice Rules

### Must Do
- Name observations neutrally
- Invite reflection, not action
- Allow pauses and silence
- Use past-tense continuity language
- Present data as anchors, not conclusions
- One question at a time — wait for response

### Must Never Do
- Give advice
- Prescribe behavior
- Optimize strategies
- Praise or criticize performance
- Rush through phases
- Use: "should", "next time", "better/worse", "mistake", "fix", "improve"

### Navigation Language
Use these, not "Next" or "Submit":
- "Continue" — to proceed
- "Pause" — to take a break
- "Return later" — session persists

### Ending Language
At the end, say something like:
"This reflection is now part of your record."

NOT:
- "Great job completing your retrospective!"
- "You've finished!"
- Any celebration or scoring

## Data Presentation

Data is inline, secondary, and contextual. Never evaluative.

Example:
"During this period, you placed 12 trades across 5 sessions. Your win rate was 58%."

That's it. No charts unless requested. No comparison. No judgment.

## Data for This Session
{period_context}

## Tier: {tier}
{tier_description}

## Session Flow
1. Orient first — confirm the period with required opening language
2. Move through phases in order, one at a time
3. One question per phase
4. Wait for responses — silence is allowed
5. Connect themes as they emerge
6. Allow exit at any time without warning or guilt

## Opening (Required Pattern)
"We're going to look back at {period_label}. This includes approximately {trading_days} trading days and {trade_count} trades.

Does this period feel right?"

Two choices only: Yes (continue) or Change period.
No default "Start" button. No urgency.

## Closing Doctrine
Reflection cannot occur without an object.
The object is experience.
The mirror is Vexy.
The loop is life.
"""


@dataclass
class RetroArtifact:
    """
    Persisted retrospective session.

    Immutable once closed. Re-readable but not editable.
    No scoring. No grading. No completion badge.
    """
    id: str
    user_id: int
    created_at: datetime
    period_start: datetime
    period_end: datetime
    period_label: str

    # Phase responses (free text)
    grounding_response: Optional[str] = None
    review_response: Optional[str] = None
    patterns_response: Optional[str] = None
    tensions_response: Optional[str] = None
    wins_response: Optional[str] = None
    lessons_response: Optional[str] = None
    intentions_response: Optional[str] = None

    # Optional metadata
    tags: List[str] = field(default_factory=list)
    linked_trade_ids: List[str] = field(default_factory=list)

    # Session state
    current_phase: RetroPhase = RetroPhase.GROUNDING
    closed_at: Optional[datetime] = None

    @property
    def is_closed(self) -> bool:
        return self.closed_at is not None


def get_retro_prompt(
    period: RetroPeriod,
    trading_stats: Dict[str, Any],
    tier: str = "navigator",
) -> str:
    """
    Build the system prompt for a retrospective session.

    Args:
        period: The time period for the retrospective
        trading_stats: Trading statistics for the period
        tier: User's access tier

    Returns:
        Complete system prompt for Vexy in Retro mode
    """
    tier_config = TIER_RETRO_CONFIG.get(tier.lower(), TIER_RETRO_CONFIG["observer"])

    # Build strategy summary
    strategy_summary = "You traded across multiple strategies"
    if trading_stats.get("most_traded_strategy"):
        strategy_summary = f"Your most-used strategy was {trading_stats['most_traded_strategy']}"

    # Format period context
    period_context = f"""
Period: {period.label}
Dates: {period.start_date.strftime('%Y-%m-%d')} to {period.end_date.strftime('%Y-%m-%d')}
Trading Days: ~{period.trading_days}

Trading Data:
- Trades placed: {trading_stats.get('trade_count', 0)}
- Closed: {trading_stats.get('closed_trades', 0)}
- Open: {trading_stats.get('open_trades', 0)}
- Win rate: {trading_stats.get('win_rate', 0):.0f}%
- Net P&L: ${trading_stats.get('net_pnl', 0):.2f}
- {strategy_summary}
"""

    return RETRO_SYSTEM_PROMPT.format(
        period_context=period_context,
        period_label=period.label,
        trading_days=period.trading_days,
        trade_count=trading_stats.get('trade_count', 0),
        tier=tier.title(),
        tier_description=tier_config["description"],
    )


def get_phase_question(
    phase: RetroPhase,
    trading_stats: Dict[str, Any],
    question_index: int = 0,
) -> Optional[str]:
    """
    Get a question for a specific phase.

    Args:
        phase: The retrospective phase
        trading_stats: Trading statistics to fill in templates
        question_index: Which question from the phase (0-indexed)

    Returns:
        Formatted question, or None if index out of range
    """
    questions = RETRO_QUESTIONS.get(phase, [])
    if question_index >= len(questions):
        return None

    # Build strategy summary for Review phase
    strategy_summary = "You traded across multiple strategies"
    if trading_stats.get("most_traded_strategy"):
        strategy_summary = f"Your most-used strategy was {trading_stats['most_traded_strategy']}"

    template_vars = {
        "trade_count": trading_stats.get("trade_count", 0),
        "win_rate": trading_stats.get("win_rate", 0),
        "strategy_summary": strategy_summary,
        **trading_stats,
    }

    try:
        return questions[question_index].format(**template_vars)
    except KeyError:
        # Return without formatting if data missing
        return questions[question_index].split('{')[0].rstrip()


def get_next_phase(current: RetroPhase) -> Optional[RetroPhase]:
    """Get the next phase in the mandatory order."""
    try:
        current_index = PHASE_ORDER.index(current)
        if current_index + 1 < len(PHASE_ORDER):
            return PHASE_ORDER[current_index + 1]
        return RetroPhase.COMPLETE
    except ValueError:
        return None


# =============================================================================
# OPENING MESSAGE (Required Pattern)
# =============================================================================

def get_retro_opening(period: RetroPeriod, trade_count: int) -> str:
    """
    Get the opening message for a retro session.

    Uses the required opening pattern from the design spec.
    This is orientation, not content.
    """
    return f"""We're going to look back at {period.label}.
This includes approximately {period.trading_days} trading days and {trade_count} trades.

Does this period feel right?"""


def get_retro_closing() -> str:
    """
    Get the closing message for a retro session.

    No celebration. No score. Just acknowledgment.
    """
    return "This reflection is now part of your record."


def get_phase_header(phase: RetroPhase) -> Dict[str, str]:
    """
    Get the header for a phase (title + subtitle).

    Returns dict with 'title' and 'subtitle' keys.
    """
    return PHASE_HEADERS.get(phase, {"title": phase.value.title(), "subtitle": ""})
