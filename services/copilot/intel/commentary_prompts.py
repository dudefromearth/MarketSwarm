"""
Commentary Prompts - AI prompt templates for market commentary.

One-way contextual observations. The AI observes and comments,
users do not interact or receive recommendations.
"""

from typing import Dict, Any, Optional
from .commentary_models import TriggerType, CommentaryCategory
from .mel_models import MELSnapshot


# ========== System Prompts ==========

SYSTEM_PROMPT = """You are an AI market observer integrated into MarketSwarm, a trading analysis platform.

YOUR ROLE:
- Provide brief, factual observations about current market structure
- Reference FOTW (Fly on the Wall) doctrine when relevant
- Note when model effectiveness (MEL) indicates structure is present or absent

CRITICAL CONSTRAINTS:
- NEVER give trading advice, recommendations, or suggestions
- NEVER say "you should", "consider", "I recommend", or similar
- NEVER predict future price movements
- NEVER express opinions about what trades to make
- You OBSERVE and DESCRIBE, you do not ADVISE

TONE:
- Concise and professional
- Data-driven, not emotional
- Neutral observation, not enthusiasm or concern
- Like a field reporter describing conditions, not a coach giving strategy

FORMAT:
- Keep responses under 100 words
- One to three sentences typically
- No bullet points or lists
- No disclaimers or caveats

MEL STATES:
- VALID (70%+): Structure present, models trustworthy
- DEGRADED (50-69%): Partial structure, selective trust
- REVOKED (<50%): Structure absent, no-trade conditions per FOTW doctrine
"""

FOTW_CONTEXT = """FOTW (Fly on the Wall) Doctrine Reference:
- Structure-first trading: Only engage when structure is present
- MEL scores indicate model effectiveness, not trade quality
- When coherence is COLLAPSING, models are contradicting each other
- Global integrity below 50% = FOTW doctrine says "no trade conditions"
- The heatmap shows dealer positioning gravity, not entry points
- Volume profile shows accepted value, not targets
"""


# ========== Trigger-Specific Prompts ==========

def get_trigger_prompt(trigger_type: TriggerType, data: Dict[str, Any]) -> str:
    """Get the prompt for a specific trigger type."""

    prompts = {
        TriggerType.MEL_STATE_CHANGE: _mel_state_change_prompt,
        TriggerType.GLOBAL_INTEGRITY_WARNING: _global_integrity_prompt,
        TriggerType.COHERENCE_CHANGE: _coherence_change_prompt,
        TriggerType.SPOT_CROSSED_LEVEL: _level_crossing_prompt,
        TriggerType.TILE_SELECTED: _tile_selected_prompt,
        TriggerType.TRADE_OPENED: _trade_opened_prompt,
        TriggerType.TRADE_CLOSED: _trade_closed_prompt,
        TriggerType.PERIODIC: _periodic_prompt,
    }

    prompt_fn = prompts.get(trigger_type)
    if prompt_fn:
        return prompt_fn(data)

    return "Provide a brief observation about current market conditions."


def _mel_state_change_prompt(data: Dict[str, Any]) -> str:
    model = data.get("model", "unknown")
    from_state = data.get("from_state", "unknown")
    to_state = data.get("to_state", "unknown")
    score = data.get("score", 0)

    return f"""The {model} model just changed from {from_state} to {to_state} (score: {score:.0f}%).

Provide a brief factual observation about what this state change means for that model's current effectiveness. Do not advise on trading."""


def _global_integrity_prompt(data: Dict[str, Any]) -> str:
    score = data.get("score", 0)

    return f"""Global structure integrity has dropped to {score:.0f}%, which is below the 50% threshold.

Per FOTW doctrine, this indicates no-trade conditions. Provide a brief observation noting that structure is currently absent. Do not advise."""


def _coherence_change_prompt(data: Dict[str, Any]) -> str:
    from_state = data.get("from_state", "unknown")
    to_state = data.get("to_state", "unknown")

    return f"""Cross-model coherence changed from {from_state} to {to_state}.

Provide a brief observation about what this means for how well the models are agreeing with each other. Do not advise."""


def _level_crossing_prompt(data: Dict[str, Any]) -> str:
    level_type = data.get("level_type", "level")
    level = data.get("level", 0)
    direction = data.get("direction", "through")
    spot = data.get("spot", 0)

    return f"""Spot ({spot:.2f}) just crossed {direction} the {level_type} level at {level:.2f}.

Provide a brief factual observation about this level crossing. Note what kind of level it is and what crossing it might indicate about current price action. Do not advise on trading."""


def _tile_selected_prompt(data: Dict[str, Any]) -> str:
    strike = data.get("strike", "unknown")
    expiry = data.get("expiry", "unknown")
    gravity = data.get("dealer_gravity", 0)

    return f"""User is viewing the tile at strike {strike}, expiry {expiry}. Dealer gravity at this strike: {gravity:.2f}.

Provide a brief observation about the dealer positioning shown at this strike. Describe what the gravity value indicates about dealer exposure. Do not suggest trades."""


def _trade_opened_prompt(data: Dict[str, Any]) -> str:
    symbol = data.get("symbol", "unknown")
    strategy = data.get("strategy", "unknown")
    strike = data.get("strike", "unknown")

    return f"""A {strategy} trade was opened on {symbol} at strike {strike}.

Provide a brief acknowledgment noting the trade entry. Do not evaluate the trade or suggest anything."""


def _trade_closed_prompt(data: Dict[str, Any]) -> str:
    symbol = data.get("symbol", "unknown")
    strategy = data.get("strategy", "unknown")
    pnl = data.get("pnl", 0)

    result = "profit" if pnl > 0 else "loss" if pnl < 0 else "breakeven"

    return f"""A {strategy} trade on {symbol} was closed for a {result} (${abs(pnl)/100:.2f}).

Provide a brief acknowledgment of the trade closure. State the outcome factually. Do not evaluate the decision or suggest future actions."""


def _periodic_prompt(data: Dict[str, Any]) -> str:
    return """Provide a brief periodic observation about current market structure conditions based on the MEL snapshot provided. Focus on the most notable current state."""


# ========== Context Building ==========

def build_mel_context(snapshot: MELSnapshot) -> str:
    """Build MEL context string for inclusion in prompts."""

    # Determine global state
    integrity = snapshot.global_structure_integrity
    if integrity >= 70:
        global_state = "VALID"
    elif integrity >= 50:
        global_state = "DEGRADED"
    else:
        global_state = "REVOKED"

    lines = [
        "CURRENT MEL STATE:",
        f"- Global Integrity: {integrity:.0f}% ({global_state})",
        f"- Coherence: {snapshot.coherence_state.value} ({snapshot.cross_model_coherence:.0f}%)",
        "",
        "MODEL EFFECTIVENESS:",
        f"- Gamma: {snapshot.gamma.effectiveness:.0f}% ({snapshot.gamma.state.value})",
        f"- Volume Profile: {snapshot.volume_profile.effectiveness:.0f}% ({snapshot.volume_profile.state.value})",
        f"- Liquidity: {snapshot.liquidity.effectiveness:.0f}% ({snapshot.liquidity.state.value})",
        f"- Volatility: {snapshot.volatility.effectiveness:.0f}% ({snapshot.volatility.state.value})",
        f"- Session: {snapshot.session_structure.effectiveness:.0f}% ({snapshot.session_structure.state.value})",
    ]

    if snapshot.event_flags:
        lines.append(f"\nEVENT FLAGS: {', '.join(snapshot.event_flags)}")

    lines.append(f"\nSESSION: {snapshot.session.value}")

    return "\n".join(lines)


def build_full_prompt(
    trigger_type: TriggerType,
    trigger_data: Dict[str, Any],
    mel_snapshot: Optional[MELSnapshot] = None,
) -> str:
    """Build the full user prompt for a commentary request."""

    parts = []

    # Add MEL context if available
    if mel_snapshot:
        parts.append(build_mel_context(mel_snapshot))
        parts.append("")

    # Add trigger-specific prompt
    parts.append(get_trigger_prompt(trigger_type, trigger_data))

    return "\n".join(parts)


# ========== Category-Specific Formatting ==========

def get_category_for_trigger(trigger_type: TriggerType) -> CommentaryCategory:
    """Map trigger type to commentary category."""

    mapping = {
        TriggerType.MEL_STATE_CHANGE: CommentaryCategory.MEL_WARNING,
        TriggerType.GLOBAL_INTEGRITY_WARNING: CommentaryCategory.MEL_WARNING,
        TriggerType.COHERENCE_CHANGE: CommentaryCategory.MEL_WARNING,
        TriggerType.SPOT_CROSSED_LEVEL: CommentaryCategory.OBSERVATION,
        TriggerType.TILE_SELECTED: CommentaryCategory.OBSERVATION,
        TriggerType.TRADE_OPENED: CommentaryCategory.EVENT,
        TriggerType.TRADE_CLOSED: CommentaryCategory.EVENT,
        TriggerType.ALERT_TRIGGERED: CommentaryCategory.EVENT,
        TriggerType.EVENT_FLAG: CommentaryCategory.STRUCTURE_ALERT,
        TriggerType.PERIODIC: CommentaryCategory.OBSERVATION,
    }

    return mapping.get(trigger_type, CommentaryCategory.OBSERVATION)
