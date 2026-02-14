"""
dcl.py — Doctrine Control Layer.

Determines doctrine mode (STRICT/HYBRID/REFLECTIVE) based on LPD classification.
Provides constraint sets for each mode.

Constitutional constraints:
- STRICT domains (strategy, edge lab, architecture, governance) always get
  full doctrine enforcement.
- HYBRID mode requires structural separation (doctrine first, reflective second).
- REFLECTIVE mode relaxes most checks but preserves sovereignty.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Set

from .lpd import DomainCategory, LPDClassification


class DoctrineMode(Enum):
    STRICT = "strict"
    HYBRID = "hybrid"
    REFLECTIVE = "reflective"


@dataclass
class DoctrineConstraints:
    """Constraint set for a given doctrine mode."""
    require_playbook: bool
    structured_format: bool
    no_new_primitives: bool
    no_speculation: bool
    no_metaphor: bool
    no_roadmap_leak: bool
    allow_avatar_lenses: bool
    allow_reflective_overlay: bool


# Domains that require STRICT mode — no relaxation allowed
STRICT_DOMAINS: Set[DomainCategory] = {
    DomainCategory.STRATEGY_MECHANICS,
    DomainCategory.EDGE_LAB,
    DomainCategory.PRODUCT_ARCHITECTURE,
    DomainCategory.GOVERNANCE_SOVEREIGNTY,
}

# Constraint presets per mode
MODE_CONSTRAINTS = {
    DoctrineMode.STRICT: DoctrineConstraints(
        require_playbook=True,
        structured_format=True,
        no_new_primitives=True,
        no_speculation=True,
        no_metaphor=True,
        no_roadmap_leak=True,
        allow_avatar_lenses=False,
        allow_reflective_overlay=False,
    ),
    DoctrineMode.HYBRID: DoctrineConstraints(
        require_playbook=True,
        structured_format=True,
        no_new_primitives=True,
        no_speculation=True,
        no_metaphor=False,
        no_roadmap_leak=True,
        allow_avatar_lenses=True,
        allow_reflective_overlay=True,
    ),
    DoctrineMode.REFLECTIVE: DoctrineConstraints(
        require_playbook=False,
        structured_format=False,
        no_new_primitives=False,
        no_speculation=False,
        no_metaphor=False,
        no_roadmap_leak=True,
        allow_avatar_lenses=True,
        allow_reflective_overlay=True,
    ),
}


class DoctrineControlLayer:
    """
    Determines doctrine mode and constraints based on LPD classification.

    Strict domains always get STRICT mode.
    Emotional queries get REFLECTIVE mode.
    Mixed (hybrid) gets HYBRID with structural separation requirement.
    """

    def determine_mode(self, classification: LPDClassification) -> DoctrineMode:
        """Determine doctrine mode from LPD classification."""
        domain = classification.domain

        # STRICT for strict domains
        if domain in STRICT_DOMAINS:
            return DoctrineMode.STRICT

        # HYBRID for explicitly hybrid classifications
        if domain == DomainCategory.HYBRID:
            return DoctrineMode.HYBRID

        # REFLECTIVE for emotional/reflective
        if domain == DomainCategory.EMOTIONAL_REFLECTIVE:
            return DoctrineMode.REFLECTIVE

        # PROCESS_DISCIPLINE gets HYBRID (process has doctrine + reflective aspects)
        if domain == DomainCategory.PROCESS_DISCIPLINE:
            return DoctrineMode.HYBRID

        # Default to STRICT for anything else (conservative)
        return DoctrineMode.STRICT

    def get_constraints(self, mode: DoctrineMode) -> DoctrineConstraints:
        """Get constraint set for a doctrine mode."""
        return MODE_CONSTRAINTS.get(mode, MODE_CONSTRAINTS[DoctrineMode.STRICT])

    def allows_overlay(self, mode: DoctrineMode) -> bool:
        """Whether this mode allows overlay injection."""
        constraints = self.get_constraints(mode)
        return constraints.allow_reflective_overlay
