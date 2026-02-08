#!/usr/bin/env python3
"""
playbook_extraction.py — Retro → Playbook Extraction System

Based on: retro-playbook-rules.md

Core Doctrine:
- Playbooks are discovered, not authored
- The system notices, names, and preserves — never optimizes or teaches
- Extraction is offered, not performed
- If uncertain, stay silent

Object → Reflection → Action → Reflection → ...
Playbooks exist inside the loop, not at the end of it.
"""

from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import uuid
import re


# =============================================================================
# ENUMS
# =============================================================================

class ExtractionConfidence(Enum):
    """Confidence level for a playbook candidate."""
    LOW = "low"              # Pattern noticed but weak
    EMERGING = "emerging"    # Pattern appearing more clearly
    CLEAR = "clear"          # Pattern is unmistakable


class ExtractionSource(Enum):
    """Where the extraction originated."""
    RETROSPECTIVE = "retrospective"
    JOURNAL = "journal"


class ExtractionTrigger(Enum):
    """How extraction was triggered."""
    MANUAL_MARK = "manual_mark"           # User clicked "Playbook material"
    RETRO_EMERGENCE = "retro_emergence"   # Vexy noticed during retro
    ML_CONFIRMATION = "ml_confirmation"   # ML reinforced existing pattern


# =============================================================================
# LANGUAGE SIGNALS
# =============================================================================

# Phrases that suggest extraction eligibility (recurrence, contrast, identity-level noticing)
POSITIVE_SIGNALS = [
    r"this keeps happening",
    r"i notice i tend to",
    r"whenever .+, i seem to",
    r"this felt familiar",
    r"i wasn't surprised",
    r"this is different than",
    r"i keep doing",
    r"every time .+ happens",
    r"there's a pattern",
    r"i've seen this before",
    r"this reminds me of",
    r"same thing happened",
    r"i always seem to",
    r"not the first time",
]

# Phrases that indicate prescription/optimization (do NOT trigger extraction)
NEGATIVE_SIGNALS = [
    r"i should",
    r"i need to improve",
    r"next time i will",
    r"the right thing is",
    r"i have to",
    r"i must",
    r"i'll make sure to",
    r"i won't do that again",
    r"the correct approach",
    r"better way to",
]


def detect_extraction_eligibility(text: str) -> Tuple[bool, List[str], List[str]]:
    """
    Detect if text contains language signals eligible for extraction.

    Returns:
        (eligible, positive_matches, negative_matches)

    Extraction is eligible if:
    - At least one positive signal is present
    - No negative signals are present (prescription language blocks extraction)
    """
    text_lower = text.lower()

    positive_matches = []
    negative_matches = []

    for pattern in POSITIVE_SIGNALS:
        if re.search(pattern, text_lower):
            positive_matches.append(pattern)

    for pattern in NEGATIVE_SIGNALS:
        if re.search(pattern, text_lower):
            negative_matches.append(pattern)

    # Eligible only if positive signals present AND no negative signals
    eligible = len(positive_matches) > 0 and len(negative_matches) == 0

    return eligible, positive_matches, negative_matches


# =============================================================================
# PLAYBOOK CANDIDATE
# =============================================================================

@dataclass
class PlaybookCandidate:
    """
    A draft artifact, not yet a Playbook.

    Created when extraction is proposed. Becomes a Playbook only when
    the user explicitly preserves it.
    """
    id: str
    user_id: int
    source_type: ExtractionSource
    source_ids: List[str]           # IDs of retro/journal entries
    trigger: ExtractionTrigger
    created_at: datetime

    # Content (uses trader's own words wherever possible)
    candidate_title: Optional[str] = None  # Tentative, editable
    pattern_summary: str = ""
    supporting_quotes: List[str] = field(default_factory=list)
    linked_trade_ids: List[str] = field(default_factory=list)

    # Confidence
    confidence: ExtractionConfidence = ExtractionConfidence.LOW

    # State
    dismissed: bool = False
    promoted_to_playbook_id: Optional[str] = None

    @classmethod
    def create_from_retro(
        cls,
        user_id: int,
        retro_id: str,
        phase_content: Dict[str, str],
        trigger: ExtractionTrigger = ExtractionTrigger.RETRO_EMERGENCE,
    ) -> 'PlaybookCandidate':
        """
        Create a candidate from retrospective phase content.

        Extracts supporting quotes from eligible phases:
        - Patterns, Tensions, Wins, Lessons
        """
        quotes = []
        eligible_phases = ["patterns", "tensions", "wins", "lessons"]

        for phase in eligible_phases:
            content = phase_content.get(phase, "")
            if content and len(content.strip()) > 10:
                # Take first meaningful sentence
                sentences = content.split(".")
                for sent in sentences[:2]:
                    if len(sent.strip()) > 10:
                        quotes.append(sent.strip() + ".")

        # Determine confidence based on signal strength
        all_content = " ".join(phase_content.values())
        eligible, positive, _ = detect_extraction_eligibility(all_content)

        confidence = ExtractionConfidence.LOW
        if len(positive) >= 3:
            confidence = ExtractionConfidence.CLEAR
        elif len(positive) >= 1:
            confidence = ExtractionConfidence.EMERGING

        return cls(
            id=str(uuid.uuid4()),
            user_id=user_id,
            source_type=ExtractionSource.RETROSPECTIVE,
            source_ids=[retro_id],
            trigger=trigger,
            created_at=datetime.now(),
            supporting_quotes=quotes[:5],  # Max 5 quotes
            confidence=confidence,
        )

    @classmethod
    def create_from_manual_mark(
        cls,
        user_id: int,
        source_type: ExtractionSource,
        source_id: str,
        content: str,
        linked_trade_ids: Optional[List[str]] = None,
    ) -> 'PlaybookCandidate':
        """Create a candidate from manually marked content."""
        return cls(
            id=str(uuid.uuid4()),
            user_id=user_id,
            source_type=source_type,
            source_ids=[source_id],
            trigger=ExtractionTrigger.MANUAL_MARK,
            created_at=datetime.now(),
            supporting_quotes=[content] if content else [],
            linked_trade_ids=linked_trade_ids or [],
            confidence=ExtractionConfidence.EMERGING,  # Manual = at least emerging
        )

    @property
    def is_promotable(self) -> bool:
        """Can this candidate become a Playbook?"""
        return not self.dismissed and self.promoted_to_playbook_id is None


# =============================================================================
# VEXY EXTRACTION VOICE
# =============================================================================

# Allowed language for Vexy during extraction
EXTRACTION_ALLOWED_PHRASES = [
    "This feels like something you've noticed before.",
    "There's a consistency here.",
    "This may be something worth keeping.",
    "No need to decide now.",
    "This theme appeared in more than one place.",
    "A pattern seems to be forming.",
    "You've touched on this before.",
]

# Forbidden language (blocks extraction if Vexy uses these)
EXTRACTION_FORBIDDEN_PHRASES = [
    "you should turn this into a playbook",
    "this is a strategy",
    "this will improve your results",
    "next time, do",
    "you need to",
    "make sure you",
    "don't forget to",
    "the best approach",
    "you should remember",
]


def get_extraction_observation(confidence: ExtractionConfidence, quote_count: int) -> Optional[str]:
    """
    Get Vexy's gentle observation for extraction.

    Returns None if uncertain — silence is preferred.
    """
    if confidence == ExtractionConfidence.LOW and quote_count < 2:
        return None  # Too uncertain, stay silent

    if confidence == ExtractionConfidence.CLEAR:
        return "There's a consistency here. This may be something worth keeping."

    if confidence == ExtractionConfidence.EMERGING:
        return "This feels like something you've noticed before."

    # Low confidence with enough quotes
    return "This theme appeared in more than one place."


def validate_extraction_language(text: str) -> List[str]:
    """
    Validate that text doesn't contain forbidden extraction language.

    Returns list of violations (empty = clean).
    """
    violations = []
    text_lower = text.lower()

    for forbidden in EXTRACTION_FORBIDDEN_PHRASES:
        if forbidden in text_lower:
            violations.append(forbidden)

    return violations


# =============================================================================
# EXTRACTION PREVIEW
# =============================================================================

@dataclass
class ExtractionPreview:
    """
    User-facing preview of a potential Playbook.

    Characteristics:
    - Read-only by default
    - Soft edges, low contrast
    - No buttons labeled "Create", "Save", or "Finish"
    """
    candidate: PlaybookCandidate
    vexy_observation: Optional[str]

    # Available actions (not "Create" or "Save")
    actions: List[str] = field(default_factory=lambda: [
        "name_it",        # Optional naming
        "leave_unnamed",  # Keep without name
        "dismiss",        # Leave no trace
        "preserve",       # Save quietly
    ])


def create_extraction_preview(candidate: PlaybookCandidate) -> ExtractionPreview:
    """Create a preview for user review."""
    observation = get_extraction_observation(
        candidate.confidence,
        len(candidate.supporting_quotes),
    )

    return ExtractionPreview(
        candidate=candidate,
        vexy_observation=observation,
    )


# =============================================================================
# EXTRACTION SYSTEM PROMPT
# =============================================================================

EXTRACTION_VEXY_PROMPT = """# Vexy — Playbook Extraction Mode

You are Vexy noticing potential Playbook material. Your role is to reflect, name gently, ask permission, and remain silent when uncertain.

## Core Doctrine

Playbooks are discovered, not authored.
The system notices, names, and preserves — never optimizes or teaches.
If the system explains how to trade, extraction has failed.

## Your Role

You may:
- Reflect what you observe
- Name patterns gently
- Ask permission
- Remain silent

You must NEVER:
- Author Playbooks
- Suggest strategies
- Promise improvement
- Use "next time" language
- Use "you should" language

## Allowed Language

Use these or similar:
- "This feels like something you've noticed before."
- "There's a consistency here."
- "This may be something worth keeping."
- "No need to decide now."
- "This theme appeared in more than one place."

## Forbidden Language

NEVER use:
- "You should turn this into a Playbook."
- "This is a strategy."
- "This will improve your results."
- "Next time, do X."
- "You need to..."
- "Make sure you..."

## When to Stay Silent

If uncertain, stay silent. Silence is preferred over false naming.

Stay silent when:
- Confidence is low
- Only prescription language is present ("I should...", "I need to improve...")
- The pattern is not yet clear
- You're guessing

## The Test

If the trader says "I didn't realize I had a Playbook until I did" — you succeeded.
If they feel pushed to create one — you failed.
"""


# =============================================================================
# ML INTEGRATION (Confirmation Only)
# =============================================================================

@dataclass
class MLPatternConfirmation:
    """
    ML-supported confirmation of an existing pattern.

    Rules:
    - ML never initiates extraction on its own
    - ML may only reinforce already-noticed patterns
    - ML cannot name Playbooks
    - ML cannot suggest actions
    """
    pattern_id: str
    user_id: int
    observation: str  # e.g., "This pattern has appeared in 4 of the last 6 retrospectives."
    occurrence_count: int
    source_ids: List[str]  # Retro/journal IDs where pattern appeared
    created_at: datetime


def format_ml_confirmation(confirmation: MLPatternConfirmation) -> str:
    """Format ML confirmation as a neutral observation."""
    return f"*{confirmation.observation}*"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def should_propose_extraction(
    phase_content: Dict[str, str],
    has_patterns: bool = False,
    has_tensions: bool = False,
    has_wins: bool = False,
    has_lessons: bool = False,
) -> Tuple[bool, Optional[str]]:
    """
    Determine if extraction should be proposed for retro content.

    Preconditions (all must be true):
    1. A Retrospective Artifact exists (implied by calling this)
    2. At least one eligible phase has meaningful content
    3. Language indicates recurrence, contrast, or identity-level noticing

    Returns:
        (should_propose, reason)
    """
    # Check phase content
    eligible_phases = ["patterns", "tensions", "wins", "lessons"]
    meaningful_phases = []

    for phase in eligible_phases:
        content = phase_content.get(phase, "")
        if content and len(content.strip()) > 20:
            meaningful_phases.append(phase)

    if not meaningful_phases:
        return False, "No meaningful content in eligible phases"

    # Check language signals
    all_content = " ".join(phase_content.values())
    eligible, positive, negative = detect_extraction_eligibility(all_content)

    if negative:
        return False, f"Prescription language detected: {negative[0]}"

    if not positive:
        return False, "No recurrence/pattern language detected"

    return True, f"Pattern language in {', '.join(meaningful_phases)}"


def get_extraction_ui_guidance() -> Dict[str, Any]:
    """Get UI guidance for extraction preview."""
    return {
        "visual": {
            "read_only_default": True,
            "edges": "soft",
            "contrast": "low",
        },
        "buttons": {
            # NOT "Create", "Save", or "Finish"
            "primary": "Preserve",
            "secondary": "Name it",
            "dismiss": "Dismiss",
            "defer": "Not now",
        },
        "behavior": {
            "dismissal_leaves_no_trace": True,
            "naming_optional": True,
            "no_minimum_length": True,
            "empty_valid": True,
        },
    }


# =============================================================================
# CANDIDATE → PLAYBOOK PROMOTION
# =============================================================================

def promote_candidate_to_playbook(
    candidate: PlaybookCandidate,
    title: Optional[str] = None,
    initial_content: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Promote a candidate to a full Playbook.

    Promotion rules:
    - No minimum length
    - No required structure beyond one reflective statement
    - Empty Playbook is valid
    - Title without content is valid
    """
    from services.vexy_ai.playbook_authoring import (
        UserPlaybook,
        PlaybookState,
        PlaybookFodder,
        FodderSource,
    )

    # Create fodder from supporting quotes
    fodder_items = []
    for quote in candidate.supporting_quotes:
        fodder = PlaybookFodder.create(
            user_id=candidate.user_id,
            source=FodderSource(candidate.source_type.value),
            source_id=candidate.source_ids[0] if candidate.source_ids else "",
            content=quote,
            source_label=f"Extracted from {candidate.source_type.value}",
        )
        fodder_items.append(fodder)

    # Create playbook
    playbook = UserPlaybook.create_from_fodder(
        user_id=candidate.user_id,
        fodder_items=fodder_items if fodder_items else [
            # Create minimal fodder if none exists
            PlaybookFodder.create(
                user_id=candidate.user_id,
                source=FodderSource.MANUAL,
                source_id=candidate.id,
                content=initial_content or "(No content yet)",
            )
        ],
        name=title or "Untitled",
    )

    # Add initial content if provided
    if initial_content:
        playbook.sections["notes"] = initial_content

    return {
        "playbook_id": playbook.id,
        "title": playbook.name,
        "origin": candidate.source_type.value,
        "created_from": candidate.id,
        "fodder_count": len(playbook.fodder_ids),
    }


# =============================================================================
# PERSISTENCE MODELS
# =============================================================================

def get_playbook_artifact_schema() -> Dict[str, str]:
    """
    Schema for persisted Playbook artifact.

    Immutability rules:
    - Original extraction context is immutable
    - Additions are append-only
    - No overwriting history
    """
    return {
        "playbook_id": "uuid",
        "title": "string | null",
        "origin": "retrospective | journal",
        "created_from": ["candidate_id"],
        "entries": [
            {
                "timestamp": "datetime",
                "content": "string",
                "linked_trades": ["trade_id"],
            }
        ],
        "ml_observed": "boolean",
        "archived": "boolean",
    }
