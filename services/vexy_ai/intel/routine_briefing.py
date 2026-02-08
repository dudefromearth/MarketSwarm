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

import os
import time
import uuid
from datetime import datetime, UTC
from typing import Any, Dict, Optional

import httpx

# Retry configuration for rate limits
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0  # seconds
BACKOFF_MULTIPLIER = 2.0


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
Length: 2-3 short paragraphs maximum. Be brief. Less is more.
Perspective: Speak TO the operator, not FOR them. Assume competence. Assume agency.
If no market data is available, say so plainly in one sentence rather than filling space with generalities.

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


def _format_log_health_signals(signals: list) -> str:
    """Format log health signals for the prompt."""
    if not signals:
        return ""

    lines = []

    # Group by signal type for cleaner presentation
    inactive_logs = []
    archive_ready = []
    ml_excluded = []
    cap_warning = None
    retirement_warnings = []

    for signal in signals:
        signal_type = signal.get("type", "")
        log_name = signal.get("log_name", "Unknown")
        message = signal.get("message", "")

        if signal_type == "log_inactive":
            inactive_logs.append(f"{log_name}: {message}")
        elif signal_type == "log_ready_for_archive":
            archive_ready.append(log_name)
        elif signal_type == "ml_excluded_active_log":
            ml_excluded.append(log_name)
        elif signal_type == "approaching_active_log_cap":
            cap_warning = message
        elif signal_type == "retirement_pending":
            retirement_warnings.append(f"{log_name}: {message}")

    if inactive_logs:
        lines.append(f"Inactive logs: {'; '.join(inactive_logs)}")

    if ml_excluded:
        lines.append(f"ML-excluded active logs: {', '.join(ml_excluded)}")

    if archive_ready:
        lines.append(f"Ready to archive: {', '.join(archive_ready)}")

    if cap_warning:
        lines.append(f"Log capacity: {cap_warning}")

    if retirement_warnings:
        lines.append(f"Retiring soon: {'; '.join(retirement_warnings)}")

    return "\n".join(lines)


def build_routine_prompt(payload: Dict[str, Any], log_health_signals: list = None) -> str:
    """Build the user prompt for routine briefing."""
    market_context = payload.get("market_context", {})
    user_context = payload.get("user_context", {})
    open_loops = payload.get("open_loops", {})

    market_text = _format_market_context(market_context)
    user_text = _format_user_context(user_context)
    loops_text = _format_open_loops(open_loops)
    log_health_text = _format_log_health_signals(log_health_signals or [])

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

    if log_health_text:
        prompt_parts.extend([
            "",
            "## Log Hygiene (mention gently if relevant, never as instruction)",
            log_health_text,
        ])

    prompt_parts.extend([
        "",
        "Provide a calm, grounding orientation. 2-3 short paragraphs maximum. No bullet points.",
        "Be specific about what's present. If data is missing, acknowledge it briefly and move on.",
    ])

    return "\n".join(prompt_parts)


class RoutineBriefingSynthesizer:
    """
    Synthesizes Routine Mode orientation briefings.

    Stateless and deterministic - called explicitly by the UI.
    Supports OpenAI Assistants API (preferred) or chat completions fallback.
    """

    def __init__(self, config: Dict[str, Any], logger=None):
        self.logger = logger
        self.config = config

        # Read API keys from config (check top-level and env dict) with env fallback
        env = config.get("env", {}) or {}
        self.openai_key = (
            config.get("OPENAI_API_KEY") or
            env.get("OPENAI_API_KEY") or
            os.getenv("OPENAI_API_KEY") or
            ""
        )
        self.xai_key = (
            config.get("XAI_API_KEY") or
            env.get("XAI_API_KEY") or
            os.getenv("XAI_API_KEY") or
            ""
        )

        # Check for Routine-specific assistant, fall back to Convexity assistant
        self.assistant_id = (
            config.get("ROUTINE_ASSISTANT_ID") or
            env.get("ROUTINE_ASSISTANT_ID") or
            os.getenv("ROUTINE_ASSISTANT_ID") or
            config.get("CONVEXITY_ASSISTANT_ID") or
            env.get("CONVEXITY_ASSISTANT_ID") or
            os.getenv("CONVEXITY_ASSISTANT_ID") or
            ""
        )

        # Determine mode: XAI preferred, then OpenAI assistant, then OpenAI chat
        if self.xai_key:
            self.mode = "chat"
            self.api_key = self.xai_key
            self.api_base = "https://api.x.ai/v1"
            self.model = "grok-3"
            self._log(f"using XAI Chat: {self.model}")
        elif self.assistant_id and self.openai_key:
            self.mode = "assistant"
            self.api_key = self.openai_key
            self.api_base = "https://api.openai.com/v1"
            self.model = "gpt-4o-mini"
            self._log(f"using OpenAI Assistant: {self.assistant_id[:20]}...")
        elif self.openai_key:
            self.mode = "chat"
            self.api_key = self.openai_key
            self.api_base = "https://api.openai.com/v1"
            self.model = "gpt-4o-mini"
            self._log(f"using OpenAI Chat: {self.model}")
        else:
            self.mode = None

    def _log(self, msg: str, emoji: str = "🌅"):
        if self.logger:
            self.logger.info(msg, emoji=emoji)

    def synthesize(
        self,
        payload: Dict[str, Any],
        log_health_signals: list = None
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a Routine Mode briefing.

        Args:
            payload: Request payload with market_context, user_context, open_loops
            log_health_signals: Optional list of log health signals for context

        Returns:
            Response dict with briefing_id, mode, narrative, generated_at, model
        """
        if not self.mode:
            self._log("No OpenAI API key configured", emoji="⚠️")
            return None

        user_prompt = build_routine_prompt(payload, log_health_signals)

        self._log("Generating routine briefing...")

        # Use Assistant API if configured, otherwise fall back to chat
        if self.mode == "assistant":
            narrative = self._synthesize_assistant(user_prompt)
            model_label = f"vexy-routine-v1 (assistant:{self.assistant_id[:12]}...)"
        else:
            narrative = self._synthesize_chat(user_prompt)
            model_label = f"vexy-routine-v1 ({self.model})"

        if not narrative:
            return None

        return {
            "briefing_id": str(uuid.uuid4()),
            "mode": "routine",
            "narrative": narrative.strip(),
            "generated_at": datetime.now(UTC).isoformat(),
            "model": model_label,
        }

    def _synthesize_assistant(self, user_prompt: str) -> Optional[str]:
        """Synthesize using OpenAI Assistants API with retry logic."""
        headers = {
            "Authorization": f"Bearer {self.openai_key}",
            "Content-Type": "application/json",
            "OpenAI-Beta": "assistants=v2",
        }

        backoff = INITIAL_BACKOFF

        for attempt in range(MAX_RETRIES):
            try:
                with httpx.Client(timeout=60.0) as client:
                    # 1. Create a thread
                    thread_resp = client.post(f"{self.api_base}/threads", headers=headers, json={})
                    if thread_resp.status_code == 429:
                        self._retry_wait(attempt, backoff, thread_resp)
                        backoff *= BACKOFF_MULTIPLIER
                        continue
                    if thread_resp.status_code != 200:
                        self._log(f"Thread creation failed: {thread_resp.status_code}", emoji="❌")
                        return None
                    thread_id = thread_resp.json()["id"]

                    # 2. Add message - assistant is already trained on Routine Mode
                    msg_resp = client.post(
                        f"{self.api_base}/threads/{thread_id}/messages",
                        headers=headers,
                        json={"role": "user", "content": user_prompt},
                    )
                    if msg_resp.status_code == 429:
                        self._retry_wait(attempt, backoff, msg_resp)
                        backoff *= BACKOFF_MULTIPLIER
                        continue
                    if msg_resp.status_code != 200:
                        self._log(f"Message creation failed: {msg_resp.status_code}", emoji="❌")
                        return None

                    # 3. Create a run
                    run_resp = client.post(
                        f"{self.api_base}/threads/{thread_id}/runs",
                        headers=headers,
                        json={"assistant_id": self.assistant_id},
                    )
                    if run_resp.status_code == 429:
                        self._retry_wait(attempt, backoff, run_resp)
                        backoff *= BACKOFF_MULTIPLIER
                        continue
                    if run_resp.status_code != 200:
                        self._log(f"Run creation failed: {run_resp.status_code}", emoji="❌")
                        return None
                    run_id = run_resp.json()["id"]

                    # 4. Poll for completion
                    max_polls = 30
                    for _ in range(max_polls):
                        time.sleep(1)
                        status_resp = client.get(
                            f"{self.api_base}/threads/{thread_id}/runs/{run_id}",
                            headers=headers,
                        )
                        if status_resp.status_code != 200:
                            continue
                        run_data = status_resp.json()
                        status = run_data.get("status")
                        if status == "completed":
                            break
                        elif status in ("failed", "cancelled", "expired"):
                            error = run_data.get("last_error", {})
                            error_msg = error.get("message", "unknown error")
                            self._log(f"Run {status}: {error_msg}", emoji="❌")
                            return None
                    else:
                        self._log("Run timed out", emoji="⚠️")
                        return None

                    # 5. Retrieve messages
                    msgs_resp = client.get(
                        f"{self.api_base}/threads/{thread_id}/messages",
                        headers=headers,
                    )
                    if msgs_resp.status_code != 200:
                        self._log(f"Message retrieval failed: {msgs_resp.status_code}", emoji="❌")
                        return None

                    messages = msgs_resp.json().get("data", [])
                    for msg in messages:
                        if msg.get("role") == "assistant":
                            content = msg.get("content", [])
                            if content and content[0].get("type") == "text":
                                text = content[0]["text"]["value"]
                                self._log(f"Assistant briefing complete: {len(text)} chars", emoji="✅")
                                return text.strip()

                    return None

            except httpx.TimeoutException:
                self._log(f"API timeout (attempt {attempt + 1}/{MAX_RETRIES})", emoji="⚠️")
                time.sleep(backoff)
                backoff *= BACKOFF_MULTIPLIER
            except Exception as e:
                self._log(f"Assistant synthesis error: {e}", emoji="❌")
                return None

        self._log(f"All {MAX_RETRIES} attempts failed", emoji="❌")
        return None

    def _synthesize_chat(self, user_prompt: str) -> Optional[str]:
        """Synthesize using chat completions API with retry logic."""
        backoff = INITIAL_BACKOFF

        for attempt in range(MAX_RETRIES):
            try:
                with httpx.Client(timeout=30.0) as client:
                    response = client.post(
                        f"{self.api_base}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
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

                    if response.status_code == 429:
                        self._retry_wait(attempt, backoff, response)
                        backoff *= BACKOFF_MULTIPLIER
                        continue

                    if response.status_code != 200:
                        self._log(f"API error: {response.status_code} - {response.text[:200]}", emoji="❌")
                        return None

                    data = response.json()
                    narrative = data.get("choices", [{}])[0].get("message", {}).get("content", "")

                    if not narrative:
                        self._log("Empty response from API", emoji="⚠️")
                        return None

                    self._log(f"Routine briefing generated: {len(narrative)} chars", emoji="✅")
                    return narrative.strip()

            except httpx.TimeoutException:
                self._log(f"API timeout (attempt {attempt + 1}/{MAX_RETRIES})", emoji="⚠️")
                time.sleep(backoff)
                backoff *= BACKOFF_MULTIPLIER
            except Exception as e:
                self._log(f"Synthesis error: {e}", emoji="❌")
                return None

        self._log(f"All {MAX_RETRIES} attempts failed", emoji="❌")
        return None

    def _retry_wait(self, attempt: int, backoff: float, response: httpx.Response) -> None:
        """Handle rate limit retry with appropriate wait time."""
        retry_after = response.headers.get("Retry-After")
        wait_time = float(retry_after) if retry_after else backoff
        self._log(f"Rate limited (429), waiting {wait_time:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})", emoji="⏳")
        time.sleep(wait_time)
