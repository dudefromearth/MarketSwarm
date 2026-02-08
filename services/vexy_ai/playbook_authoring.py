#!/usr/bin/env python3
"""
playbook_authoring.py — User-Authored Playbook System

Based on: playbook-design-spec.md

Core Doctrine:
- Playbooks are distilled lived knowledge, not recipes
- Playbooks are written after reflection, not during action
- Extraction, not invention
- "What keeps appearing?" — not "What should your playbook say?"

A Playbook is never created from an empty state.
It emerges from marked material: Journal entries, Retrospective excerpts, ML patterns.
"""

from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import uuid


# =============================================================================
# ENUMS
# =============================================================================

class PlaybookState(Enum):
    """Visibility states for playbooks."""
    DRAFT = "draft"          # Private, evolving
    ACTIVE = "active"        # Referenced by Vexy
    ARCHIVED = "archived"    # Read-only, still consultable

    # Note: Deletion is NOT permitted


class FodderSource(Enum):
    """Valid sources for playbook material."""
    JOURNAL = "journal"              # Journal entries
    RETROSPECTIVE = "retrospective"  # Retrospective phase responses
    ML_PATTERN = "ml_pattern"        # ML-flagged patterns
    TRADE = "trade"                  # Linked trades
    MANUAL = "manual"                # Manual marking


class PlaybookSection(Enum):
    """Optional canonical sections. None are required."""
    CONTEXT = "context"              # When does this matter?
    SIGNAL = "signal"                # How do I notice it?
    RESPONSE = "response"            # What do I do when I see it?
    FAILURE_MODE = "failure_mode"    # How does this break?
    NOTES = "notes"                  # Open reflection


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class PlaybookFodder:
    """
    Raw material that may become part of a Playbook.

    Created when user clicks "Mark as Playbook Material".
    This does NOT create a Playbook — it creates fodder.
    """
    id: str
    user_id: int
    source: FodderSource
    source_id: str              # ID of the source (journal entry, retro, trade)
    content: str                # The actual text/content
    created_at: datetime
    marked_at: datetime

    # Optional context
    source_date: Optional[datetime] = None
    source_label: Optional[str] = None  # e.g., "Retrospective - Patterns Phase"

    # Linking
    linked_playbook_id: Optional[str] = None  # If pulled into a playbook

    @classmethod
    def create(
        cls,
        user_id: int,
        source: FodderSource,
        source_id: str,
        content: str,
        source_date: Optional[datetime] = None,
        source_label: Optional[str] = None,
    ) -> 'PlaybookFodder':
        """Create new fodder."""
        now = datetime.now()
        return cls(
            id=str(uuid.uuid4()),
            user_id=user_id,
            source=source,
            source_id=source_id,
            content=content,
            created_at=now,
            marked_at=now,
            source_date=source_date,
            source_label=source_label,
        )


@dataclass
class PlaybookRevision:
    """
    A point-in-time snapshot of playbook content.

    Edits preserve history — revisions are never deleted.
    """
    id: str
    playbook_id: str
    created_at: datetime
    sections: Dict[str, str]    # section_name -> content
    fodder_ids: List[str]       # IDs of fodder included at this revision


@dataclass
class UserPlaybook:
    """
    A user-authored Playbook.

    - Never created from empty state
    - Evolves over time
    - Never deleted (only archived)
    - Edits preserve history
    """
    id: str
    user_id: int
    name: str
    state: PlaybookState
    created_at: datetime
    updated_at: datetime

    # Current content (by optional section)
    sections: Dict[str, str] = field(default_factory=dict)

    # Linked fodder (source material)
    fodder_ids: List[str] = field(default_factory=list)

    # Revision history (immutable)
    revision_ids: List[str] = field(default_factory=list)

    # Metadata
    tags: List[str] = field(default_factory=list)

    @classmethod
    def create_from_fodder(
        cls,
        user_id: int,
        fodder_items: List[PlaybookFodder],
        name: str = "Untitled",
    ) -> 'UserPlaybook':
        """
        Create a new playbook from fodder.

        Playbooks are NEVER created empty.
        """
        if not fodder_items:
            raise ValueError("Cannot create playbook without fodder material")

        now = datetime.now()
        return cls(
            id=str(uuid.uuid4()),
            user_id=user_id,
            name=name,
            state=PlaybookState.DRAFT,
            created_at=now,
            updated_at=now,
            fodder_ids=[f.id for f in fodder_items],
        )

    @property
    def is_draft(self) -> bool:
        return self.state == PlaybookState.DRAFT

    @property
    def is_active(self) -> bool:
        return self.state == PlaybookState.ACTIVE

    @property
    def is_archived(self) -> bool:
        return self.state == PlaybookState.ARCHIVED


# =============================================================================
# SECTION METADATA
# =============================================================================

SECTION_PROMPTS: Dict[PlaybookSection, Dict[str, str]] = {
    PlaybookSection.CONTEXT: {
        "title": "Context",
        "prompt": "When does this matter?",
        "description": "The conditions or situations where this insight applies",
    },
    PlaybookSection.SIGNAL: {
        "title": "Signal / Recognition",
        "prompt": "How do I notice it?",
        "description": "What tells you this pattern is present",
    },
    PlaybookSection.RESPONSE: {
        "title": "Response",
        "prompt": "What do I do when I see it?",
        "description": "The action or non-action this calls for",
    },
    PlaybookSection.FAILURE_MODE: {
        "title": "Failure Mode",
        "prompt": "How does this break?",
        "description": "When this pattern misleads or doesn't apply",
    },
    PlaybookSection.NOTES: {
        "title": "Notes",
        "prompt": "Open reflection",
        "description": "Anything else that belongs here",
    },
}


# =============================================================================
# UI GUIDANCE
# =============================================================================

PLAYBOOK_UI_GUIDANCE = {
    # Mental mode
    "felt_experience": "Integration",
    "mode": "Enduring",

    # Visual treatment
    "visual": {
        "feel": ["calm", "sparse", "slow", "deliberate"],
        "urgency": False,
        "completion_sense": False,
    },

    # Layout
    "layout": {
        "left_rail": "sources",         # Source constellation
        "main": "authoring_surface",     # Integrated text
        "left_rail_readonly": True,      # Sources are read-only
    },

    # Initial state
    "initial_prompt": "Here are the moments you marked. What connects them?",

    # Authoring actions
    "supported_actions": [
        "quoting",      # Pull excerpts into surface
        "rephrasing",   # Rewrite in own words
        "merging",      # Collapse observations into one insight
        "annotating",   # Add context
        "highlighting", # Highlight phrases
    ],

    # Anti-patterns (hard rules)
    "forbidden": {
        "gamification": True,
        "quality_scores": True,
        "completion_tracking": True,
        "ranking": True,
        "volume_encouragement": True,
        "blank_page_creation": True,
    },
}


# =============================================================================
# VEXY VOICE FOR PLAYBOOK AUTHORING
# =============================================================================

PLAYBOOK_VEXY_PROMPT = """# Vexy — Playbook Authoring Mode

You are Vexy assisting with **Playbook authoring**. This is an integration space where lived experience becomes distilled knowledge.

## What a Playbook Is

A Playbook is **distilled lived knowledge** — not a recipe, ruleset, checklist, or tutorial.

It is:
- A crystallization of repeated experience
- A container for wisdom discovered, not prescribed
- A reusable lens the trader can return to

> Playbooks are written after reflection, not during action.

## Your Role

You may:
- Reflect similarities across fodder
- Point out repeated language or themes
- Ask clarifying questions
- Suggest consolidation of ideas

Example:
"These three excerpts all reference hesitation near structure. Is that intentional?"

## What You Must NEVER Do

You must not:
- Write the Playbook for them
- Suggest optimization
- Prescribe improvements
- Turn the Playbook into a system
- Use "You should add..." or "A better version would be..."

The trader discovers. You reflect.

## Voice

Your voice here is:
- Calm
- Sparse
- Integrative
- Patient

You are not teaching. You are mirroring what they've already learned.

## Guiding Question

Never ask: "What should your playbook say?"

Only ever ask: "What keeps appearing?"

## The Doctrine

- Object → Reflection → Action
- Extraction, not invention
- Presence over performance
- Antifragility — learning from variance, not optimizing it away

## North Star

If the trader says:
"This feels like something *I discovered*, not something the app taught me."

Then you succeeded.
"""


PLAYBOOK_FORBIDDEN_LANGUAGE = [
    "you should add",
    "a better version",
    "improve this",
    "optimize",
    "you need to include",
    "don't forget to",
    "make sure you",
    "best practice",
    "you're missing",
    "add more detail",
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_section_info(section: PlaybookSection) -> Dict[str, str]:
    """Get metadata for a playbook section."""
    return SECTION_PROMPTS.get(section, {
        "title": section.value.replace("_", " ").title(),
        "prompt": "",
        "description": "",
    })


def validate_vexy_response(response: str) -> List[str]:
    """
    Check if a Vexy response contains forbidden language.

    Returns list of violations (empty = clean).
    """
    violations = []
    response_lower = response.lower()

    for forbidden in PLAYBOOK_FORBIDDEN_LANGUAGE:
        if forbidden in response_lower:
            violations.append(forbidden)

    return violations


def format_fodder_for_authoring(fodder_items: List[PlaybookFodder]) -> str:
    """
    Format fodder items for display in the authoring surface.

    These appear in the left rail as read-only source material.
    """
    if not fodder_items:
        return "No material marked yet."

    lines = []
    for item in sorted(fodder_items, key=lambda x: x.marked_at):
        source_label = item.source_label or item.source.value.replace("_", " ").title()
        date_str = item.source_date.strftime("%b %d") if item.source_date else ""

        lines.append(f"**{source_label}** {date_str}")
        lines.append(f"> {item.content[:200]}{'...' if len(item.content) > 200 else ''}")
        lines.append("")

    return "\n".join(lines)


def get_authoring_prompt(fodder_items: List[PlaybookFodder]) -> str:
    """
    Build the opening prompt for playbook authoring.

    Never starts with a blank page.
    """
    if not fodder_items:
        return "Mark some material as Playbook fodder first, then return here."

    fodder_text = format_fodder_for_authoring(fodder_items)

    return f"""## Source Material

{fodder_text}

---

*Here are the moments you marked. What connects them?*
"""


def get_vexy_playbook_prompt(fodder_items: List[PlaybookFodder]) -> str:
    """
    Build the complete Vexy system prompt for playbook authoring.
    """
    fodder_context = format_fodder_for_authoring(fodder_items)

    return f"""{PLAYBOOK_VEXY_PROMPT}

## Current Fodder

{fodder_context}

Remember: You reflect what they've marked. You do not write the playbook.
"""


# =============================================================================
# ML INTEGRATION (Mirror, Not Model)
# =============================================================================

@dataclass
class MLObservation:
    """
    A neutral ML-derived observation.

    No confidence scores. No recommendations. No conclusions.
    ML functions as a lantern, not a judge.
    """
    id: str
    user_id: int
    observation_type: str       # e.g., "phrase_frequency", "setup_correlation"
    content: str                # The neutral observation text
    created_at: datetime
    source_ids: List[str]       # IDs of source material

    # Examples of valid observations:
    # - "This phrase appears in 7 retrospectives."
    # - "This setup correlates with your strongest exits."

    # NOT valid:
    # - "You should focus on this pattern."
    # - "This is your best setup (85% confidence)."


def format_ml_observation(obs: MLObservation) -> str:
    """Format an ML observation for display. Neutral language only."""
    return f"*{obs.content}*"


# =============================================================================
# DOWNSTREAM USE
# =============================================================================

def get_active_playbooks_for_user(user_id: int, playbooks: List[UserPlaybook]) -> List[UserPlaybook]:
    """
    Get active playbooks for a user.

    Active playbooks may inform:
    - Routine prompts
    - Process Echo language
    - Vexy reflections
    - Alert phrasing
    - Strategy context

    They are consulted, never executed.
    """
    return [pb for pb in playbooks if pb.user_id == user_id and pb.state == PlaybookState.ACTIVE]


def format_playbooks_for_vexy_context(playbooks: List[UserPlaybook]) -> str:
    """
    Format user playbooks for inclusion in Vexy's context.

    Vexy references playbooks but does not execute them.
    """
    if not playbooks:
        return ""

    lines = ["## User's Active Playbooks", ""]
    for pb in playbooks:
        lines.append(f"- **{pb.name}**")
        if pb.sections.get("context"):
            # Include context section if present
            context = pb.sections["context"][:150]
            lines.append(f"  Context: {context}...")
        lines.append("")

    lines.append("Reference these by name when relevant. They represent the trader's own distilled wisdom.")
    lines.append("Do not explain their content — let the trader consult them directly.")

    return "\n".join(lines)
