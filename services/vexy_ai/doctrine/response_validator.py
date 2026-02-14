"""
response_validator.py — Post-LLM Response Validator.

Validates responses against active doctrine mode with tiered severity:
- FATAL hard blocks (capital steering, unapproved features, roadmap leak)
  → regenerate; if second failure → controlled error, NOT invalid output
- CORRECTABLE hard blocks (optimization phrasing, primitive invention)
  → regenerate; if second failure → return with violation note
- SOFT warnings (non-canonical synonyms, terminology drift)
  → logged only, never regenerated

Constitutional constraint: Validation splits into hard blocks and soft warnings.
Only hard blocks trigger regeneration. This prevents over-strict vocabulary
policing from degrading natural language quality.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .playbook_registry import PlaybookRegistry


class ValidationSeverity(Enum):
    FATAL_HARD = "fatal_hard"        # Regenerate; if persist → controlled error
    CORRECTABLE_HARD = "correctable_hard"  # Regenerate; if persist → violation note
    SOFT_WARNING = "soft_warning"     # Logged only, never regenerated


@dataclass
class ValidationViolation:
    rule: str
    description: str
    severity: ValidationSeverity
    evidence: str = ""


@dataclass
class ValidationResult:
    passed: bool                           # False if any hard blocks
    hard_violations: List[ValidationViolation] = field(default_factory=list)
    soft_warnings: List[ValidationViolation] = field(default_factory=list)
    regenerate: bool = False               # True only for hard blocks

    @property
    def fatal_violations(self) -> List[ValidationViolation]:
        return [v for v in self.hard_violations if v.severity == ValidationSeverity.FATAL_HARD]

    @property
    def correctable_violations(self) -> List[ValidationViolation]:
        return [v for v in self.hard_violations if v.severity == ValidationSeverity.CORRECTABLE_HARD]


# =============================================================================
# VALIDATION PATTERNS
# =============================================================================

# FATAL: Capital steering language
CAPITAL_STEERING_PATTERNS = [
    re.compile(r"\b(buy|sell|enter|exit|close|open)\s+(this|that|the|a|your)\s+\w+", re.I),
    re.compile(r"\b(allocate|invest|put)\s+\d+%?\s+(of|into|toward)", re.I),
    re.compile(r"\byou\s+should\s+(buy|sell|trade|enter|exit|close|open)\b", re.I),
    re.compile(r"\b(take\s+profit|cut\s+losses|stop\s+loss)\s+at\s+\d", re.I),
    re.compile(r"\b(place|execute)\s+(a|the|your)\s+(trade|order|position)\b", re.I),
]

# FATAL: Unapproved feature claims
UNAPPROVED_FEATURE_PATTERNS = [
    re.compile(r"\b(we\s+now|we\s+can|new\s+feature|coming\s+soon|beta\s+feature)\b", re.I),
    re.compile(r"\b(auto-?trad|auto-?execut|bot|algorithm\s+will)\b", re.I),
    re.compile(r"\b(guaranteed|ensure\s+profit|risk.?free)\b", re.I),
]

# FATAL: Roadmap leak
ROADMAP_LEAK_PATTERNS = [
    re.compile(r"\b(roadmap|planned\s+feature|upcoming|in\s+development|we'?re\s+building)\b", re.I),
    re.compile(r"\b(next\s+version|future\s+release|will\s+be\s+available)\b", re.I),
]

# CORRECTABLE: Optimization phrasing in strict domains
OPTIMIZATION_PATTERNS = [
    re.compile(r"\b(optimiz|maximiz|best\s+approach|ideal\s+strategy)\b", re.I),
    re.compile(r"\b(perfect\s+setup|optimal\s+entry|most\s+efficient)\b", re.I),
    re.compile(r"\b(improve\s+your|enhance\s+your|upgrade\s+your)\b", re.I),
]

# CORRECTABLE: Structural primitive invention
PRIMITIVE_INVENTION_PATTERNS = [
    re.compile(r"\b(new\s+metric|proprietary\s+indicator|custom\s+signal)\b", re.I),
    re.compile(r"\b(i'?ve\s+(created|developed|invented|designed)\s+a)\b", re.I),
]

# HYBRID: Structural separation markers
HYBRID_DIVIDER_PATTERNS = [
    re.compile(r"^---\s*$", re.MULTILINE),
    re.compile(r"^#{1,3}\s+(Reflection|Personal|Emotional|Observational)", re.MULTILINE | re.I),
    re.compile(r"\n\n(?=(?:On\s+a\s+personal|Reflecting|I\s+notice|Emotionally))", re.I),
]


class ResponseValidator:
    """
    Post-LLM response validator with tiered severity.

    Three-tier validation:
    - Fatal hard blocks → regenerate; if persist → controlled error
    - Correctable hard blocks → regenerate; if persist → violation note
    - Soft warnings → logged, never regenerated
    """

    def __init__(self, playbook_registry: Optional["PlaybookRegistry"] = None):
        self._registry = playbook_registry

    def validate(
        self,
        response_text: str,
        mode: str,
        domain: str,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> ValidationResult:
        """
        Validate a response against doctrine mode and constraints.

        Args:
            response_text: The LLM response to validate
            mode: "strict", "hybrid", or "reflective"
            domain: LPD domain classification
            constraints: DoctrineConstraints as dict

        Returns:
            ValidationResult with hard_violations, soft_warnings, and regenerate flag
        """
        result = ValidationResult(passed=True)

        if not response_text or not response_text.strip():
            return result  # Silence always passes

        # REFLECTIVE mode — relaxed rules, most checks skipped
        if mode == "reflective":
            # Only check fatal blocks even in reflective mode
            self._check_fatal(response_text, result)
            result.passed = len(result.hard_violations) == 0
            result.regenerate = len(result.hard_violations) > 0
            return result

        # STRICT and HYBRID modes — full validation

        # 1. Fatal hard blocks (always checked)
        self._check_fatal(response_text, result)

        # 2. Correctable hard blocks (strict/hybrid only)
        self._check_correctable(response_text, mode, domain, result)

        # 3. Hybrid structural validation
        if mode == "hybrid":
            self._validate_hybrid_structure(response_text, result)

        # 4. Soft warnings (logged only)
        self._check_soft(response_text, result)

        result.passed = len(result.hard_violations) == 0
        result.regenerate = len(result.hard_violations) > 0

        return result

    def _check_fatal(self, text: str, result: ValidationResult) -> None:
        """Check for fatal hard blocks that MUST NOT be surfaced."""
        # Capital steering
        for pattern in CAPITAL_STEERING_PATTERNS:
            match = pattern.search(text)
            if match:
                result.hard_violations.append(ValidationViolation(
                    rule="capital_steering",
                    description="Response contains capital steering language",
                    severity=ValidationSeverity.FATAL_HARD,
                    evidence=match.group()[:100],
                ))
                break  # One fatal is enough

        # Unapproved features
        for pattern in UNAPPROVED_FEATURE_PATTERNS:
            match = pattern.search(text)
            if match:
                result.hard_violations.append(ValidationViolation(
                    rule="unapproved_feature",
                    description="Response claims unapproved feature",
                    severity=ValidationSeverity.FATAL_HARD,
                    evidence=match.group()[:100],
                ))
                break

        # Roadmap leak
        for pattern in ROADMAP_LEAK_PATTERNS:
            match = pattern.search(text)
            if match:
                result.hard_violations.append(ValidationViolation(
                    rule="roadmap_leak",
                    description="Response leaks roadmap or unreleased features",
                    severity=ValidationSeverity.FATAL_HARD,
                    evidence=match.group()[:100],
                ))
                break

    def _check_correctable(
        self, text: str, mode: str, domain: str, result: ValidationResult
    ) -> None:
        """Check for correctable hard blocks."""
        # Optimization phrasing (strict mode domains)
        if mode == "strict":
            for pattern in OPTIMIZATION_PATTERNS:
                match = pattern.search(text)
                if match:
                    result.hard_violations.append(ValidationViolation(
                        rule="optimization_phrasing",
                        description="Optimization language in strict doctrine domain",
                        severity=ValidationSeverity.CORRECTABLE_HARD,
                        evidence=match.group()[:100],
                    ))
                    break

        # Primitive invention (all non-reflective modes)
        for pattern in PRIMITIVE_INVENTION_PATTERNS:
            match = pattern.search(text)
            if match:
                result.hard_violations.append(ValidationViolation(
                    rule="primitive_invention",
                    description="Response invents structural primitives not in doctrine",
                    severity=ValidationSeverity.CORRECTABLE_HARD,
                    evidence=match.group()[:100],
                ))
                break

    def _validate_hybrid_structure(self, text: str, result: ValidationResult) -> None:
        """
        Validate that hybrid responses structurally enforce:
        1. Doctrine explanation section appears FIRST
        2. Clear divider separates doctrine from reflective content
        3. Reflective framing appears SECOND (never interleaved)

        If not → correctable hard block → regenerate once with explicit structural instruction.
        """
        # Check for structural divider
        has_divider = any(p.search(text) for p in HYBRID_DIVIDER_PATTERNS)

        if not has_divider and len(text) > 200:
            # Long response without structural separation
            result.hard_violations.append(ValidationViolation(
                rule="hybrid_structural_separation",
                description=(
                    "Hybrid response lacks clear separation between "
                    "doctrine and reflective content"
                ),
                severity=ValidationSeverity.CORRECTABLE_HARD,
                evidence="No structural divider found in hybrid response",
            ))

    def _check_soft(self, text: str, result: ValidationResult) -> None:
        """Check for soft warnings (logged only, never regenerated)."""
        # Non-canonical terminology (if registry available)
        if self._registry:
            term_warnings = self._registry.validate_terms(text)
            for warning in term_warnings[:3]:  # Cap at 3
                result.soft_warnings.append(ValidationViolation(
                    rule="non_canonical_term",
                    description=warning,
                    severity=ValidationSeverity.SOFT_WARNING,
                ))

        # Metaphor in strict mode (soft, not hard)
        metaphor_patterns = [
            re.compile(r"\b(like\s+a|as\s+if|imagine\s+that|think\s+of\s+it\s+as)\b", re.I),
        ]
        for pattern in metaphor_patterns:
            if pattern.search(text):
                result.soft_warnings.append(ValidationViolation(
                    rule="metaphor_in_strict",
                    description="Metaphorical language detected in strict context",
                    severity=ValidationSeverity.SOFT_WARNING,
                ))
                break

    def get_regeneration_instruction(self, violations: List[ValidationViolation]) -> str:
        """Build regeneration instruction from violation list."""
        parts = [
            "IMPORTANT: Your previous response violated doctrine constraints. "
            "Regenerate with these corrections:\n"
        ]
        for v in violations:
            parts.append(f"- {v.rule}: {v.description}")
            if v.severity == ValidationSeverity.FATAL_HARD:
                parts.append("  (CRITICAL: This content MUST NOT appear in the response)")
            elif v.severity == ValidationSeverity.CORRECTABLE_HARD:
                parts.append("  (Required: Rephrase to avoid this pattern)")

        if any(v.rule == "hybrid_structural_separation" for v in violations):
            parts.append(
                "\nFor hybrid responses, structure as:\n"
                "1. Doctrine/structural explanation FIRST\n"
                "2. Clear divider (---)\n"
                "3. Reflective/personal content SECOND"
            )

        return "\n".join(parts)
