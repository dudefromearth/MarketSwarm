"""
lpd.py — Language Pattern Detector.

Deterministic + rule-assisted classifier for domain routing.
No black-box ML in v1. Fast (<5ms). Used by the orchestrate endpoint
to classify user queries into doctrine domains.

Constitutional constraint: LPD classification is advisory.
Kernel independently validates — if proxy headers are missing,
kernel re-runs LPD+DCL internally.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class DomainCategory(Enum):
    STRATEGY_MECHANICS = "strategy_mechanics"
    REGIME_STRUCTURE = "regime_structure"
    EDGE_LAB = "edge_lab"
    PRODUCT_ARCHITECTURE = "product_architecture"
    GOVERNANCE_SOVEREIGNTY = "governance_sovereignty"
    PROCESS_DISCIPLINE = "process_discipline"
    EMOTIONAL_REFLECTIVE = "emotional_reflective"
    HYBRID = "hybrid"


# Domain → playbook mapping
DOMAIN_TO_PLAYBOOK = {
    DomainCategory.STRATEGY_MECHANICS: "strategy_logic",
    DomainCategory.REGIME_STRUCTURE: "regime_gex",
    DomainCategory.EDGE_LAB: "edge_lab",
    DomainCategory.PRODUCT_ARCHITECTURE: "admin_orchestration",
    DomainCategory.GOVERNANCE_SOVEREIGNTY: "governance_sovereignty",
    DomainCategory.PROCESS_DISCIPLINE: "end_to_end_process",
    DomainCategory.EMOTIONAL_REFLECTIVE: "",
    DomainCategory.HYBRID: "",
}


@dataclass
class LPDClassification:
    """Result of LPD classification."""
    domain: DomainCategory
    confidence: float
    secondary_domain: Optional[DomainCategory] = None
    matched_patterns: List[str] = field(default_factory=list)
    playbook_domain: str = ""

    def __post_init__(self):
        if not self.playbook_domain:
            self.playbook_domain = DOMAIN_TO_PLAYBOOK.get(self.domain, "")


# =============================================================================
# PATTERN DEFINITIONS
# =============================================================================

# Each domain has a list of (pattern, weight) tuples.
# Pattern matches are additive — domain with highest total weight wins.

DOMAIN_PATTERNS: Dict[DomainCategory, List[tuple]] = {
    DomainCategory.STRATEGY_MECHANICS: [
        (re.compile(r"\b(butterfly|iron\s*condor|vertical|spread|straddle|strangle)\b", re.I), 3.0),
        (re.compile(r"\b(strike|width|expir|DTE|premium|debit|credit)\b", re.I), 2.0),
        (re.compile(r"\b(convexity|asymmetr|risk.?reward|payoff)\b", re.I), 2.0),
        (re.compile(r"\b(position\s*siz|risk\s*budget|allocation)\b", re.I), 2.0),
        (re.compile(r"\b(trade\s*structure|structural\s*(win|loss|edge))\b", re.I), 3.0),
        (re.compile(r"\b(entry|exit)\s*(criteria|rule|logic)\b", re.I), 1.5),
        (re.compile(r"\bhow\s+(does|do)\s+(a|the)\s+(butterfly|spread|fly)\b", re.I), 3.0),
        (re.compile(r"\bdefine\s+(structural|convexity|edge|width)\b", re.I), 2.5),
        (re.compile(r"\bwhat\s+(is|are)\s+(a\s+)?(structural|convex|iron)\b", re.I), 2.5),
    ],
    DomainCategory.REGIME_STRUCTURE: [
        (re.compile(r"\b(regime|GEX|gamma\s*exposure|dealer\s*gravity)\b", re.I), 3.0),
        (re.compile(r"\b(VIX|volatility\s*regime|compression|expansion)\b", re.I), 2.0),
        (re.compile(r"\b(zero\s*gamma|flip\s*level|gamma\s*wall)\b", re.I), 3.0),
        (re.compile(r"\b(market\s*mode|vol\s*(floor|ceiling|cluster))\b", re.I), 2.0),
        (re.compile(r"\b(dealer\s*hedg|mechanical\s*force|pin)\b", re.I), 2.5),
        (re.compile(r"\bwhat\s+(is|does)\s+(the\s+)?(regime|GEX|dealer)\b", re.I), 2.5),
        (re.compile(r"\bhow\s+(does|do)\s+(regime|GEX|dealer|gamma)\b", re.I), 2.5),
    ],
    DomainCategory.EDGE_LAB: [
        (re.compile(r"\bedge\s*lab\b", re.I), 5.0),
        (re.compile(r"\b(edge\s*score|signature|pattern\s*fidelity)\b", re.I), 3.0),
        (re.compile(r"\b(retrospective|retro|post.?trade\s*analysis)\b", re.I), 2.5),
        (re.compile(r"\b(setup\s*analys|trade\s*pattern|behavioral\s*drift)\b", re.I), 2.0),
        (re.compile(r"\b(sample\s*size|historical\s*resolution)\b", re.I), 1.5),
    ],
    DomainCategory.PRODUCT_ARCHITECTURE: [
        (re.compile(r"\b(echo\s*memory|hydrat|prompt\s*assembl|kernel)\b", re.I), 3.0),
        (re.compile(r"\b(capability|SSE|redis\s*bus|truth\s*system)\b", re.I), 2.5),
        (re.compile(r"\b(playbook\s*registry|doctrine\s*mode|AOL)\b", re.I), 3.0),
        (re.compile(r"\bhow\s+(does|do)\s+(vexy|the\s*system|echo)\s+(work|process)\b", re.I), 2.0),
        (re.compile(r"\b(architecture|infrastructure|service|endpoint)\b", re.I), 1.5),
    ],
    DomainCategory.GOVERNANCE_SOVEREIGNTY: [
        (re.compile(r"\b(sovereignty|autonomy|Path\s*doctrine)\b", re.I), 3.0),
        (re.compile(r"\b(ORA|Object.?Reflection.?Action)\b", re.I), 3.0),
        (re.compile(r"\b(forbidden\s*language|imperative|prescriptive)\b", re.I), 2.5),
        (re.compile(r"\b(tier\s*scope|semantic\s*scope|validation)\b", re.I), 2.0),
        (re.compile(r"\b(non.?capabilit|constraint|invariant)\b", re.I), 2.0),
    ],
    DomainCategory.PROCESS_DISCIPLINE: [
        (re.compile(r"\b(routine|process|journal|daily\s*practice)\b", re.I), 2.0),
        (re.compile(r"\b(intent\s*declaration|readiness|state\s*reset)\b", re.I), 2.5),
        (re.compile(r"\b(pre.?market|post.?close|morning\s*digest)\b", re.I), 1.5),
        (re.compile(r"\b(loop|practice|discipline|habit)\b", re.I), 1.0),
    ],
    DomainCategory.EMOTIONAL_REFLECTIVE: [
        (re.compile(r"\b(i\s+feel|i'm\s+(frustrat|confus|overwhelm|anxi|afraid|stuck))\b", re.I), 4.0),
        (re.compile(r"\b(feeling|emotion|stressed|burnout|tilt|revenge)\b", re.I), 3.0),
        (re.compile(r"\b(why\s+do\s+i\s+keep|can't\s+stop|spiral|despair)\b", re.I), 4.0),
        (re.compile(r"\b(loss\s+streak|bad\s+day|losing|scared)\b", re.I), 2.5),
        (re.compile(r"\b(help\s+me\s+(understand|cope|deal))\b", re.I), 2.0),
        (re.compile(r"\b(i\s+need\s+(help|support|guidance))\b", re.I), 2.0),
    ],
}


class LanguagePatternDetector:
    """
    Deterministic + rule-assisted classifier. No black-box ML in v1.

    Scores each domain by summing pattern match weights. Domain with
    highest score wins. If top two scores are close, returns HYBRID.
    """

    CONFIDENCE_THRESHOLD = 0.6
    HYBRID_MARGIN = 0.3  # If top two scores are within this ratio, it's hybrid

    def __init__(
        self,
        logger: Any = None,
        confidence_threshold: Optional[float] = None,
        hybrid_margin: Optional[float] = None,
    ):
        self._logger = logger or logging.getLogger(__name__)
        if confidence_threshold is not None:
            self.CONFIDENCE_THRESHOLD = confidence_threshold
        if hybrid_margin is not None:
            self.HYBRID_MARGIN = hybrid_margin

    def classify(self, query: str) -> LPDClassification:
        """
        Classify a user query into a domain category.

        Returns LPDClassification with domain, confidence, and matched patterns.
        """
        if not query or not query.strip():
            return LPDClassification(
                domain=DomainCategory.PROCESS_DISCIPLINE,
                confidence=0.0,
                matched_patterns=[],
            )

        # Score each domain
        scores: Dict[DomainCategory, float] = {}
        all_matches: Dict[DomainCategory, List[str]] = {}

        for domain, patterns in DOMAIN_PATTERNS.items():
            domain_score = 0.0
            matches = []
            for pattern, weight in patterns:
                found = pattern.findall(query)
                if found:
                    domain_score += weight
                    matches.append(pattern.pattern[:50])
            if domain_score > 0:
                scores[domain] = domain_score
                all_matches[domain] = matches

        if not scores:
            # No patterns matched — default to process discipline (safe)
            return LPDClassification(
                domain=DomainCategory.PROCESS_DISCIPLINE,
                confidence=0.3,
                matched_patterns=[],
            )

        # Sort by score descending
        sorted_domains = sorted(scores.items(), key=lambda x: -x[1])
        top_domain, top_score = sorted_domains[0]

        # Calculate confidence as normalized score
        total_score = sum(scores.values())
        confidence = top_score / total_score if total_score > 0 else 0.0

        # Check for hybrid — if top two are close
        secondary = None
        if len(sorted_domains) >= 2:
            second_domain, second_score = sorted_domains[1]
            ratio = second_score / top_score if top_score > 0 else 0
            if ratio > (1.0 - self.HYBRID_MARGIN):
                # Close scores — hybrid mode
                secondary = second_domain
                if top_domain == DomainCategory.EMOTIONAL_REFLECTIVE:
                    # Emotional + doctrine → hybrid with doctrine secondary
                    return LPDClassification(
                        domain=DomainCategory.HYBRID,
                        confidence=confidence,
                        secondary_domain=second_domain,
                        matched_patterns=all_matches.get(top_domain, []),
                        playbook_domain=DOMAIN_TO_PLAYBOOK.get(second_domain, ""),
                    )
                elif second_domain == DomainCategory.EMOTIONAL_REFLECTIVE:
                    # Doctrine + emotional → hybrid with doctrine primary
                    return LPDClassification(
                        domain=DomainCategory.HYBRID,
                        confidence=confidence,
                        secondary_domain=second_domain,
                        matched_patterns=all_matches.get(top_domain, []),
                        playbook_domain=DOMAIN_TO_PLAYBOOK.get(top_domain, ""),
                    )

        # Low confidence → return with flag
        if confidence < self.CONFIDENCE_THRESHOLD:
            # Low confidence — still return best guess but flag it
            pass

        return LPDClassification(
            domain=top_domain,
            confidence=confidence,
            secondary_domain=secondary,
            matched_patterns=all_matches.get(top_domain, []),
        )


# =============================================================================
# LPD METRICS (Drift Observability)
# =============================================================================

class LPDMetrics:
    """Track classification quality over time for admin dashboard."""

    def __init__(self):
        self._classifications: List[Dict] = []
        self._max_history = 1000

    def log_classification(self, user_id: int, classification: LPDClassification) -> None:
        """Log a classification event."""
        entry = {
            "ts": time.time(),
            "user_id": user_id,
            "domain": classification.domain.value,
            "confidence": classification.confidence,
            "secondary": classification.secondary_domain.value if classification.secondary_domain else None,
            "low_confidence": classification.confidence < LanguagePatternDetector.CONFIDENCE_THRESHOLD,
            "is_hybrid": classification.domain == DomainCategory.HYBRID,
        }
        self._classifications.append(entry)

        # Trim history
        if len(self._classifications) > self._max_history:
            self._classifications = self._classifications[-self._max_history:]

    def get_drift_summary(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """Return summary for admin dashboard."""
        entries = self._classifications
        if user_id is not None:
            entries = [e for e in entries if e["user_id"] == user_id]

        if not entries:
            return {"total": 0}

        domain_counts: Dict[str, int] = {}
        low_confidence_count = 0
        hybrid_count = 0

        for e in entries:
            domain_counts[e["domain"]] = domain_counts.get(e["domain"], 0) + 1
            if e["low_confidence"]:
                low_confidence_count += 1
            if e["is_hybrid"]:
                hybrid_count += 1

        total = len(entries)
        return {
            "total": total,
            "by_domain": domain_counts,
            "low_confidence_rate": low_confidence_count / total if total else 0,
            "hybrid_rate": hybrid_count / total if total else 0,
        }

    def get_recent(self, limit: int = 50) -> List[Dict]:
        """Get recent classification log entries."""
        return list(reversed(self._classifications[-limit:]))
