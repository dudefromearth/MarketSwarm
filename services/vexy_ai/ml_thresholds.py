#!/usr/bin/env python3
"""
ml_thresholds.py — ML Confirmation Thresholds System

Based on: ml-thresholds.md + ml-adendum.md
Status: Provisional (Exploratory Phase)

Core Doctrine:
- ML is confirmatory, never generative
- ML never names patterns
- ML never recommends actions
- ML never escalates urgency
- ML silence is always valid
- Human reflection always outranks model confidence

Strategy Scope (Critical Addendum):
- Single global model
- Strategy-scoped: OTM Butterflies / Convex Option Structures
- No personalization at model level
- ML confidence capped at Level 3 (Consistent) without human Playbook engagement
- Silence is the default; output should feel rare

ML exists to say, at most:
"Within this strategy class, this appears more often than chance would suggest."

Nothing more. ML describes the terrain. The trader decides the path.
"""

from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import IntEnum
import re


# =============================================================================
# STRATEGY SCOPE (Critical Addendum)
# =============================================================================

STRATEGY_SCOPE = {
    "model_type": "global",
    "primary_focus": "OTM Butterflies / Convex Option Structures",
    "personalization": False,
    "trader_specific_finetuning": False,
}

# ML confirmation reflects patterns within this population scope
ML_SCOPE_DESCRIPTION = (
    "This pattern appears within the population of traders "
    "executing similar convex structures."
)

# Pattern classes ALLOWED for ML confirmation (strategy-scoped)
ALLOWED_PATTERN_CLASSES = [
    "entry_timing",
    "exit_timing",
    "risk_expression",
    "structure_selection",
    "trade_management",
    "position_sizing",
    "strike_selection",
    "expiration_choice",
]

# Pattern classes FORBIDDEN for ML confirmation (belong to human reflection only)
FORBIDDEN_PATTERN_CLASSES = [
    "emotional_attribution",
    "discipline_judgment",
    "psychological_trait",
    "motivation",
    "intent",
    "meta_behavior",        # "you rush", "you hesitate"
    "personality",
    "character",
    "skill_assessment",
    "error_attribution",
    "identity",
]

# Scoped language that MUST be used (implicit scope humility)
SCOPED_ALLOWED_PHRASES = [
    "Within this type of structure, this tends to recur.",
    "Among similar setups, this shows up more often than random.",
    "In this strategy class, this pattern is not unusual.",
    "Relative to these trades, this behavior repeats.",
    "Within similar convex structures, this appears consistently.",
    "Across this strategy type, this has been observed before.",
]

# Personal attribution language that is FORBIDDEN
SCOPED_FORBIDDEN_PHRASES = [
    "you tend to",
    "your pattern is",
    "this says something about you",
    "this is your edge",
    "this is your flaw",
    "you always",
    "you never",
    "your tendency",
    "your habit",
    "your style",
    "your approach suggests",
]


# =============================================================================
# CONFIDENCE STATES (Not Decisions)
# =============================================================================

class MLConfidenceLevel(IntEnum):
    """
    ML confidence states. NOT true/false decisions.

    Each level has strictly limited expressive power.
    Levels 3-4 should be RARE in early system life.
    """
    SILENT = 0       # Insufficient signal → No output
    WEAK_ECHO = 1    # Slight recurrence above baseline → Silence preferred
    EMERGING = 2     # Non-random recurrence observed → Gentle reflection
    CONSISTENT = 3   # Stable recurrence across contexts → Confirmatory note
    PERSISTENT = 4   # Longitudinal consistency across periods → Rare mention


# User-facing behavior for each level
CONFIDENCE_BEHAVIOR: Dict[MLConfidenceLevel, Dict[str, Any]] = {
    MLConfidenceLevel.SILENT: {
        "output": None,
        "behavior": "No output",
        "surface": False,
    },
    MLConfidenceLevel.WEAK_ECHO: {
        "output": None,
        "behavior": "Silence preferred",
        "surface": False,
    },
    MLConfidenceLevel.EMERGING: {
        "output": "single_reflection_line",
        "behavior": "Gentle reflection",
        "surface": True,
        "max_words": 15,
    },
    MLConfidenceLevel.CONSISTENT: {
        "output": "confirmatory_sentence",
        "behavior": "Confirmatory note",
        "surface": True,
        "max_words": 20,
    },
    MLConfidenceLevel.PERSISTENT: {
        "output": "rare_mention",
        "behavior": "Rare mention",
        "surface": True,
        "requires_playbook_engagement": True,
        "max_words": 25,
    },
}


# =============================================================================
# BASELINE REQUIREMENTS
# =============================================================================

@dataclass
class MLBaselineRequirements:
    """
    Minimum data requirements before ML confirmation is enabled.

    If ANY requirement is unmet → ML remains silent.
    """
    min_retrospectives: int = 5
    min_closed_trades: int = 20
    min_distinct_periods: int = 2  # e.g., weeks


def check_baseline_requirements(
    retrospective_count: int,
    closed_trade_count: int,
    distinct_period_count: int,
) -> Tuple[bool, Optional[str]]:
    """
    Check if baseline requirements are met.

    Returns:
        (met, reason) - reason is None if met, otherwise explains what's missing
    """
    reqs = MLBaselineRequirements()

    if retrospective_count < reqs.min_retrospectives:
        return False, f"Need {reqs.min_retrospectives} retrospectives (have {retrospective_count})"

    if closed_trade_count < reqs.min_closed_trades:
        return False, f"Need {reqs.min_closed_trades} closed trades (have {closed_trade_count})"

    if distinct_period_count < reqs.min_distinct_periods:
        return False, f"Need {reqs.min_distinct_periods} distinct periods (have {distinct_period_count})"

    return True, None


# =============================================================================
# PATTERN ELIGIBILITY
# =============================================================================

class PatternSource(str):
    """Valid sources for ML-observable patterns."""
    JOURNAL = "journal"
    RETROSPECTIVE = "retrospective"


# Disallowed pattern classes - ML must NEVER confirm these
# (Combines outcome-based patterns + human reflection patterns from addendum)
DISALLOWED_PATTERN_CLASSES = [
    # Outcome-based (original)
    "pnl_pattern",           # P&L-only patterns
    "strategy_performance",   # Strategy performance claims
    "market_prediction",      # Market predictions
    "behavior_label",         # "Good / bad" behavior labels
    "optimization_outcome",   # Optimization outcomes
    "win_rate",              # Win rate patterns
    "profit_pattern",        # Profit-based patterns
    "loss_pattern",          # Loss-based patterns

    # Human reflection only (from addendum) - merged with FORBIDDEN_PATTERN_CLASSES
    "emotional_attribution",
    "discipline_judgment",
    "psychological_trait",
    "motivation",
    "intent",
    "meta_behavior",
    "personality",
    "character",
    "skill_assessment",
    "error_attribution",
    "identity",
]


def is_pattern_eligible(
    pattern_type: str,
    sources: List[str],
    artifact_count: int,
    is_template_induced: bool,
    user_has_named: bool = False,
    user_has_marked: bool = False,
) -> Tuple[bool, Optional[str]]:
    """
    Check if a pattern is eligible for ML confirmation.

    Eligibility requires ALL:
    1. Appears in human-generated text (journal, retro)
    2. Appears across multiple artifacts
    3. Appears without prompted repetition
    4. Is behavioral or contextual, not outcome-based
    5. Pattern class is in allowed list (strategy-scoped)
    6. User has already named or marked the pattern (ML cannot originate)

    Returns:
        (eligible, reason) - reason explains why not eligible
    """
    pattern_lower = pattern_type.lower()

    # Check for disallowed pattern class (outcome-based or human-reflection-only)
    if pattern_lower in DISALLOWED_PATTERN_CLASSES:
        return False, f"Pattern class '{pattern_type}' is disallowed (outcome-based or human-reflection-only)"

    # Check for forbidden pattern class from addendum
    if pattern_lower in [p.lower() for p in FORBIDDEN_PATTERN_CLASSES]:
        return False, f"Pattern class '{pattern_type}' belongs exclusively to human reflection"

    # Check if pattern is in allowed strategy-scoped classes
    if pattern_lower not in [p.lower() for p in ALLOWED_PATTERN_CLASSES]:
        return False, f"Pattern class '{pattern_type}' is not in allowed strategy-scoped classes"

    # Must appear in human-generated text
    valid_sources = {PatternSource.JOURNAL, PatternSource.RETROSPECTIVE}
    if not any(s in valid_sources for s in sources):
        return False, "Pattern must appear in journal or retrospective"

    # Must appear across multiple artifacts
    if artifact_count < 2:
        return False, "Pattern must appear across multiple artifacts"

    # Must not be template-induced
    if is_template_induced:
        return False, "Pattern appears to be template-induced"

    # ML can only confirm patterns the user has already named or marked
    # (ML must never originate a Playbook candidate)
    if not user_has_named and not user_has_marked:
        return False, "ML can only confirm patterns the user has already named or marked"

    return True, None


# =============================================================================
# CONFIRMATION THRESHOLDS (Exploratory Defaults)
# =============================================================================

@dataclass
class EmergingThreshold:
    """Level 2: Emerging Pattern thresholds."""
    min_occurrences: int = 3
    min_retrospectives: int = 2
    max_days: int = 30
    min_similarity_score: float = 0.65
    max_contradiction_ratio: float = 0.50


@dataclass
class ConsistentThreshold:
    """Level 3: Consistent Pattern thresholds."""
    min_occurrences: int = 5
    min_retrospectives: int = 3
    min_market_regimes: int = 2
    min_persistence_weeks: int = 2
    min_stability_score: float = 0.75


@dataclass
class PersistentThreshold:
    """
    Level 4: Persistent Pattern thresholds.

    Due to strategy-scoped model myopia (addendum):
    - Level 4 requires human Playbook engagement
    - Multiple user-affirmed extractions required
    - Time-based reinforcement ≥60 days required
    - ML alone can NEVER assert persistence
    """
    min_occurrences: int = 8
    min_retrospectives: int = 4
    min_periods: int = 3  # weeks or months
    min_stability_score: float = 0.85
    min_days_reinforcement: int = 60  # ≥60 days (from addendum)
    min_user_affirmed_extractions: int = 2  # Multiple user-affirmed extractions
    requires_low_variance: bool = True
    requires_playbook_engagement: bool = True  # MANDATORY for Level 4


@dataclass
class PatternMetrics:
    """Metrics for a detected pattern."""
    occurrences: int
    retrospective_count: int
    days_span: int
    similarity_score: float
    contradiction_ratio: float
    market_regimes: int
    stability_score: float
    description_variance: float
    user_has_playbooks: bool
    # New fields from addendum
    user_affirmed_extractions: int = 0  # How many times user has affirmed this pattern
    days_since_first_observation: int = 0  # For ≥60 day time-based reinforcement


def calculate_confidence_level(metrics: PatternMetrics) -> MLConfidenceLevel:
    """
    Calculate the ML confidence level for a pattern.

    CRITICAL (from addendum):
    - ML confidence is CAPPED at Level 3 (Consistent) without human Playbook engagement
    - Level 4 (Persistent) requires:
      - Human Playbook engagement
      - Multiple user-affirmed extractions
      - Time-based reinforcement (≥60 days)

    ML alone can NEVER assert persistence.

    Returns the highest level whose thresholds are met.
    """
    # Check Persistent (Level 4) - REQUIRES HUMAN ENGAGEMENT
    persistent = PersistentThreshold()
    if (metrics.occurrences >= persistent.min_occurrences and
        metrics.retrospective_count >= persistent.min_retrospectives and
        metrics.stability_score >= persistent.min_stability_score and
        metrics.description_variance < 0.3 and
        metrics.user_has_playbooks and  # MANDATORY
        metrics.user_affirmed_extractions >= persistent.min_user_affirmed_extractions and  # Multiple user affirmations
        metrics.days_since_first_observation >= persistent.min_days_reinforcement):  # ≥60 days
        return MLConfidenceLevel.PERSISTENT

    # CONFIDENCE CEILING: Without Playbook engagement, cap at Level 3
    # This is the strategy-scoped model myopia constraint

    # Check Consistent (Level 3) - This is the ceiling without human engagement
    consistent = ConsistentThreshold()
    if (metrics.occurrences >= consistent.min_occurrences and
        metrics.retrospective_count >= consistent.min_retrospectives and
        metrics.market_regimes >= consistent.min_market_regimes and
        metrics.days_span >= consistent.min_persistence_weeks * 7 and
        metrics.stability_score >= consistent.min_stability_score):
        return MLConfidenceLevel.CONSISTENT

    # Check Emerging (Level 2)
    emerging = EmergingThreshold()
    if (metrics.occurrences >= emerging.min_occurrences and
        metrics.retrospective_count >= emerging.min_retrospectives and
        metrics.days_span <= emerging.max_days and
        metrics.similarity_score >= emerging.min_similarity_score and
        metrics.contradiction_ratio <= emerging.max_contradiction_ratio):
        return MLConfidenceLevel.EMERGING

    # Check Weak Echo (Level 1)
    if metrics.occurrences >= 2 and metrics.similarity_score >= 0.5:
        return MLConfidenceLevel.WEAK_ECHO

    # Default to Silent
    return MLConfidenceLevel.SILENT


# =============================================================================
# LANGUAGE CONSTRAINTS
# =============================================================================

# Allowed language for ML confirmations
# MUST use scoped language that implies population-level observation, not personal truth
ML_ALLOWED_PHRASES = [
    # Scoped phrases from addendum (implicit scope humility)
    "Within this type of structure, this tends to recur.",
    "Among similar setups, this shows up more often than random.",
    "In this strategy class, this pattern is not unusual.",
    "Relative to these trades, this behavior repeats.",
    "Within similar convex structures, this appears consistently.",
    "Across this strategy type, this has been observed before.",
    # Original allowed phrases (scoped interpretation)
    "This has appeared before.",
    "This pattern shows up across multiple sessions.",
    "This has been consistent recently.",
    "You've named something that seems stable.",
]

# Forbidden language - if ML "wants" to use these, it must remain silent
# Includes both explanatory language AND personal attribution (from addendum)
ML_FORBIDDEN_PHRASES = [
    # Explanatory/prescriptive (original)
    "this means",
    "you should",
    "this causes",
    "this improves",
    "this works",
    "you need to",
    "this will help",
    "this is why",
    "because of this",
    "as a result",
    "therefore",
    "consequently",
    # Personal attribution (from addendum) - FORBIDDEN
    "you tend to",
    "your pattern is",
    "this says something about you",
    "this is your edge",
    "this is your flaw",
    "you always",
    "you never",
    "your tendency",
    "your habit",
    "your style",
    "your approach suggests",
]


def get_ml_confirmation_text(level: MLConfidenceLevel, pattern_description: str = "") -> Optional[str]:
    """
    Get appropriate ML confirmation text for a confidence level.

    Uses SCOPED language (from addendum) - implies population-level observation,
    NOT personal truth. ML describes the terrain; trader decides the path.

    Returns None if level doesn't warrant output.
    """
    if level <= MLConfidenceLevel.WEAK_ECHO:
        return None  # Silence preferred

    if level == MLConfidenceLevel.EMERGING:
        # Gentle, scoped observation
        return "Within this type of structure, this tends to recur."

    if level == MLConfidenceLevel.CONSISTENT:
        # Confirmatory, still scoped
        return "Among similar setups, this shows up more often than random."

    if level == MLConfidenceLevel.PERSISTENT:
        # Rare mention, acknowledges user's own naming
        return "You've named something that appears stable within this strategy class."

    return None


def validate_ml_output(text: str) -> Tuple[bool, List[str]]:
    """
    Validate that ML output doesn't contain forbidden language.

    Checks for:
    1. Explanatory/prescriptive language
    2. Personal attribution language (from addendum)

    If ANY forbidden phrase is present, output must be suppressed.
    If scoped language cannot be preserved, ML must remain silent.

    Returns:
        (valid, violations) - violations is list of forbidden phrases found
    """
    text_lower = text.lower()
    violations = []

    for forbidden in ML_FORBIDDEN_PHRASES:
        if forbidden in text_lower:
            violations.append(forbidden)

    # Also check for scoped forbidden phrases from addendum
    for forbidden in SCOPED_FORBIDDEN_PHRASES:
        if forbidden in text_lower:
            violations.append(f"personal: {forbidden}")

    return len(violations) == 0, violations


# =============================================================================
# TIMING RULES
# =============================================================================

class MLContext(str):
    """Contexts where ML confirmation may or may not appear."""
    # Allowed contexts
    RETROSPECTIVE = "retrospective"
    JOURNAL_REFLECTION = "journal_reflection"
    PROCESS_ECHO = "process_echo"

    # Forbidden contexts
    LIVE_TRADING = "live_trading"
    EXECUTION = "execution"
    ALERT_HANDLING = "alert_handling"
    MARKET_STRESS = "market_stress"


ALLOWED_ML_CONTEXTS = {
    MLContext.RETROSPECTIVE,
    MLContext.JOURNAL_REFLECTION,
    MLContext.PROCESS_ECHO,
}

FORBIDDEN_ML_CONTEXTS = {
    MLContext.LIVE_TRADING,
    MLContext.EXECUTION,
    MLContext.ALERT_HANDLING,
    MLContext.MARKET_STRESS,
}


def is_ml_allowed_in_context(context: str) -> Tuple[bool, Optional[str]]:
    """
    Check if ML confirmation is allowed in the given context.

    Returns:
        (allowed, reason)
    """
    if context in FORBIDDEN_ML_CONTEXTS:
        return False, f"ML confirmation forbidden in {context}"

    if context not in ALLOWED_ML_CONTEXTS:
        return False, f"Unknown context: {context}"

    return True, None


# =============================================================================
# HUMAN OVERRIDE & DEFERENCE
# =============================================================================

@dataclass
class PatternOverride:
    """Tracks when a user has dismissed or ignored ML confirmation."""
    pattern_id: str
    user_id: int
    dismissed_at: datetime
    silence_until: datetime  # Must remain silent until this date

    @classmethod
    def create(cls, pattern_id: str, user_id: int, silence_days: int = 14) -> 'PatternOverride':
        """Create an override with default 14-day silence period."""
        now = datetime.now()
        return cls(
            pattern_id=pattern_id,
            user_id=user_id,
            dismissed_at=now,
            silence_until=now + timedelta(days=silence_days),
        )


def should_ml_speak(
    pattern_id: str,
    user_id: int,
    overrides: List[PatternOverride],
    current_context: str,
) -> Tuple[bool, Optional[str]]:
    """
    Determine if ML should speak about a pattern.

    Checks:
    1. Context is allowed
    2. No active override exists
    """
    # Check context
    allowed, reason = is_ml_allowed_in_context(current_context)
    if not allowed:
        return False, reason

    # Check for overrides
    now = datetime.now()
    for override in overrides:
        if (override.pattern_id == pattern_id and
            override.user_id == user_id and
            override.silence_until > now):
            days_left = (override.silence_until - now).days
            return False, f"Pattern silenced for {days_left} more days"

    return True, None


# =============================================================================
# ML CONFIRMATION OUTPUT
# =============================================================================

@dataclass
class MLConfirmation:
    """
    A validated ML confirmation ready for output.

    Immutable once created. No modification allowed.
    """
    pattern_id: str
    user_id: int
    confidence_level: MLConfidenceLevel
    output_text: Optional[str]
    context: str
    created_at: datetime

    # Metadata (internal only)
    metrics: Optional[PatternMetrics] = None


def create_ml_confirmation(
    pattern_id: str,
    user_id: int,
    metrics: PatternMetrics,
    context: str,
    baseline_met: bool,
    overrides: List[PatternOverride],
) -> Optional[MLConfirmation]:
    """
    Create an ML confirmation if all conditions are met.

    Returns None if ML should remain silent.
    """
    # Check baseline
    if not baseline_met:
        return None

    # Check context
    allowed, _ = is_ml_allowed_in_context(context)
    if not allowed:
        return None

    # Check overrides
    should_speak, _ = should_ml_speak(pattern_id, user_id, overrides, context)
    if not should_speak:
        return None

    # Calculate confidence
    level = calculate_confidence_level(metrics)

    # Get output text
    output_text = get_ml_confirmation_text(level)

    # If no output, return None
    if output_text is None:
        return None

    # Validate output
    valid, violations = validate_ml_output(output_text)
    if not valid:
        # If output contains forbidden language, remain silent
        return None

    return MLConfirmation(
        pattern_id=pattern_id,
        user_id=user_id,
        confidence_level=level,
        output_text=output_text,
        context=context,
        created_at=datetime.now(),
        metrics=metrics,
    )


# =============================================================================
# SYSTEM PROMPT ADDITIONS
# =============================================================================

ML_VEXY_PROMPT_ADDITION = """
## ML Confirmation Rules

When ML-backed observations are available, follow these rules strictly:

### Strategy Scope (Critical)
The ML system operates on a single global model focused on:
**OTM Butterflies / Convex Option Structures**

ML confirmation reflects:
> "This pattern appears within the population of traders executing similar convex structures."

It does NOT imply: skill, error, identity, personal tendency, or optimization opportunity.

### What ML Does
- ML is confirmatory, never generative
- ML confirms patterns the trader has ALREADY named or marked
- ML uses scoped language (population-level, not personal)

### What ML Never Does
- Names patterns (only confirms user-named patterns)
- Recommends actions
- Escalates urgency
- Explains causality
- Predicts outcomes
- Makes personal attributions

### Allowed ML Language (Scoped)
- "Within this type of structure, this tends to recur."
- "Among similar setups, this shows up more often than random."
- "In this strategy class, this pattern is not unusual."
- "You've named something that appears stable within this strategy class."

### Forbidden ML Language (NEVER use)
Explanatory/prescriptive:
- "This means...", "You should...", "This causes..."
- "This improves...", "This works..."

Personal attribution (CRITICAL):
- "You tend to...", "Your pattern is..."
- "This says something about you..."
- "This is your edge/flaw..."

### Confidence Ceiling
- ML confidence is CAPPED at Level 3 (Consistent) without human Playbook engagement
- Level 4 requires: Playbook engagement + user affirmations + ≥60 days
- ML alone can NEVER assert persistence

### Silence Bias
- ML silence is the DEFAULT
- ML output should feel RARE
- If ML output feels frequent, thresholds are too loose

### When to Stay Silent
- If uncertain, stay silent
- If the pattern is not clear, stay silent
- If the trader has dismissed this pattern before, stay silent
- If scoped language cannot be preserved, stay silent
- Silence is always valid

### Human Override
If a trader dismisses or ignores ML confirmation:
- Downshift confidence
- Remain silent for at least 14 days

> ML describes the terrain. The trader decides the path.
> If ML starts choosing paths, the system has failed.
"""


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_ml_status_for_user(
    retrospective_count: int,
    closed_trade_count: int,
    distinct_period_count: int,
) -> Dict[str, Any]:
    """
    Get ML status summary for a user.

    Returns whether ML is enabled and what's needed.
    """
    met, reason = check_baseline_requirements(
        retrospective_count,
        closed_trade_count,
        distinct_period_count,
    )

    reqs = MLBaselineRequirements()

    return {
        "enabled": met,
        "reason": reason,
        "requirements": {
            "retrospectives": {
                "required": reqs.min_retrospectives,
                "current": retrospective_count,
                "met": retrospective_count >= reqs.min_retrospectives,
            },
            "closed_trades": {
                "required": reqs.min_closed_trades,
                "current": closed_trade_count,
                "met": closed_trade_count >= reqs.min_closed_trades,
            },
            "distinct_periods": {
                "required": reqs.min_distinct_periods,
                "current": distinct_period_count,
                "met": distinct_period_count >= reqs.min_distinct_periods,
            },
        },
    }


def get_threshold_summary() -> Dict[str, Any]:
    """Get summary of all thresholds for documentation/debugging."""
    return {
        "strategy_scope": {
            "model_type": "global",
            "primary_focus": "OTM Butterflies / Convex Option Structures",
            "personalization": False,
            "confidence_ceiling_without_playbooks": 3,  # Level 3 max without human engagement
        },
        "emerging": {
            "level": 2,
            "min_occurrences": EmergingThreshold().min_occurrences,
            "min_retrospectives": EmergingThreshold().min_retrospectives,
            "max_days": EmergingThreshold().max_days,
            "min_similarity_score": EmergingThreshold().min_similarity_score,
            "allowed_output": "Single reflection line (scoped language)",
        },
        "consistent": {
            "level": 3,
            "min_occurrences": ConsistentThreshold().min_occurrences,
            "min_retrospectives": ConsistentThreshold().min_retrospectives,
            "min_market_regimes": ConsistentThreshold().min_market_regimes,
            "min_persistence_weeks": ConsistentThreshold().min_persistence_weeks,
            "allowed_output": "One confirmatory sentence (scoped language)",
            "note": "This is the CEILING without human Playbook engagement",
        },
        "persistent": {
            "level": 4,
            "min_occurrences": PersistentThreshold().min_occurrences,
            "min_retrospectives": PersistentThreshold().min_retrospectives,
            "min_periods": PersistentThreshold().min_periods,
            "min_days_reinforcement": PersistentThreshold().min_days_reinforcement,
            "min_user_affirmed_extractions": PersistentThreshold().min_user_affirmed_extractions,
            "requires_playbook_engagement": True,
            "allowed_output": "Rare mention (ONLY with playbook engagement + ≥60 days)",
            "note": "ML alone can NEVER assert persistence",
        },
        "allowed_pattern_classes": ALLOWED_PATTERN_CLASSES,
        "forbidden_pattern_classes": FORBIDDEN_PATTERN_CLASSES + DISALLOWED_PATTERN_CLASSES,
    }
