"""
playbook_registry.py — Doctrine Playbook Registry.

Loads structured YAML playbooks from disk, validates provenance tags,
and detects hash mismatches against current PathRuntime state.

Constitutional constraints:
- Every playbook MUST carry doctrine_source, path_runtime_hash, path_runtime_version
- Hash mismatch → CRITICAL log + safe mode (STRICT-only, no playbook injection)
- Safe mode is visible, deterministic, machine-detectable
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class DoctrinePlaybook:
    """A loaded and validated doctrine playbook."""
    domain: str
    version: str
    doctrine_source: str
    path_runtime_version: str
    path_runtime_hash: str
    generated_at: str
    canonical_terminology: Dict[str, str] = field(default_factory=dict)
    definitions: Dict[str, Any] = field(default_factory=dict)
    structural_logic: List[str] = field(default_factory=list)
    mechanisms: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    failure_modes: List[str] = field(default_factory=list)
    non_capabilities: List[str] = field(default_factory=list)


class PlaybookRegistry:
    """
    Registry for doctrine playbooks with provenance validation.

    On startup, loads all YAML playbooks and compares embedded
    path_runtime_hash with current PathRuntime hash. Mismatches
    trigger safe mode — STRICT-only, no playbook injection.
    """

    def __init__(self, playbook_dir: str, path_runtime: Any, logger: Any = None):
        self._playbook_dir = Path(playbook_dir)
        self._path_runtime = path_runtime
        self._logger = logger or logging.getLogger(__name__)
        self._playbooks: Dict[str, DoctrinePlaybook] = {}
        self._safe_mode = False
        self._mismatch_details: List[str] = []

    @property
    def safe_mode(self) -> bool:
        """True if playbooks are out of sync with PathRuntime."""
        return self._safe_mode

    def load_all(self) -> None:
        """
        Load and validate all playbooks from the playbook directory.

        Rejects playbooks missing doctrine_source or hash.
        If any playbook's path_runtime_hash doesn't match current PathRuntime,
        enters safe mode (STRICT-only, no playbook injection).
        """
        self._playbooks.clear()
        self._safe_mode = False
        self._mismatch_details.clear()

        if not self._playbook_dir.exists():
            self._log(
                f"Doctrine playbook directory not found: {self._playbook_dir}",
                emoji="⚠️",
            )
            return

        yaml_files = sorted(self._playbook_dir.glob("*.yaml"))
        if not yaml_files:
            self._log("No doctrine playbooks found", emoji="⚠️")
            return

        # Compute current runtime hash for comparison
        current_hash = self._compute_current_hash()

        for yaml_path in yaml_files:
            try:
                playbook = self._load_playbook(yaml_path)
                if playbook is None:
                    continue

                # Validate provenance
                if not self._validate_provenance(playbook, yaml_path.name):
                    continue

                # Check hash match
                if playbook.path_runtime_hash != current_hash:
                    self._mismatch_details.append(
                        f"{yaml_path.name}: embedded={playbook.path_runtime_hash[:12]}... "
                        f"current={current_hash[:12]}..."
                    )

                self._playbooks[playbook.domain] = playbook

            except Exception as e:
                self._log(f"Failed to load playbook {yaml_path.name}: {e}", emoji="❌")

        # Enter safe mode if any hash mismatches
        if self._mismatch_details:
            self._safe_mode = True
            self._log(
                f"DOCTRINE HASH MISMATCH — entering safe mode. "
                f"Mismatches: {self._mismatch_details}",
                emoji="🚨",
                level="critical",
            )
        else:
            self._log(
                f"Loaded {len(self._playbooks)} doctrine playbooks, all synchronized",
                emoji="📖",
            )

    def _load_playbook(self, yaml_path: Path) -> Optional[DoctrinePlaybook]:
        """Load a single YAML playbook file."""
        with open(yaml_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        if not raw or "playbook" not in raw:
            self._log(f"Invalid playbook format in {yaml_path.name}", emoji="⚠️")
            return None

        pb = raw["playbook"]

        # Parse canonical_terminology from list of {term, definition} dicts
        canon = {}
        for item in pb.get("canonical_terminology", []):
            if isinstance(item, dict) and "term" in item:
                canon[item["term"]] = item.get("definition", "")

        return DoctrinePlaybook(
            domain=pb.get("domain", ""),
            version=pb.get("version", "0.0.0"),
            doctrine_source=pb.get("doctrine_source", ""),
            path_runtime_version=pb.get("path_runtime_version", ""),
            path_runtime_hash=pb.get("path_runtime_hash", ""),
            generated_at=pb.get("generated_at", ""),
            canonical_terminology=canon,
            definitions=pb.get("definitions", {}),
            structural_logic=pb.get("structural_logic", []),
            mechanisms=pb.get("mechanisms", []),
            constraints=pb.get("constraints", []),
            failure_modes=pb.get("failure_modes", []),
            non_capabilities=pb.get("non_capabilities", []),
        )

    def _validate_provenance(self, playbook: DoctrinePlaybook, filename: str) -> bool:
        """Reject playbooks without provenance tags."""
        if playbook.doctrine_source != "path_v4_runtime":
            self._log(
                f"Rejected {filename}: missing or invalid doctrine_source "
                f"(got '{playbook.doctrine_source}')",
                emoji="🚫",
            )
            return False
        if not playbook.path_runtime_hash:
            self._log(f"Rejected {filename}: missing path_runtime_hash", emoji="🚫")
            return False
        if not playbook.path_runtime_version:
            self._log(f"Rejected {filename}: missing path_runtime_version", emoji="🚫")
            return False
        return True

    def _compute_current_hash(self) -> str:
        """Compute hash of current PathRuntime state for comparison."""
        try:
            from services.vexy_ai.doctrine.playbook_generator import PlaybookGenerator
            gen = PlaybookGenerator(self._path_runtime)
            return gen.compute_runtime_hash()
        except Exception as e:
            self._log(f"Cannot compute runtime hash: {e}", emoji="⚠️")
            return ""

    def is_synchronized(self) -> bool:
        """Returns True if all playbooks match current PathRuntime hash."""
        return not self._safe_mode and len(self._playbooks) > 0

    def get_playbook(self, domain: str) -> Optional[DoctrinePlaybook]:
        """Get a playbook by domain name."""
        return self._playbooks.get(domain)

    def get_all_playbooks(self) -> Dict[str, DoctrinePlaybook]:
        """Get all loaded playbooks."""
        return dict(self._playbooks)

    def get_all_canonical_terms(self) -> Dict[str, str]:
        """Get unified canonical terminology from all playbooks."""
        terms = {}
        for pb in self._playbooks.values():
            terms.update(pb.canonical_terminology)
        return terms

    def validate_terms(self, text: str) -> List[str]:
        """
        Check text for non-canonical term usage.

        Returns list of warnings like "Used 'win' — canonical term is 'structural win'".
        """
        warnings = []
        all_terms = self.get_all_canonical_terms()

        text_lower = text.lower()
        for canonical, definition in all_terms.items():
            # Check if the full canonical term is NOT used, but a shorter
            # colloquial variant is. This is heuristic — not exhaustive.
            canonical_lower = canonical.lower()
            if canonical_lower not in text_lower:
                # Check for short-form usage (first word only if multi-word)
                words = canonical_lower.split()
                if len(words) > 1:
                    short_form = words[0]
                    # Only flag if the short form appears as a standalone word
                    if re.search(rf'\b{re.escape(short_form)}\b', text_lower):
                        warnings.append(
                            f"Non-canonical term '{short_form}' — "
                            f"canonical: '{canonical}'"
                        )

        return warnings

    def get_playbook_injection(self, domain: str) -> str:
        """
        Build a prompt injection string for a domain playbook.

        Returns empty string if in safe mode or domain not found.
        """
        if self._safe_mode:
            return ""

        pb = self._playbooks.get(domain)
        if not pb:
            return ""

        parts = [f"## Doctrine Playbook: {pb.domain} (v{pb.version})\n"]

        if pb.canonical_terminology:
            parts.append("### Canonical Terminology\n")
            for term, defn in pb.canonical_terminology.items():
                parts.append(f"- **{term}**: {defn}\n")

        if pb.definitions:
            parts.append("\n### Definitions\n")
            if isinstance(pb.definitions, dict):
                for key, val in pb.definitions.items():
                    parts.append(f"- **{key}**: {val}\n")
            else:
                parts.append(f"{pb.definitions}\n")

        if pb.structural_logic:
            parts.append("\n### Structural Logic\n")
            for item in pb.structural_logic:
                parts.append(f"- {item}\n")

        if pb.constraints:
            parts.append("\n### Constraints\n")
            for item in pb.constraints:
                parts.append(f"- {item}\n")

        if pb.non_capabilities:
            parts.append("\n### Non-Capabilities\n")
            for item in pb.non_capabilities:
                parts.append(f"- {item}\n")

        return "".join(parts)

    def get_health(self) -> Dict[str, Any]:
        """Get registry health status for admin endpoints."""
        return {
            "safe_mode": self._safe_mode,
            "doctrine_synchronized": self.is_synchronized(),
            "playbook_count": len(self._playbooks),
            "playbooks": {
                domain: {
                    "version": pb.version,
                    "generated_at": pb.generated_at,
                    "hash": pb.path_runtime_hash[:12] + "...",
                }
                for domain, pb in self._playbooks.items()
            },
            "mismatch_details": self._mismatch_details if self._safe_mode else [],
        }

    def _log(self, msg: str, emoji: str = "📖", level: str = "info"):
        log_fn = getattr(self._logger, level, None) or getattr(self._logger, "info")
        try:
            log_fn(msg, emoji=emoji)
        except TypeError:
            log_fn(f"{emoji} {msg}")
