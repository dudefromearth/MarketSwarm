"""
Routine Panel v1 — Backend Support

Provides:
1. RoutineContextPhase - Day/time classification for Orientation adaptation
2. RoutineOrientationGenerator - Mode A orientation messages
3. MarketReadinessAggregator - Cached market readiness artifact
4. Lexicon enforcement for doctrine-aligned language

Philosophy: Help the trader arrive, not complete tasks.
Train how to begin, not what to do.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, time
from enum import Enum
import pytz
import random
import os
import json


class RoutineContextPhase(Enum):
    """Day/time classification for Orientation adaptation."""
    WEEKDAY_PREMARKET = "weekday_premarket"      # Before open on trading day
    WEEKDAY_INTRADAY = "weekday_intraday"        # Market open
    WEEKDAY_AFTERHOURS = "weekday_afterhours"    # Post close
    FRIDAY_NIGHT = "friday_night"                # Transition out
    WEEKEND_MORNING = "weekend_morning"          # Rest + reflection potential
    WEEKEND_AFTERNOON = "weekend_afternoon"      # Light maintenance
    WEEKEND_EVENING = "weekend_evening"          # Prep-for-week / intention setting
    HOLIDAY = "holiday"                          # Market closed, reflective tone


# US Market holidays (simplified list - major holidays)
US_MARKET_HOLIDAYS_2025 = {
    "2025-01-01",  # New Year's Day
    "2025-01-20",  # MLK Day
    "2025-02-17",  # Presidents Day
    "2025-04-18",  # Good Friday
    "2025-05-26",  # Memorial Day
    "2025-06-19",  # Juneteenth
    "2025-07-04",  # Independence Day
    "2025-09-01",  # Labor Day
    "2025-11-27",  # Thanksgiving
    "2025-12-25",  # Christmas
}


def get_routine_context_phase(
    now: Optional[datetime] = None,
    holidays: Optional[set] = None
) -> RoutineContextPhase:
    """
    Determine current context phase based on time and day.

    Args:
        now: Current datetime (defaults to now in ET)
        holidays: Set of holiday dates as YYYY-MM-DD strings

    Returns:
        RoutineContextPhase for the current moment
    """
    et = pytz.timezone('America/New_York')

    if now is None:
        now = datetime.now(et)
    elif now.tzinfo is None:
        now = et.localize(now)

    if holidays is None:
        holidays = US_MARKET_HOLIDAYS_2025

    date_str = now.strftime('%Y-%m-%d')
    weekday = now.weekday()  # 0=Monday, 6=Sunday
    current_time = now.time()

    # Check for holiday
    if date_str in holidays:
        return RoutineContextPhase.HOLIDAY

    # Weekend logic
    if weekday == 6:  # Sunday
        if current_time < time(12, 0):
            return RoutineContextPhase.WEEKEND_MORNING
        elif current_time < time(17, 0):
            return RoutineContextPhase.WEEKEND_AFTERNOON
        else:
            return RoutineContextPhase.WEEKEND_EVENING

    if weekday == 5:  # Saturday
        if current_time < time(12, 0):
            return RoutineContextPhase.WEEKEND_MORNING
        elif current_time < time(17, 0):
            return RoutineContextPhase.WEEKEND_AFTERNOON
        else:
            return RoutineContextPhase.WEEKEND_EVENING

    # Friday night transition
    if weekday == 4 and current_time >= time(16, 0):
        return RoutineContextPhase.FRIDAY_NIGHT

    # Weekday logic
    if current_time < time(9, 30):
        return RoutineContextPhase.WEEKDAY_PREMARKET
    elif current_time < time(16, 0):
        return RoutineContextPhase.WEEKDAY_INTRADAY
    else:
        return RoutineContextPhase.WEEKDAY_AFTERHOURS


class RoutineOrientationGenerator:
    """
    Generates Mode A orientation messages.

    Doctrine:
    - May be silent (returns None)
    - Never asks questions
    - Never instructs
    - Adapts to RoutineContextPhase
    """

    # Templates for each phase
    # None in the list means silence is a valid option
    PHASE_TEMPLATES: Dict[RoutineContextPhase, List[Optional[str]]] = {
        RoutineContextPhase.WEEKDAY_PREMARKET: [
            "It's {day_name} morning. {vix_note}",
            "{day_name}. Markets open soon.",
            "Morning. {vix_note}",
            None,  # Silence option
        ],
        RoutineContextPhase.WEEKDAY_INTRADAY: [
            "Markets are open.",
            "{vix_note}",
            None,
        ],
        RoutineContextPhase.WEEKDAY_AFTERHOURS: [
            "Markets have closed for the day.",
            "After hours. The session is done.",
            None,
        ],
        RoutineContextPhase.FRIDAY_NIGHT: [
            "Friday evening. The week closes behind you.",
            "Week's end. Markets rest until Monday.",
            None,
        ],
        RoutineContextPhase.WEEKEND_MORNING: [
            "Saturday. Markets rest. So can you.",
            "Sunday morning. The week ahead is still unwritten.",
            None,
        ],
        RoutineContextPhase.WEEKEND_AFTERNOON: [
            "Weekend afternoon. No urgency here.",
            None,
        ],
        RoutineContextPhase.WEEKEND_EVENING: [
            "Sunday evening. Monday approaches.",
            "The week ahead begins to take shape.",
            None,
        ],
        RoutineContextPhase.HOLIDAY: [
            "Markets are closed today. This space is lighter.",
            "Holiday. Markets rest.",
            None,
        ],
    }

    # VIX regime notes
    VIX_NOTES = {
        'zombieland': "Volatility is suppressed.",
        'goldilocks': "Volatility is moderate.",
        'elevated': "Volatility is elevated.",
        'chaos': "Volatility is running high.",
    }

    def generate(
        self,
        phase: RoutineContextPhase,
        vix_level: Optional[float] = None,
        vix_regime: Optional[str] = None,
    ) -> Optional[str]:
        """
        Generate orientation message for the given phase.

        Args:
            phase: Current routine context phase
            vix_level: Current VIX level
            vix_regime: Current VIX regime (zombieland, goldilocks, elevated, chaos)

        Returns:
            Orientation message or None (silence)
        """
        templates = self.PHASE_TEMPLATES.get(phase, [None])

        # Randomly select a template (including None for silence)
        template = random.choice(templates)

        if template is None:
            return None

        # Get day name
        et = pytz.timezone('America/New_York')
        now = datetime.now(et)
        day_name = now.strftime('%A')

        # Build VIX note
        vix_note = ""
        if vix_regime and vix_regime in self.VIX_NOTES:
            vix_note = self.VIX_NOTES[vix_regime]
        elif vix_level is not None:
            if vix_level < 13:
                vix_note = "Volatility is suppressed."
            elif vix_level < 18:
                vix_note = "Volatility is moderate."
            elif vix_level < 25:
                vix_note = "Volatility is elevated."
            else:
                vix_note = "Volatility is running high."

        # Format template
        message = template.format(
            day_name=day_name,
            vix_note=vix_note,
        )

        # Clean up extra spaces
        message = ' '.join(message.split())

        return message if message.strip() else None


class MarketReadinessAggregator:
    """
    Aggregates market context as a minimal cached artifact.

    Returns read-only awareness data, not predictions.
    Enforces lexicon constraints.

    This is NOT a real-time heavy endpoint - it's a compact daily
    readiness artifact, generated once (or infrequently), cached.
    """

    # Lexicon enforcement
    FORBIDDEN_TERMS = [
        "POC", "VAH", "VAL",
        "point of control", "value area high", "value area low",
    ]

    TERM_REPLACEMENTS = {
        "HVN": "Volume Node",
        "LVN": "Volume Well",
        "thin_zone": "Crevasse",
        "thin zone": "Crevasse",
        "low volume node": "Volume Well",
        "high volume node": "Volume Node",
    }

    WAITING_ANCHOR = (
        "Today is a waiting day until an entry event appears "
        "(or doesn't). Waiting is part of the edge."
    )

    VIX_IMPLICATIONS = {
        'zombieland': "Tight structures may last longer than expected.",
        'goldilocks': "Balanced conditions for patient waiting.",
        'elevated': "Wider structures may develop faster.",
        'chaos': "Expect rapid structure changes.",
    }

    def __init__(self, market_data_service=None, logger=None):
        self.market_data_service = market_data_service
        self.logger = logger

    def aggregate(self, user_id: int) -> Dict[str, Any]:
        """
        Aggregate market readiness data for a user.

        Returns a cached, minimal payload:
        {
            "generated_at": ISO timestamp,
            "context_phase": RoutineContextPhase value,
            "carrying": {
                "globex_summary": str,
                "euro_note": str | None,
                "macro_events": List[str] (max 3),
            },
            "volatility": {
                "vix_level": float,
                "regime": str,
                "implication": str,
            },
            "topology": {
                "structure_synopsis": str,
                "gex_posture": str,
                "key_levels": List[float],
            },
            "waiting_anchor": str,
        }
        """
        phase = get_routine_context_phase()

        # For now, return a template structure
        # In production, this would pull from market data services
        payload = {
            "generated_at": datetime.now(pytz.UTC).isoformat(),
            "context_phase": phase.value,
            "carrying": {
                "globex_summary": "Overnight session data not yet loaded.",
                "euro_note": None,
                "macro_events": [],
            },
            "volatility": {
                "vix_level": None,
                "regime": None,
                "implication": None,
            },
            "topology": {
                "structure_synopsis": "Structure data loading.",
                "gex_posture": None,
                "key_levels": [],
            },
            "waiting_anchor": self.WAITING_ANCHOR,
        }

        return payload

    def aggregate_with_data(
        self,
        globex_summary: Optional[str] = None,
        euro_note: Optional[str] = None,
        macro_events: Optional[List[str]] = None,
        vix_level: Optional[float] = None,
        vix_regime: Optional[str] = None,
        structure_synopsis: Optional[str] = None,
        gex_posture: Optional[str] = None,
        key_levels: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """
        Aggregate market readiness with provided data.

        All text fields are run through lexicon enforcement.
        """
        phase = get_routine_context_phase()

        # Enforce lexicon on text fields
        safe_globex = self._enforce_lexicon(globex_summary or "")
        safe_structure = self._enforce_lexicon(structure_synopsis or "")
        safe_gex = self._enforce_lexicon(gex_posture or "")

        # Determine VIX implication
        vix_implication = None
        if vix_regime and vix_regime in self.VIX_IMPLICATIONS:
            vix_implication = self.VIX_IMPLICATIONS[vix_regime]
        elif vix_level is not None:
            if vix_level < 13:
                vix_implication = self.VIX_IMPLICATIONS['zombieland']
            elif vix_level < 18:
                vix_implication = self.VIX_IMPLICATIONS['goldilocks']
            elif vix_level < 25:
                vix_implication = self.VIX_IMPLICATIONS['elevated']
            else:
                vix_implication = self.VIX_IMPLICATIONS['chaos']

        # Limit macro events to 3
        safe_events = []
        if macro_events:
            safe_events = [self._enforce_lexicon(e) for e in macro_events[:3]]

        payload = {
            "generated_at": datetime.now(pytz.UTC).isoformat(),
            "context_phase": phase.value,
            "carrying": {
                "globex_summary": safe_globex or "No overnight summary available.",
                "euro_note": self._enforce_lexicon(euro_note) if euro_note else None,
                "macro_events": safe_events,
            },
            "volatility": {
                "vix_level": vix_level,
                "regime": vix_regime,
                "implication": vix_implication,
            },
            "topology": {
                "structure_synopsis": safe_structure or "Structure data not available.",
                "gex_posture": safe_gex or None,
                "key_levels": key_levels or [],
            },
            "waiting_anchor": self.WAITING_ANCHOR,
        }

        return payload

    def _enforce_lexicon(self, text: str) -> str:
        """
        Rewrite text to use approved lexicon.

        - Removes forbidden terms
        - Replaces technical terms with doctrine-approved alternatives
        """
        if not text:
            return text

        result = text

        # Check for forbidden terms (case-insensitive)
        for term in self.FORBIDDEN_TERMS:
            if term.lower() in result.lower():
                # Log violation if logger available
                if self.logger:
                    self.logger.warn(
                        f"Lexicon violation detected: '{term}' in text",
                        emoji="⚠️"
                    )
                # Remove the forbidden term
                import re
                result = re.sub(re.escape(term), '[removed]', result, flags=re.IGNORECASE)

        # Apply term replacements
        for old_term, new_term in self.TERM_REPLACEMENTS.items():
            import re
            result = re.sub(re.escape(old_term), new_term, result, flags=re.IGNORECASE)

        return result


# Forbidden language for Routine context (used by post-check)
ROUTINE_FORBIDDEN_LANGUAGE = [
    "you should",
    "consider trading",
    "consider entering",
    "consider exiting",
    "buy",
    "sell",
    "enter",
    "exit",
    "take profit",
    "stop loss",
    "next time",
    "improve",
    "optimize",
    "POC",
    "VAH",
    "VAL",
]


def check_forbidden_language(text: str) -> List[str]:
    """
    Check text for forbidden language in Routine context.

    Returns list of violations found.
    """
    if not text:
        return []

    violations = []
    text_lower = text.lower()

    for phrase in ROUTINE_FORBIDDEN_LANGUAGE:
        if phrase.lower() in text_lower:
            violations.append(phrase)

    return violations


def get_vix_regime(vix_level: float) -> str:
    """
    Determine VIX regime from level.

    Returns: zombieland, goldilocks, elevated, or chaos
    """
    if vix_level < 13:
        return 'zombieland'
    elif vix_level < 18:
        return 'goldilocks'
    elif vix_level < 25:
        return 'elevated'
    else:
        return 'chaos'
