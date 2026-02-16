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

import copy
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

OVERRIDE_KEY_PREFIX = "doctrine:playbook_override"


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
        self._base_playbooks: Dict[str, DoctrinePlaybook] = {}
        self._safe_mode = False
        self._mismatch_details: List[str] = []
        self._redis = None

    def set_redis(self, redis_client) -> None:
        """Set Redis client for override persistence."""
        self._redis = redis_client

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
        self._base_playbooks.clear()
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

                # Store base copy before overrides
                self._base_playbooks[playbook.domain] = copy.deepcopy(playbook)

                # Apply Redis overrides
                overrides = self._load_overrides(playbook.domain)
                if overrides:
                    self._apply_overrides(playbook, overrides)

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

    # =================================================================
    # Redis Override System
    # =================================================================

    def _load_overrides(self, domain: str) -> Optional[Dict]:
        """Load admin overrides from Redis for a domain."""
        if not self._redis:
            return None
        try:
            raw = self._redis.get(f"{OVERRIDE_KEY_PREFIX}:{domain}")
            if raw:
                return json.loads(raw)
        except Exception as e:
            self._log(f"Failed to load overrides for {domain}: {e}", emoji="⚠️")
        return None

    def _apply_overrides(self, playbook: DoctrinePlaybook, overrides: Dict) -> None:
        """Apply admin overrides to a playbook (in-place mutation)."""
        if "canonical_terminology" in overrides:
            term_ovr = overrides["canonical_terminology"]
            for term_name in term_ovr.get("remove", []):
                playbook.canonical_terminology.pop(term_name, None)
            for term_name, definition in term_ovr.get("add", {}).items():
                playbook.canonical_terminology[term_name] = definition

        if "definitions" in overrides:
            playbook.definitions.update(overrides["definitions"])

        for list_field in ("structural_logic", "mechanisms", "constraints",
                           "failure_modes", "non_capabilities"):
            if list_field in overrides:
                field_ovr = overrides[list_field]
                base_list = getattr(playbook, list_field)
                remove_indices = sorted(field_ovr.get("remove", []), reverse=True)
                for idx in remove_indices:
                    if 0 <= idx < len(base_list):
                        base_list.pop(idx)
                for item in field_ovr.get("add", []):
                    base_list.append(item)

    def save_override(self, domain: str, field: str, data: Dict) -> bool:
        """Save an admin override for a specific field of a domain playbook."""
        if not self._redis:
            return False
        try:
            existing = self._load_overrides(domain) or {}

            if field == "canonical_terminology":
                current = existing.get("canonical_terminology", {"add": {}, "remove": []})
                if "add" in data:
                    for item in data["add"]:
                        current.setdefault("add", {})[item["term"]] = item["definition"]
                if "remove" in data:
                    current.setdefault("remove", [])
                    for term in data["remove"]:
                        if term not in current["remove"]:
                            current["remove"].append(term)
                        current.get("add", {}).pop(term, None)
                existing["canonical_terminology"] = current

            elif field == "definitions":
                current = existing.get("definitions", {})
                current.update(data)
                existing["definitions"] = current

            elif field in ("structural_logic", "mechanisms", "constraints",
                           "failure_modes", "non_capabilities"):
                current = existing.get(field, {"add": [], "remove": []})
                if "add" in data:
                    current.setdefault("add", []).extend(data["add"])
                if "remove" in data:
                    current.setdefault("remove", [])
                    for idx in data["remove"]:
                        if idx not in current["remove"]:
                            current["remove"].append(idx)
                existing[field] = current
            else:
                return False

            self._redis.set(
                f"{OVERRIDE_KEY_PREFIX}:{domain}", json.dumps(existing)
            )
            self._reload_playbook(domain)
            return True

        except Exception as e:
            self._log(f"Failed to save override for {domain}/{field}: {e}", emoji="❌")
            return False

    def clear_overrides(self, domain: str) -> bool:
        """Clear all admin overrides for a domain, reverting to base YAML."""
        if not self._redis:
            return False
        try:
            self._redis.delete(f"{OVERRIDE_KEY_PREFIX}:{domain}")
            self._reload_playbook(domain)
            return True
        except Exception as e:
            self._log(f"Failed to clear overrides for {domain}: {e}", emoji="❌")
            return False

    def _reload_playbook(self, domain: str) -> None:
        """Reload a single playbook from base + overrides."""
        base = self._base_playbooks.get(domain)
        if not base:
            return
        merged = copy.deepcopy(base)
        overrides = self._load_overrides(domain)
        if overrides:
            self._apply_overrides(merged, overrides)
        self._playbooks[domain] = merged

    def has_overrides(self, domain: str) -> bool:
        """Check if a domain has admin overrides."""
        if not self._redis:
            return False
        try:
            return bool(self._redis.exists(f"{OVERRIDE_KEY_PREFIX}:{domain}"))
        except Exception:
            return False

    def get_full_content(self, domain: str) -> Optional[Dict]:
        """Get full playbook content with source annotations for admin UI."""
        merged = self._playbooks.get(domain)
        base = self._base_playbooks.get(domain)
        if not merged or not base:
            return None

        overrides = self._load_overrides(domain) or {}
        term_ovr = overrides.get("canonical_terminology", {})
        admin_added_terms = set(term_ovr.get("add", {}).keys())
        hidden_terms = set(term_ovr.get("remove", []))

        terms = []
        for term, definition in merged.canonical_terminology.items():
            terms.append({
                "term": term,
                "definition": definition,
                "source": "admin" if term in admin_added_terms else "base",
            })
        for term in hidden_terms:
            if term in base.canonical_terminology:
                terms.append({
                    "term": term,
                    "definition": base.canonical_terminology[term],
                    "source": "base",
                    "hidden": True,
                })

        def annotate_list(field_name: str) -> List[Dict]:
            merged_list = getattr(merged, field_name)
            base_list = getattr(base, field_name)
            field_ovr = overrides.get(field_name, {})
            admin_additions = field_ovr.get("add", [])
            hidden_indices = set(field_ovr.get("remove", []))

            items = []
            for item in merged_list:
                source = "admin" if item in admin_additions else "base"
                items.append({"text": item, "source": source})
            for idx in hidden_indices:
                if 0 <= idx < len(base_list):
                    items.append({
                        "text": base_list[idx], "source": "base", "hidden": True,
                    })
            return items

        def_overrides = overrides.get("definitions", {})
        definitions = {}
        for key, val in merged.definitions.items():
            definitions[key] = {
                "value": val,
                "source": "admin" if key in def_overrides else "base",
            }

        return {
            "domain": merged.domain,
            "version": merged.version,
            "doctrine_source": merged.doctrine_source,
            "path_runtime_version": merged.path_runtime_version,
            "path_runtime_hash": merged.path_runtime_hash,
            "generated_at": merged.generated_at,
            "has_overrides": bool(overrides),
            "canonical_terminology": terms,
            "definitions": definitions,
            "structural_logic": annotate_list("structural_logic"),
            "mechanisms": annotate_list("mechanisms"),
            "constraints": annotate_list("constraints"),
            "failure_modes": annotate_list("failure_modes"),
            "non_capabilities": annotate_list("non_capabilities"),
        }

    def get_diff(self, domain: str) -> Optional[Dict]:
        """Show what admin has changed vs base YAML."""
        base = self._base_playbooks.get(domain)
        merged = self._playbooks.get(domain)
        if not base or not merged:
            return None
        overrides = self._load_overrides(domain) or {}
        return {
            "domain": domain,
            "has_overrides": bool(overrides),
            "overrides": overrides,
            "base": {
                "canonical_terminology": base.canonical_terminology,
                "definitions": base.definitions,
                "structural_logic": base.structural_logic,
                "mechanisms": base.mechanisms,
                "constraints": base.constraints,
                "failure_modes": base.failure_modes,
                "non_capabilities": base.non_capabilities,
            },
            "merged": {
                "canonical_terminology": merged.canonical_terminology,
                "definitions": merged.definitions,
                "structural_logic": merged.structural_logic,
                "mechanisms": merged.mechanisms,
                "constraints": merged.constraints,
                "failure_modes": merged.failure_modes,
                "non_capabilities": merged.non_capabilities,
            },
        }

    # =================================================================
    # Term Registry (Cross-Playbook)
    # =================================================================

    def get_term_registry(self) -> List[Dict]:
        """Get all canonical terms with playbook assignments."""
        term_map: Dict[str, Dict] = {}
        for domain, pb in self._playbooks.items():
            base_pb = self._base_playbooks.get(domain)
            overrides = self._load_overrides(domain) or {}
            admin_terms = set(overrides.get("canonical_terminology", {}).get("add", {}).keys())

            for term, definition in pb.canonical_terminology.items():
                if term not in term_map:
                    term_map[term] = {
                        "term": term,
                        "definition": definition,
                        "playbooks": [],
                        "source": "admin" if term in admin_terms else "base",
                    }
                term_map[term]["playbooks"].append(domain)
                if term in admin_terms:
                    term_map[term]["source"] = "admin"

        return sorted(term_map.values(), key=lambda t: t["term"])

    def add_term_to_playbooks(self, term: str, definition: str,
                              playbooks: List[str]) -> bool:
        """Add a term to one or more playbooks via overrides."""
        if not self._redis:
            return False
        for domain in playbooks:
            if domain not in self._base_playbooks:
                continue
            self.save_override(domain, "canonical_terminology", {
                "add": [{"term": term, "definition": definition}],
            })
        return True

    def remove_term_from_all(self, term: str) -> bool:
        """Hide a term from all playbooks that contain it."""
        if not self._redis:
            return False
        for domain, pb in self._base_playbooks.items():
            if term in pb.canonical_terminology:
                self.save_override(domain, "canonical_terminology", {
                    "remove": [term],
                })
        for domain in list(self._playbooks.keys()):
            overrides = self._load_overrides(domain) or {}
            admin_add = overrides.get("canonical_terminology", {}).get("add", {})
            if term in admin_add:
                del admin_add[term]
                self._redis.set(
                    f"{OVERRIDE_KEY_PREFIX}:{domain}", json.dumps(overrides)
                )
                self._reload_playbook(domain)
        return True

    def update_term(self, term: str, definition: str,
                    playbooks: List[str]) -> bool:
        """Update a term's definition and playbook assignments."""
        if not self._redis:
            return False
        current_playbooks = set()
        for domain, pb in self._playbooks.items():
            if term in pb.canonical_terminology:
                current_playbooks.add(domain)

        target_playbooks = set(playbooks)

        # Add to new playbooks
        for domain in target_playbooks - current_playbooks:
            self.save_override(domain, "canonical_terminology", {
                "add": [{"term": term, "definition": definition}],
            })

        # Remove from old playbooks
        for domain in current_playbooks - target_playbooks:
            self.save_override(domain, "canonical_terminology", {
                "remove": [term],
            })

        # Update definition in remaining playbooks
        for domain in target_playbooks & current_playbooks:
            self.save_override(domain, "canonical_terminology", {
                "add": [{"term": term, "definition": definition}],
            })

        return True

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
