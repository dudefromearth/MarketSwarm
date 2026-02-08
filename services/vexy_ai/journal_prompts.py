#!/usr/bin/env python3
"""
journal_prompts.py — Journal-Specific Vexy Voice & Prompt System

Based on:
- daily-journal.md: Daily Synopsis & Vexy Voice Rules
- vexy-journal.md: Journal Vexy Interaction Model

Core Doctrine:
- The Journal is not a place to perform work. It is a place to notice what occurred.
- Vexy is silent by default. Presence is assumed. Speech is earned.
- Silence is not a failure state. Silence is correct.
"""

from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime, date
from enum import Enum
import random


# =============================================================================
# ENUMS & CONSTANTS
# =============================================================================

class PromptCategory(Enum):
    """Categories for prepared reflective prompts."""
    ATTENTION = "attention"      # Where did focus go?
    CONTRAST = "contrast"        # What differed from what?
    PRESENCE = "presence"        # What felt steady?
    ABSENCE = "absence"          # What didn't happen?


class JournalLens(Enum):
    """Lenses (ways of noticing) for optional focus."""
    MARKET_STRUCTURE = "market_structure"
    EXECUTION_TIMING = "execution_timing"
    RISK_SHAPE = "risk_shape"
    INTERNAL_STATE = "internal_state"
    PRESENCE_ATTENTION = "presence_attention"


# Maximum prepared prompts per day
MAX_PROMPTS_PER_DAY = 2


# =============================================================================
# FORBIDDEN LANGUAGE (Journal-Specific)
# =============================================================================

JOURNAL_FORBIDDEN_LANGUAGE = [
    # Advice-giving
    "you should",
    "consider",
    "next time",
    "improve",

    # Optimization
    "better",
    "worse",
    "optimize",
    "increase",

    # Judgment
    "good day",
    "bad day",
    "mistake",
    "correct",
    "wrong",

    # Forward-looking (belongs in Retrospective)
    "this week",
    "overall",
    "trend",

    # Performance framing
    "win rate",
    "success",
    "failure",
]


# =============================================================================
# DAILY SYNOPSIS STRUCTURE
# =============================================================================

@dataclass
class DailySynopsis:
    """
    The Daily Synopsis: a weather report, not a scorecard.

    Four optional sections, rendered only when data exists.
    No section is mandatory.
    """
    date: date

    # Section A: Activity
    activity: Optional[Dict[str, Any]] = None
    # trade_count, open_count, first_trade_time, last_trade_time, session_window

    # Section B: Rhythm
    rhythm: Optional[Dict[str, Any]] = None
    # clustering, gaps, pacing_note

    # Section C: Risk & Exposure
    risk_exposure: Optional[Dict[str, Any]] = None
    # max_defined_risk, peak_exposure_time, concurrent_positions

    # Section D: Context (optional, situational)
    context: Optional[str] = None
    # e.g., "CPI released pre-market", "Friday session", "Low-liquidity holiday"


def generate_synopsis_section_activity(trades: List[Dict]) -> Optional[Dict[str, Any]]:
    """Generate Activity section from trade data."""
    if not trades:
        return None

    trade_count = len(trades)
    open_trades = [t for t in trades if t.get("status") == "open"]
    closed_trades = [t for t in trades if t.get("status") == "closed"]

    # Extract timestamps
    timestamps = [t.get("timestamp") or t.get("entry_time") for t in trades if t.get("timestamp") or t.get("entry_time")]
    timestamps = sorted([t for t in timestamps if t])

    first_trade = timestamps[0] if timestamps else None
    last_trade = timestamps[-1] if timestamps else None

    # Determine session window
    session_window = None
    if first_trade and last_trade:
        # Parse and determine morning/afternoon
        try:
            first_hour = datetime.fromisoformat(first_trade.replace("Z", "+00:00")).hour
            last_hour = datetime.fromisoformat(last_trade.replace("Z", "+00:00")).hour

            if first_hour < 12 and last_hour < 12:
                session_window = "morning session"
            elif first_hour >= 12 and last_hour >= 12:
                session_window = "afternoon session"
            else:
                session_window = "full session"
        except:
            session_window = None

    return {
        "trade_count": trade_count,
        "open_count": len(open_trades),
        "closed_count": len(closed_trades),
        "first_trade_time": first_trade,
        "last_trade_time": last_trade,
        "session_window": session_window,
    }


def generate_synopsis_section_rhythm(trades: List[Dict]) -> Optional[Dict[str, Any]]:
    """Generate Rhythm section from trade timestamps."""
    if len(trades) < 2:
        return None

    timestamps = [t.get("timestamp") or t.get("entry_time") for t in trades]
    timestamps = sorted([t for t in timestamps if t])

    if len(timestamps) < 2:
        return None

    # Calculate gaps between trades
    gaps = []
    for i in range(1, len(timestamps)):
        try:
            t1 = datetime.fromisoformat(timestamps[i-1].replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(timestamps[i].replace("Z", "+00:00"))
            gaps.append((t2 - t1).total_seconds() / 60)  # minutes
        except:
            continue

    if not gaps:
        return None

    avg_gap = sum(gaps) / len(gaps)
    max_gap = max(gaps)

    # Determine clustering
    clustering = None
    if max_gap > 60:  # More than 1 hour gap
        clustering = "activity clustered with significant gaps"
    elif avg_gap < 10:
        clustering = "rapid succession of trades"
    else:
        clustering = "steady pacing throughout"

    return {
        "clustering": clustering,
        "avg_gap_minutes": round(avg_gap, 1),
        "max_gap_minutes": round(max_gap, 1),
        "trade_count": len(timestamps),
    }


def generate_synopsis_section_risk(trades: List[Dict]) -> Optional[Dict[str, Any]]:
    """Generate Risk & Exposure section."""
    if not trades:
        return None

    # Calculate max defined risk
    max_risk = 0
    concurrent_count = 0

    for trade in trades:
        risk = trade.get("defined_risk") or trade.get("max_loss") or 0
        if isinstance(risk, (int, float)):
            max_risk = max(max_risk, abs(risk))

        if trade.get("status") == "open":
            concurrent_count += 1

    if max_risk == 0 and concurrent_count == 0:
        return None

    return {
        "max_defined_risk": max_risk,
        "concurrent_positions": concurrent_count,
    }


def format_synopsis_text(synopsis: DailySynopsis) -> str:
    """
    Format the synopsis as human-readable text.

    The Synopsis should feel like a weather report, not a scorecard.
    """
    lines = []

    # Activity
    if synopsis.activity:
        a = synopsis.activity
        if a["trade_count"] == 1:
            lines.append(f"1 trade placed")
        else:
            lines.append(f"{a['trade_count']} trades placed")

        if a["open_count"] > 0:
            lines.append(f"{a['open_count']} {'trade remains' if a['open_count'] == 1 else 'trades remain'} open")

        if a["session_window"]:
            lines.append(f"All activity occurred in the {a['session_window']}")

    # Rhythm
    if synopsis.rhythm:
        r = synopsis.rhythm
        if r["clustering"]:
            lines.append(r["clustering"].capitalize())
        if r["max_gap_minutes"] and r["max_gap_minutes"] > 30:
            lines.append(f"Longest gap: {int(r['max_gap_minutes'])} minutes")

    # Risk & Exposure
    if synopsis.risk_exposure:
        re = synopsis.risk_exposure
        if re["max_defined_risk"] > 0:
            lines.append(f"Maximum defined risk: ${re['max_defined_risk']:.0f}")
        if re["concurrent_positions"] > 1:
            lines.append(f"Multiple concurrent positions present")

    # Context
    if synopsis.context:
        lines.append(synopsis.context)

    if not lines:
        return "No market activity recorded today."

    return "\n".join(lines)


# =============================================================================
# PREPARED REFLECTIVE PROMPTS (Mode B)
# =============================================================================

# Prompts by category - each is a single sentence, refers to today only,
# points attention, not outcome
PREPARED_PROMPTS: Dict[PromptCategory, List[str]] = {
    PromptCategory.ATTENTION: [
        "What did you notice about the timing of today's trades?",
        "Where did most of today's activity concentrate?",
        "What drew your attention during the session?",
        "Where did focus land most naturally today?",
    ],
    PromptCategory.CONTRAST: [
        "How did the second half of the session differ from the first?",
        "What changed after the first trade?",
        "What felt different about today compared to yesterday?",
        "Where did the rhythm shift?",
    ],
    PromptCategory.PRESENCE: [
        "What felt steady today?",
        "Where did attention feel strongest?",
        "What remained constant through the session?",
        "When did you feel most present?",
    ],
    PromptCategory.ABSENCE: [
        "What didn't happen today that sometimes does?",
        "What space was left unused?",
        "What remained untouched?",
        "Where was there silence that might have held activity?",
    ],
}


@dataclass
class ReflectivePrompt:
    """A prepared reflective prompt for the Journal."""
    text: str
    category: PromptCategory
    grounded_in: Optional[str] = None  # What data grounds this prompt


def generate_reflective_prompts(
    synopsis: DailySynopsis,
    trades: List[Dict],
    trader_has_written: bool = False,
) -> List[ReflectivePrompt]:
    """
    Generate prepared reflective prompts based on today's data.

    Rules:
    - Maximum 2 prompts per day, often 0
    - Only if sufficient data exists
    - Only if prompt can be grounded in facts
    - Only if language does not imply evaluation
    - Not generated if trader has already written

    Silence is preferable to filler.
    """
    if trader_has_written:
        return []

    if not trades or len(trades) == 0:
        return []

    prompts = []

    # Check for attention-worthy patterns
    if synopsis.activity and synopsis.activity.get("session_window"):
        # Activity concentrated in one session
        prompt = ReflectivePrompt(
            text=random.choice(PREPARED_PROMPTS[PromptCategory.ATTENTION]),
            category=PromptCategory.ATTENTION,
            grounded_in=f"Activity in {synopsis.activity['session_window']}"
        )
        prompts.append(prompt)

    # Check for rhythm patterns
    if synopsis.rhythm:
        r = synopsis.rhythm
        if r.get("max_gap_minutes") and r["max_gap_minutes"] > 45:
            # Significant gap suggests contrast
            prompt = ReflectivePrompt(
                text=random.choice(PREPARED_PROMPTS[PromptCategory.CONTRAST]),
                category=PromptCategory.CONTRAST,
                grounded_in=f"Gap of {int(r['max_gap_minutes'])} minutes observed"
            )
            prompts.append(prompt)
        elif r.get("clustering") and "clustered" in r["clustering"]:
            prompt = ReflectivePrompt(
                text="Where did most of today's activity concentrate?",
                category=PromptCategory.ATTENTION,
                grounded_in=r["clustering"]
            )
            prompts.append(prompt)

    # Check for absence (single trade day)
    if len(trades) == 1:
        prompt = ReflectivePrompt(
            text="What space was left unused?",
            category=PromptCategory.ABSENCE,
            grounded_in="Single-entry day"
        )
        prompts.append(prompt)

    # Limit to MAX_PROMPTS_PER_DAY
    if len(prompts) > MAX_PROMPTS_PER_DAY:
        prompts = random.sample(prompts, MAX_PROMPTS_PER_DAY)

    return prompts


# =============================================================================
# JOURNAL VEXY SYSTEM PROMPT
# =============================================================================

JOURNAL_BASE_PROMPT = """# Vexy — Journal Mode

You are Vexy in **Journal Mode**. The Journal is a space for noticing, not performing.

## Core Doctrine

The Journal is not a place to perform work.
It is a place to notice what occurred.

Vexy is silent by default. Presence is assumed. Speech is earned.

## Your Purpose Here

- Reflect what is observed, nothing more
- Respond when directly asked
- Hold space without filling it
- Allow exit without conclusion

## Two Valid Modes

### Mode A: On-Demand Conversation
When the trader asks directly via the butterfly icon:
- Respond conversationally
- Stay grounded in today's data
- Keep responses short (1-3 paragraphs max)
- End without a question unless explicitly asked

### Mode B: Responding to Prepared Prompts
When the trader clicks a prepared prompt:
- Treat it as a reflection request
- Anchor to observable data
- Name patterns, avoid conclusions
- Stop after observation — no lesson, no advice

## Voice Rules

### Allowed Language
- "Noticing..."
- "This day shows..."
- "A pattern appears..."
- "Most activity occurred..."
- Neutral, observational phrasing

### Forbidden Language (NEVER use these)
- "You should..."
- "Consider..."
- "Next time..."
- "Improve..."
- "Better / worse"
- "Good day / bad day"
- "Mistake"
- "Success / failure"
- "This week..." (belongs in Retrospective)
- "Overall..." (belongs in Retrospective)
- "Trend..." (belongs in Retrospective)

## Response Shape

Responses must:
- Be short (1-3 paragraphs max)
- Be grounded in observable facts from today
- End without a question (unless asked for one)
- Avoid any forward-looking language

Ending with silence is acceptable.

## Context Boundaries

You have access to:
- Today's Daily Synopsis
- Today's trades
- Calendar date

You do NOT have access to:
- Previous days' context
- Retrospectives
- Future context

If the trader asks for coaching, skill building, strategy refinement, or goal setting:

> "That kind of reflection lives better in the Retrospective."
> or
> "This is something the Playbook holds more clearly."

## The Loop

Object → Reflection → Action

The trader learns:
- To see before speaking
- To ask when ready
- To leave when complete

Silence is success.

## Today's Context

{synopsis_text}

{trade_context}
"""


JOURNAL_DIRECT_QUESTION_PROMPT = """The trader has asked a direct question in the Journal.

Remember:
- Respond conversationally but briefly
- Stay grounded in today's observable facts
- No advice, no optimization, no forward-looking language
- 1-3 paragraphs maximum
- End without a question unless they asked for one

Vexy reflects only what is present.
"""


JOURNAL_PREPARED_PROMPT_RESPONSE = """The trader clicked a prepared reflective prompt. This is Mode B.

The prompt was: "{prompt_text}"

Your response must:
- Anchor to observable data from today
- Name patterns without drawing conclusions
- Be brief (1-2 paragraphs)
- Stop after observation

No lesson. No advice. No "this means."

Example good response:
"Most trades occurred within a narrow window early in the session. After that point, activity dropped off significantly."

Stop there.
"""


# =============================================================================
# LENS DESCRIPTIONS
# =============================================================================

LENS_DESCRIPTIONS: Dict[JournalLens, str] = {
    JournalLens.MARKET_STRUCTURE: "Focus attention on how market structure shaped today's activity",
    JournalLens.EXECUTION_TIMING: "Notice the timing and pacing of entries and exits",
    JournalLens.RISK_SHAPE: "Observe the shape of risk exposure through the session",
    JournalLens.INTERNAL_STATE: "Reflect on internal state during trading moments",
    JournalLens.PRESENCE_ATTENTION: "Notice where attention was strongest and where it wandered",
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_journal_prompt(
    synopsis: DailySynopsis,
    trades: List[Dict],
    mode: str = "direct",  # "direct" or "prepared"
    prepared_prompt_text: Optional[str] = None,
) -> str:
    """
    Build the complete system prompt for Journal mode.

    Args:
        synopsis: Today's Daily Synopsis
        trades: Today's trades
        mode: "direct" for on-demand conversation, "prepared" for prompt response
        prepared_prompt_text: The text of the prepared prompt (if mode="prepared")

    Returns:
        Complete system prompt for Vexy in Journal mode
    """
    synopsis_text = format_synopsis_text(synopsis)

    # Format trade context
    if trades:
        trade_lines = []
        for i, t in enumerate(trades, 1):
            strategy = t.get("strategy", "Unknown")
            status = t.get("status", "unknown")
            trade_lines.append(f"Trade {i}: {strategy} ({status})")
        trade_context = "Today's trades:\n" + "\n".join(trade_lines)
    else:
        trade_context = "No trades today."

    base = JOURNAL_BASE_PROMPT.format(
        synopsis_text=synopsis_text,
        trade_context=trade_context,
    )

    if mode == "prepared" and prepared_prompt_text:
        base += "\n\n" + JOURNAL_PREPARED_PROMPT_RESPONSE.format(
            prompt_text=prepared_prompt_text
        )
    else:
        base += "\n\n" + JOURNAL_DIRECT_QUESTION_PROMPT

    return base


def should_vexy_speak(
    synopsis: DailySynopsis,
    trades: List[Dict],
    trader_has_written: bool = False,
) -> tuple[bool, Optional[str]]:
    """
    Determine if Vexy should surface a reflection unprompted.

    Returns:
        (should_speak, reflection_text) - reflection_text is None if should_speak is False

    Vexy may surface at most one reflection when ALL conditions are met:
    1. A meaningful pattern exists
    2. The pattern is non-obvious from the Synopsis alone
    3. The language can remain purely reflective
    4. The trader has not already written
    """
    # Condition 4: Trader has written
    if trader_has_written:
        return False, None

    # No trades = no reflection
    if not trades or len(trades) == 0:
        return False, None

    # Look for non-obvious patterns

    # Pattern: Unusually clustered activity
    if synopsis.rhythm and synopsis.rhythm.get("avg_gap_minutes"):
        avg = synopsis.rhythm["avg_gap_minutes"]
        if avg < 5 and len(trades) >= 3:
            return True, "Most activity occurred within a short window early in the session."

    # Pattern: Single trade with high risk
    if len(trades) == 1:
        trade = trades[0]
        risk = trade.get("defined_risk") or trade.get("max_loss") or 0
        if risk > 500:  # Threshold for "high risk"
            return True, "A single position was taken today with significant defined risk."

    # Default: Stay silent
    return False, None


def validate_response_language(response: str) -> List[str]:
    """
    Check if a response contains forbidden language.

    Returns list of violations found (empty list = clean).
    """
    violations = []
    response_lower = response.lower()

    for forbidden in JOURNAL_FORBIDDEN_LANGUAGE:
        if forbidden in response_lower:
            violations.append(forbidden)

    return violations


# =============================================================================
# SYNOPSIS BUILDER
# =============================================================================

def build_daily_synopsis(
    trade_date: date,
    trades: List[Dict],
    market_context: Optional[str] = None,
) -> DailySynopsis:
    """
    Build a complete Daily Synopsis from trade data.

    Args:
        trade_date: The date for this synopsis
        trades: List of trade dictionaries
        market_context: Optional context string (e.g., "CPI released pre-market")

    Returns:
        DailySynopsis object ready for display
    """
    return DailySynopsis(
        date=trade_date,
        activity=generate_synopsis_section_activity(trades),
        rhythm=generate_synopsis_section_rhythm(trades),
        risk_exposure=generate_synopsis_section_risk(trades),
        context=market_context,
    )
