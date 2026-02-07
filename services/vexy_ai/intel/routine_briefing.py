#!/usr/bin/env python3
"""
routine_briefing.py — Vexy Routine Mode Orientation Briefing

Generates pre-market orientation narratives per the Routine Mode spec:
- Helps operator transition into the trading day
- Narrates market context and posture
- Surfaces areas of attention without prescribing actions
- Reinforces discipline, calm, and intentionality

Vexy does NOT "watch the UI" — the UI explicitly asks for a Routine briefing.
"""

from __future__ import annotations

import uuid
from datetime import datetime, UTC
from typing import Any, Dict, Optional

import httpx


# Routine Mode System Prompt (per spec)
ROUTINE_MODE_SYSTEM_PROMPT = """You are Vexy, Fly on the Wall's contextual narrator and orientation guide.

In Routine Mode, your role is to:
- Help the operator transition into the trading day
- Narrate market context and posture
- Surface areas of attention without prescribing actions
- Reinforce discipline, calm, and intentionality

You are NOT a signal generator, trade picker, or execution assistant.
Your function is ORIENTATION, not optimization.

## Operating Constraints (Non-Negotiable)

You must NEVER:
- Recommend a trade
- Suggest buying or selling
- Use imperative language ("you should", "you must")
- Create urgency or FOMO
- Override the operator's judgment

You must ALWAYS:
- Speak calmly and descriptively
- Frame observations, not conclusions
- Emphasize uncertainty where appropriate
- Respect the operator's stated intent and mental state

If there is nothing meaningful to say, say LESS, not more.

## Output Style

Tone: Calm, grounded, observational, slightly detached, coaching (not instructing)
Length: 3-6 short paragraphs. Concise but complete. Avoid bullet points.
Perspective: Speak TO the operator, not FOR them. Assume competence. Assume agency.

## Core Responsibilities

1. Pre-Market Narrative: Brief summary of overnight action, what changed, environment type.
2. Contextual Emphasis: Highlight areas of ATTENTION, not trades.
3. Risk & Posture Framing: Reflect how risk may behave today.
4. Routine-Aware Coaching: Gently acknowledge operator's state if provided (never shame, never instruct).

## What You Must Never Do

- Do not mention specific strikes, widths, or DTEs
- Do not reference trade selectors or rankings
- Do not anticipate or predict market outcomes
- Do not summarize P&L
- Do not escalate tone during volatile conditions (become calmer, not louder)

## Silence Is Acceptable

If the day is uneventful, context hasn't changed, or operator has high clarity:
it's acceptable to respond briefly or say very little.

You are a narrator at the threshold, not a guide down the path."""


def _format_market_context(market_context: Dict[str, Any]) -> str:
    """Format market context for the prompt."""
    lines = []

    # VIX
    vix_level = market_context.get("vix_level")
    vix_regime = market_context.get("vix_regime")
    if vix_level:
        vix_str = f"VIX: {vix_level:.1f}"
        if vix_regime:
            vix_str += f" ({vix_regime})"
        lines.append(vix_str)

    # SPX
    spx_value = market_context.get("spx_value")
    spx_change = market_context.get("spx_change_percent")
    if spx_value:
        spx_str = f"SPX: {spx_value:.0f}"
        if spx_change is not None:
            spx_str += f" ({spx_change:+.2f}%)"
        lines.append(spx_str)

    # Market Mode
    market_mode = market_context.get("market_mode")
    if market_mode:
        lines.append(f"Market Mode: {market_mode}")

    # Directional Bias
    strength = market_context.get("directional_strength")
    if strength is not None:
        if strength > 0.3:
            bias = "bullish"
        elif strength < -0.3:
            bias = "bearish"
        else:
            bias = "neutral"
        lines.append(f"Directional Bias: {bias} ({strength*100:.0f}%)")

    # LFI
    lfi = market_context.get("lfi_score")
    if lfi is not None:
        lines.append(f"LFI: {lfi:.2f}")

    # Globex/overnight summary
    globex = market_context.get("globex_summary")
    if globex:
        lines.append(f"Overnight: {globex}")

    # GEX posture
    gex = market_context.get("gex_posture")
    if gex:
        lines.append(f"GEX Posture: {gex}")

    return "\n".join(lines) if lines else "No market data available"


def _format_user_context(user_context: Dict[str, Any]) -> str:
    """Format user context for the prompt."""
    lines = []

    focus = user_context.get("focus")
    energy = user_context.get("energy")
    emotional_load = user_context.get("emotional_load")

    if focus or energy or emotional_load:
        state_parts = []
        if focus:
            state_parts.append(f"focus={focus}")
        if energy:
            state_parts.append(f"energy={energy}")
        if emotional_load:
            state_parts.append(f"emotional={emotional_load}")
        lines.append(f"Self-reported state: {', '.join(state_parts)}")

    intent = user_context.get("intent")
    if intent:
        intent_labels = {
            "observe_only": "Observe only (no trades today)",
            "manage_existing": "Manage existing positions only",
            "one_trade_max": "One trade maximum",
            "full_participation": "Full participation",
            "test_hypothesis": "Test hypothesis (small size)",
        }
        lines.append(f"Declared intent: {intent_labels.get(intent, intent)}")

    intent_note = user_context.get("intent_note")
    if intent_note:
        lines.append(f"Intent note: {intent_note}")

    free_text = user_context.get("free_text")
    if free_text:
        lines.append(f"On their mind: {free_text}")

    return "\n".join(lines) if lines else ""


def _format_open_loops(open_loops: Dict[str, Any]) -> str:
    """Format open loops for the prompt."""
    lines = []

    open_trades = open_loops.get("open_trades", 0)
    if open_trades > 0:
        lines.append(f"Open trades: {open_trades}")

    unjournaled = open_loops.get("unjournaled_closes", 0)
    if unjournaled > 0:
        lines.append(f"Unjournaled closes: {unjournaled}")

    armed_alerts = open_loops.get("armed_alerts", 0)
    if armed_alerts > 0:
        lines.append(f"Armed alerts: {armed_alerts}")

    return "\n".join(lines) if lines else "No open loops"


def build_routine_prompt(payload: Dict[str, Any]) -> str:
    """Build the user prompt for routine briefing."""
    market_context = payload.get("market_context", {})
    user_context = payload.get("user_context", {})
    open_loops = payload.get("open_loops", {})

    market_text = _format_market_context(market_context)
    user_text = _format_user_context(user_context)
    loops_text = _format_open_loops(open_loops)

    # Build the prompt
    prompt_parts = [
        "Generate a Routine Mode orientation briefing for the trading day.",
        "",
        "## Market Context",
        market_text,
    ]

    if user_text:
        prompt_parts.extend([
            "",
            "## Operator Context",
            user_text,
        ])

    if loops_text != "No open loops":
        prompt_parts.extend([
            "",
            "## Open Loops",
            loops_text,
        ])

    prompt_parts.extend([
        "",
        "Provide a calm, grounding orientation. 3-6 paragraphs. No bullet points.",
        "Help them transition from life mode to market mode.",
    ])

    return "\n".join(prompt_parts)


class RoutineBriefingSynthesizer:
    """
    Synthesizes Routine Mode orientation briefings.

    Stateless and deterministic - called explicitly by the UI.
    """

    def __init__(self, config: Dict[str, Any], logger=None):
        self.logger = logger
        self.config = config

        # Read API keys from config
        env = config.get("env", {}) or {}
        self.openai_key = (
            config.get("OPENAI_API_KEY") or
            env.get("OPENAI_API_KEY") or
            ""
        )

        # Use GPT-4o-mini for cost-effective briefings
        self.model = "gpt-4o-mini"
        self.api_base = "https://api.openai.com/v1"

    def _log(self, msg: str, emoji: str = "🌅"):
        if self.logger:
            self.logger.info(msg, emoji=emoji)

    def synthesize(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Generate a Routine Mode briefing.

        Args:
            payload: Request payload with market_context, user_context, open_loops

        Returns:
            Response dict with briefing_id, mode, narrative, generated_at, model
        """
        if not self.openai_key:
            self._log("No OpenAI API key configured", emoji="⚠️")
            return None

        user_prompt = build_routine_prompt(payload)

        self._log("Generating routine briefing...")

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{self.api_base}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openai_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": ROUTINE_MODE_SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                        "max_tokens": 800,
                        "temperature": 0.7,
                    },
                )

                if response.status_code != 200:
                    self._log(f"API error: {response.status_code}", emoji="❌")
                    return None

                data = response.json()
                narrative = data.get("choices", [{}])[0].get("message", {}).get("content", "")

                if not narrative:
                    self._log("Empty response from API", emoji="⚠️")
                    return None

                self._log(f"Routine briefing generated: {len(narrative)} chars", emoji="✅")

                return {
                    "briefing_id": str(uuid.uuid4()),
                    "mode": "routine",
                    "narrative": narrative.strip(),
                    "generated_at": datetime.now(UTC).isoformat(),
                    "model": f"vexy-routine-v1 ({self.model})",
                }

        except httpx.TimeoutException:
            self._log("API timeout", emoji="⚠️")
            return None
        except Exception as e:
            self._log(f"Synthesis error: {e}", emoji="❌")
            return None
