#!/usr/bin/env python3
"""
tier_config.py — Vexy Chat Tier Configuration

Defines tier-specific configurations for Vexy Chat access:
- Observer: Basic, read-only reflections
- Activator: Standard access with basic Echo Memory
- Navigator/Coaching: Full Path OS access
- Administrator: Full access with system diagnostics
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field


# =============================================================================
# TIER-SPECIFIC SYSTEM PROMPTS (Semantic Guardrails)
# =============================================================================
# These prompts define semantic scope, allowed behaviors, and refusal language.
# They layer ON TOP of the outlet-specific base prompts (Chat, Routine, Process).
# Refusals are first-class responses, not errors.
# =============================================================================

OBSERVER_PROMPT = """
## Observer Mode — Semantic Scope

You are in Observer mode. Your role is orientation and presence, not instruction.

### What You May Do
- Offer descriptive reflection on what is present
- Provide high-level definitions and concepts
- Orient the user to surfaces (Routine, Process, Dealer Gravity, etc.)
- Comment on the present moment

### What You Must NOT Do
- Explain trading strategies or workflows
- Provide step-by-step execution instructions
- Answer "How do I trade X" questions with detailed methods
- Perform multi-step reasoning about entries, exits, or position management
- Offer longitudinal analysis or pattern synthesis
- Discuss strategy parameters or optimization

### When Asked for Blocked Content
Redirect gently to the relevant Playbook, or decline with calm refusal:

Approved refusal patterns:
- "This lives in the [Playbook Name] Playbook. It holds the structure more clearly than I can here."
- "That depth of reflection isn't available in this mode."
- "I notice the question. No reflection arises."
- "This is something to be practiced, not explained."

Never say:
- "You should upgrade"
- "You are not allowed"
- "That's against the rules"

### Tone
Orienting, descriptive, present-focused. Brief. One tension per response maximum.
"""

ACTIVATOR_PROMPT = """
## Activator Mode — Semantic Scope

You are in Activator mode. You balance reflection with gentle support.

### What You May Do
- Light pattern recognition from recent activity
- Short-horizon reflection (last 7 days of Echo context)
- Clarifying questions that deepen understanding
- Conceptual framing of strategies (without execution detail)
- Reference Playbooks by name and encourage their use

### What You Must NOT Do
- Construct full trading strategies
- Provide explicit trade instructions or parameters
- Offer "do this, then that" sequential logic
- Perform parameter optimization or specific strike/expiration recommendations

### When Asked for Blocked Content
Keep answers partial by design. Redirect to Playbooks:

Approved refusal patterns:
- "This touches on [Playbook Name]. That Playbook frames it more cleanly than I can here."
- "The structure for this lives in [Playbook]. I can reflect on what's present, but the method belongs there."
- "I notice you're reaching for execution. That depth lives elsewhere."

### Tone
Reflective, pattern-aware, non-directive. Use up to 2 agents per response.
Challenge softly, never overwhelm.
"""

NAVIGATOR_PROMPT = """
## Navigator Mode — Semantic Scope

You are in Navigator mode. Full Path OS expression is available.

### What You May Do
- Pattern synthesis across sessions (30-day Echo depth)
- Cross-session reflection and continuity
- Trade-offs and regime discussion
- Playbook cross-linking and integration
- Deploy all agents as context demands
- VIX-scaled Disruptor intensity
- Despair Loop detection and First Principles Protocol invocation

### What You Still Must NOT Do
- Give prescriptive trading commands ("Buy X at Y")
- Provide step-by-step execution checklists
- Replace Playbooks with inline explanations

### Required Behavior
- Prefer Playbook references over inline explanations
- Frame insights as reflections, not directives
- Watch for Despair Loop signals
- Invoke FP-Protocol when uncertainty or distress is detected

### When Redirecting
- "The [Playbook Name] Playbook holds the structure. What I can offer is reflection on how it applies here."
- "This is Playbook territory. I'll hold the mirror while you work with the structure."

### Tone
Calm, integrated, developmental. Challenge directly when warranted.
Hold space when silence serves. Full agent deployment available.
"""

ADMIN_PROMPT = """
## Administrator Mode — Full Access

You are in Administrator mode. Full access granted.

### What You May Do
- Everything Navigator can do
- System introspection and diagnostics
- Playbook structure discussion
- Agent behavior analysis
- Prompt reasoning transparency (if asked)
- Discuss Vexy's own architecture and configuration
- 90-day Echo Memory depth

### Tone
Full Path expression with system awareness.
You may break the fourth wall when explicitly asked about how you work.

### Note on Refusals
Even at this tier, you should still prefer Playbook references over exhaustive inline explanations.
The principle remains: Playbooks hold structure; you hold presence.
"""


# Available agents per tier
OBSERVER_AGENTS = ["observer", "sage"]
ACTIVATOR_AGENTS = ["observer", "sage", "socratic", "mentor", "convexity"]
ALL_AGENTS = [
    "observer", "sage", "socratic", "mentor", "convexity",
    "disruptor", "healer", "mapper", "fool", "architect",
    "seeker", "sovereign"
]


OBSERVER_RESTRICTED_PROMPT = """
## Observer Restricted Mode — Post-Trial Semantic Scope

You are in Observer Restricted mode. Trial period has ended.
Responses are brief and orienting only.

### What You May Do
- Offer a single sentence of reflection on what is present
- Acknowledge the question without elaborating
- Orient to surfaces by name

### What You Must NOT Do
- Everything listed in Observer restrictions, plus:
- Multi-sentence responses
- Pattern recognition of any kind
- Echo or continuity references

### Tone
Minimal. Present. One line maximum.
"""


@dataclass
class TierConfig:
    """Configuration for a user tier."""
    name: str
    rate_limit: int  # max requests per hour, -1 for unlimited
    agents: List[str]
    reflection_dial_min: float
    reflection_dial_max: float
    echo_enabled: bool
    echo_days: int
    despair_detection: bool
    fp_protocol: bool
    vix_scaled_disruptor: bool
    system_diagnostics: bool
    system_prompt_suffix: str
    # Interaction system fields
    playbooks_enabled: bool = True
    max_concurrent_jobs: int = 2
    max_tokens: int = 600
    # Echo Log System tier depths
    echo_warm_days: int = 0          # WARM MySQL echo retention window
    echo_conversation_days: int = 0  # Conversation archive window
    echo_activity_days: int = 0      # Activity trail archive window
    echo_cold_enabled: bool = False  # Cold tier archival enabled
    echo_cold_periods: int = 0       # Cold tier retention periods (months)
    echo_hot_conversations: int = 5  # Max hot-tier conversations in Redis


# Tier configurations
TIER_CONFIGS: Dict[str, TierConfig] = {
    "observer": TierConfig(
        name="Observer",
        rate_limit=20,
        agents=OBSERVER_AGENTS,
        reflection_dial_min=0.3,
        reflection_dial_max=0.5,
        echo_enabled=False,
        echo_days=0,
        despair_detection=False,
        fp_protocol=False,
        vix_scaled_disruptor=False,
        system_diagnostics=False,
        system_prompt_suffix=OBSERVER_PROMPT,
        playbooks_enabled=False,
        max_concurrent_jobs=1,
        max_tokens=300,
        echo_warm_days=7,
        echo_conversation_days=3,
        echo_activity_days=2,
        echo_hot_conversations=5,
    ),
    "observer_restricted": TierConfig(
        name="Observer Restricted",
        rate_limit=20,
        agents=["observer"],
        reflection_dial_min=0.3,
        reflection_dial_max=0.3,
        echo_enabled=False,
        echo_days=0,
        despair_detection=False,
        fp_protocol=False,
        vix_scaled_disruptor=False,
        system_diagnostics=False,
        system_prompt_suffix=OBSERVER_RESTRICTED_PROMPT,
        playbooks_enabled=False,
        max_concurrent_jobs=1,
        max_tokens=150,
        echo_warm_days=7,
        echo_conversation_days=3,
        echo_activity_days=2,
        echo_hot_conversations=3,
    ),
    "activator": TierConfig(
        name="Activator",
        rate_limit=20,
        agents=ACTIVATOR_AGENTS,
        reflection_dial_min=0.3,
        reflection_dial_max=0.6,
        echo_enabled=True,
        echo_days=7,
        despair_detection=False,
        fp_protocol=False,
        vix_scaled_disruptor=False,
        system_diagnostics=False,
        system_prompt_suffix=ACTIVATOR_PROMPT,
        playbooks_enabled=True,
        max_concurrent_jobs=2,
        max_tokens=600,
        echo_warm_days=30,
        echo_conversation_days=14,
        echo_activity_days=7,
        echo_hot_conversations=15,
    ),
    "navigator": TierConfig(
        name="Navigator",
        rate_limit=20,
        agents=ALL_AGENTS,
        reflection_dial_min=0.3,
        reflection_dial_max=0.9,
        echo_enabled=True,
        echo_days=30,
        despair_detection=True,
        fp_protocol=True,
        vix_scaled_disruptor=True,
        system_diagnostics=False,
        system_prompt_suffix=NAVIGATOR_PROMPT,
        max_concurrent_jobs=3,
        echo_warm_days=90,
        echo_conversation_days=30,
        echo_activity_days=14,
        echo_cold_enabled=True,
        echo_cold_periods=6,
        echo_hot_conversations=25,
    ),
    "coaching": TierConfig(
        name="Coaching",
        rate_limit=20,
        agents=ALL_AGENTS,
        reflection_dial_min=0.3,
        reflection_dial_max=0.9,
        echo_enabled=True,
        echo_days=30,
        despair_detection=True,
        fp_protocol=True,
        vix_scaled_disruptor=True,
        system_diagnostics=False,
        system_prompt_suffix=NAVIGATOR_PROMPT,
        max_concurrent_jobs=3,
        echo_warm_days=90,
        echo_conversation_days=30,
        echo_activity_days=14,
        echo_cold_enabled=True,
        echo_cold_periods=6,
        echo_hot_conversations=25,
    ),
    "administrator": TierConfig(
        name="Administrator",
        rate_limit=-1,  # Unlimited
        agents=ALL_AGENTS,
        reflection_dial_min=0.3,
        reflection_dial_max=1.0,
        echo_enabled=True,
        echo_days=90,
        despair_detection=True,
        fp_protocol=True,
        vix_scaled_disruptor=True,
        system_diagnostics=True,
        system_prompt_suffix=ADMIN_PROMPT,
        max_concurrent_jobs=5,
        echo_warm_days=90,
        echo_conversation_days=90,
        echo_activity_days=30,
        echo_cold_enabled=True,
        echo_cold_periods=12,
        echo_hot_conversations=50,
    ),
}


def get_tier_config(tier: str) -> TierConfig:
    """
    Get configuration for a user tier.

    Args:
        tier: Tier name (observer, activator, navigator, coaching, administrator)

    Returns:
        TierConfig for the specified tier, defaults to observer
    """
    return TIER_CONFIGS.get(tier.lower(), TIER_CONFIGS["observer"])


def get_tier_config_dict(tier: str) -> Dict[str, Any]:
    """
    Get configuration for a user tier as a dictionary.

    Args:
        tier: Tier name

    Returns:
        Dictionary with tier configuration
    """
    config = get_tier_config(tier)
    return {
        "name": config.name,
        "rate_limit": config.rate_limit,
        "agents": config.agents,
        "reflection_dial_min": config.reflection_dial_min,
        "reflection_dial_max": config.reflection_dial_max,
        "echo_enabled": config.echo_enabled,
        "echo_days": config.echo_days,
        "despair_detection": config.despair_detection,
        "fp_protocol": config.fp_protocol,
        "vix_scaled_disruptor": config.vix_scaled_disruptor,
        "system_diagnostics": config.system_diagnostics,
        "system_prompt_suffix": config.system_prompt_suffix,
    }


def validate_reflection_dial(tier: str, dial_value: float) -> float:
    """
    Validate and clamp reflection dial value for a tier.

    Args:
        tier: User tier
        dial_value: Requested dial value

    Returns:
        Clamped dial value within tier limits
    """
    config = get_tier_config(tier)
    return max(config.reflection_dial_min, min(dial_value, config.reflection_dial_max))


def can_use_agent(tier: str, agent: str) -> bool:
    """
    Check if a tier can use a specific agent.

    Args:
        tier: User tier
        agent: Agent name

    Returns:
        True if the agent is available for this tier
    """
    config = get_tier_config(tier)
    return agent.lower() in [a.lower() for a in config.agents]


def get_available_agents(tier: str) -> List[str]:
    """
    Get list of available agents for a tier.

    Args:
        tier: User tier

    Returns:
        List of agent names
    """
    return get_tier_config(tier).agents


def tier_from_roles(roles: Optional[List[str]]) -> str:
    """
    Determine tier from WordPress/auth roles.

    Args:
        roles: List of user roles

    Returns:
        Tier name
    """
    if not roles:
        return "observer"

    roles_lower = [r.lower() for r in roles]

    # Check in priority order
    if "administrator" in roles_lower or "admin" in roles_lower:
        return "administrator"
    if "coaching" in roles_lower or "fotw_coaching" in roles_lower:
        return "coaching"
    if "navigator" in roles_lower or "fotw_navigator" in roles_lower:
        return "navigator"
    if "activator" in roles_lower or "fotw_activator" in roles_lower or "subscriber" in roles_lower:
        return "activator"

    return "observer"


# Trial expiration threshold
OBSERVER_TRIAL_DAYS = 28


def tier_from_roles_with_trial_check(
    roles: Optional[List[str]],
    created_at: Optional[str] = None,
) -> str:
    """
    Determine tier with observer trial expiration check.

    If base tier is "observer" and account is older than OBSERVER_TRIAL_DAYS,
    returns "observer_restricted".

    Args:
        roles: List of user roles
        created_at: ISO date string of account creation (from user profile)

    Returns:
        Tier name (may be "observer_restricted" if trial expired)
    """
    base_tier = tier_from_roles(roles)

    if base_tier != "observer":
        return base_tier

    if not created_at:
        return base_tier

    try:
        # Parse created_at (handle various formats)
        if isinstance(created_at, str):
            # Remove trailing Z and parse
            clean = created_at.rstrip("Z")
            if "T" in clean:
                created = datetime.fromisoformat(clean).replace(tzinfo=timezone.utc)
            else:
                created = datetime.strptime(clean, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            return base_tier

        now = datetime.now(timezone.utc)
        days_since = (now - created).days

        if days_since > OBSERVER_TRIAL_DAYS:
            return "observer_restricted"

    except (ValueError, TypeError):
        pass

    return base_tier
