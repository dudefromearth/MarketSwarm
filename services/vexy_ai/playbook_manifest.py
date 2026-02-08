#!/usr/bin/env python3
"""
playbook_manifest.py — Playbook Registry for Vexy Chat

Defines available Playbooks with metadata for:
- Playbook-aware chat responses
- Tier-gated access
- Redirection language

Playbooks hold structure; chat holds presence.
Vexy references Playbooks rather than explaining them inline.
"""

from typing import List, Optional
from dataclasses import dataclass


@dataclass
class Playbook:
    """A Playbook entry with metadata."""
    name: str
    scope: str  # Routine, Process, Strategy, App, Retrospective
    description: str
    min_tier: str  # observer, activator, navigator, administrator
    keywords: List[str]  # For matching user queries


# =============================================================================
# PLAYBOOK REGISTRY
# =============================================================================

PLAYBOOKS: List[Playbook] = [
    # ---------------------------------------------------------------------
    # ROUTINE PLAYBOOKS (Level 2 - Orientation & Presence)
    # ---------------------------------------------------------------------
    Playbook(
        name="Morning Orientation",
        scope="Routine",
        description="Pre-market grounding and presence calibration",
        min_tier="observer",
        keywords=["morning", "routine", "orientation", "start day", "begin"],
    ),
    Playbook(
        name="Fundamental Acts",
        scope="Routine",
        description="The four questions that precede any trading day",
        min_tier="observer",
        keywords=["fundamental", "acts", "questions", "intention", "focus"],
    ),

    # ---------------------------------------------------------------------
    # PROCESS PLAYBOOKS (Level 2 - Integration)
    # ---------------------------------------------------------------------
    Playbook(
        name="Process Echo",
        scope="Process",
        description="Connecting Routine observations to session outcomes",
        min_tier="activator",
        keywords=["process", "echo", "integration", "session", "end of day"],
    ),
    Playbook(
        name="Trade Journaling",
        scope="Process",
        description="Capturing the what, why, and reflection of each trade",
        min_tier="observer",
        keywords=["journal", "journaling", "record", "trade log", "entry"],
    ),

    # ---------------------------------------------------------------------
    # STRATEGY PLAYBOOKS (Level 4 - Tactical)
    # ---------------------------------------------------------------------
    Playbook(
        name="Convexity Hunting",
        scope="Strategy",
        description="Identifying and positioning for asymmetric payoff regimes",
        min_tier="activator",
        keywords=["convexity", "asymmetric", "payoff", "hunting", "optionality"],
    ),
    Playbook(
        name="0DTE Tactical",
        scope="Strategy",
        description="Same-day expiration structure and risk framing",
        min_tier="navigator",
        keywords=["0dte", "zero dte", "same day", "expiration", "intraday"],
    ),
    Playbook(
        name="Batman Structure",
        scope="Strategy",
        description="Broken-wing butterfly construction and management",
        min_tier="navigator",
        keywords=["batman", "broken wing", "butterfly", "bwb", "structure"],
    ),
    Playbook(
        name="TimeWarp",
        scope="Strategy",
        description="Calendar and diagonal spread regime alignment",
        min_tier="navigator",
        keywords=["timewarp", "calendar", "diagonal", "time spread", "theta"],
    ),
    Playbook(
        name="Goldilocks Regime",
        scope="Strategy",
        description="Trading the VIX 17-25 sweet spot",
        min_tier="activator",
        keywords=["goldilocks", "regime", "vix", "volatility", "sweet spot"],
    ),

    # ---------------------------------------------------------------------
    # APP PLAYBOOKS (Level 3 - Major Applications)
    # ---------------------------------------------------------------------
    Playbook(
        name="Dealer Gravity",
        scope="App",
        description="GEX-based support/resistance and market maker positioning",
        min_tier="activator",
        keywords=["dealer", "gravity", "gex", "gamma", "support", "resistance", "walls"],
    ),
    Playbook(
        name="Risk Graph",
        scope="App",
        description="Position visualization and P/L scenario analysis",
        min_tier="observer",
        keywords=["risk", "graph", "pnl", "profit", "loss", "visualization"],
    ),
    Playbook(
        name="Convexity Heatmap",
        scope="App",
        description="Identifying asymmetric opportunity across strikes and expirations",
        min_tier="activator",
        keywords=["heatmap", "convexity", "strikes", "expiration", "opportunity"],
    ),
    Playbook(
        name="Alert System",
        scope="App",
        description="Price, level, and condition-based notifications",
        min_tier="observer",
        keywords=["alert", "alerts", "notification", "price", "trigger"],
    ),

    # ---------------------------------------------------------------------
    # RETROSPECTIVE PLAYBOOKS (Level 5 - Wisdom Loop)
    # ---------------------------------------------------------------------
    Playbook(
        name="Weekly Retrospective",
        scope="Retrospective",
        description="Pattern review and process refinement",
        min_tier="activator",
        keywords=["weekly", "retrospective", "review", "patterns", "week"],
    ),
    Playbook(
        name="Monthly Synthesis",
        scope="Retrospective",
        description="Deeper pattern recognition and evolution tracking",
        min_tier="navigator",
        keywords=["monthly", "synthesis", "evolution", "month", "long-term"],
    ),

    # ---------------------------------------------------------------------
    # META / PATH PLAYBOOKS (Level 0-1)
    # ---------------------------------------------------------------------
    Playbook(
        name="The Path",
        scope="Meta",
        description="The meta-framework governing all practice",
        min_tier="observer",
        keywords=["path", "framework", "philosophy", "practice", "loop"],
    ),
    Playbook(
        name="Shu-Ha-Ri",
        scope="Meta",
        description="Mastery progression through follow, break, transcend",
        min_tier="observer",
        keywords=["shu", "ha", "ri", "mastery", "progression", "learning"],
    ),
    Playbook(
        name="Echo Memory Protocol",
        scope="Meta",
        description="Cross-session continuity and relationship memory",
        min_tier="activator",
        keywords=["echo", "memory", "continuity", "relationship", "protocol"],
    ),
]


# =============================================================================
# LOOKUP FUNCTIONS
# =============================================================================

def get_playbook(name: str) -> Optional[Playbook]:
    """Get a playbook by exact name."""
    for pb in PLAYBOOKS:
        if pb.name.lower() == name.lower():
            return pb
    return None


def get_playbooks_for_tier(tier: str) -> List[Playbook]:
    """Get all playbooks accessible at a given tier."""
    tier_order = ["observer", "activator", "navigator", "coaching", "administrator"]
    tier_idx = tier_order.index(tier.lower()) if tier.lower() in tier_order else 0

    accessible = []
    for pb in PLAYBOOKS:
        pb_idx = tier_order.index(pb.min_tier) if pb.min_tier in tier_order else 0
        if tier_idx >= pb_idx:
            accessible.append(pb)

    return accessible


def find_relevant_playbooks(query: str, tier: str, max_results: int = 3) -> List[Playbook]:
    """
    Find playbooks relevant to a user query.

    Returns playbooks that:
    1. Match keywords in the query
    2. Are accessible at the user's tier
    """
    query_lower = query.lower()
    accessible = get_playbooks_for_tier(tier)

    # Score by keyword matches
    scored = []
    for pb in accessible:
        score = sum(1 for kw in pb.keywords if kw in query_lower)
        if score > 0:
            scored.append((score, pb))

    # Sort by score descending
    scored.sort(key=lambda x: -x[0])

    return [pb for _, pb in scored[:max_results]]


def format_playbooks_for_prompt(playbooks: List[Playbook]) -> str:
    """Format playbooks for inclusion in system prompt."""
    if not playbooks:
        return ""

    lines = ["## Available Playbooks", ""]
    for pb in playbooks:
        lines.append(f"- **{pb.name}** ({pb.scope}): {pb.description}")

    lines.append("")
    lines.append("When relevant, reference these Playbooks by name rather than explaining their content.")
    lines.append("Playbooks hold structure; you hold presence.")

    return "\n".join(lines)


def get_playbook_names_for_tier(tier: str) -> List[str]:
    """Get just the names of accessible playbooks for a tier."""
    return [pb.name for pb in get_playbooks_for_tier(tier)]
