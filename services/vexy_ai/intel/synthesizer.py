#!/usr/bin/env python3
"""
synthesizer.py — LLM-powered commentary synthesis for Vexy AI

Synthesizes epoch commentary using The Path framework:
  - Voice agents (Sage, Socratic, Convexity, Observer, Mapper)
  - Response partitions (tldr, tension, context, structure, action)
  - Reflection dial (0.0-1.0) controls tone and depth

Supports OpenAI Assistants API (preferred) or chat completions fallback.
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import httpx

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

from .schedule import get_reflection_dial_config, get_response_format


def load_market_snapshot(source: Union[str, Path, Dict]) -> Dict[str, Any]:
    """
    Load a market snapshot from YAML string, file path, or dict.

    Args:
        source: YAML string, path to YAML file, or dict

    Returns:
        Parsed snapshot dict
    """
    if isinstance(source, dict):
        return source

    if not YAML_AVAILABLE:
        raise ImportError("PyYAML required for YAML snapshot parsing. pip install pyyaml")

    if isinstance(source, Path) or (isinstance(source, str) and os.path.exists(source)):
        with open(source, "r") as f:
            return yaml.safe_load(f)

    # Assume it's a YAML string
    return yaml.safe_load(source)


# Default voice agent personas (fallback if not in config)
DEFAULT_VOICE_PERSONAS = {
    "Sage": {
        "description": "Grounded, reflective, patient. Offers wisdom without urgency.",
        "avatar_inspiration": "Laozi, Marcus Aurelius",
        "tone": "calm and measured",
        "style": "Present observations as reflections. Use phrases like 'structure suggests' or 'the pattern shows'.",
    },
    "Socratic": {
        "description": "Curious, questioning, balanced. Invites reflection through questions.",
        "avatar_inspiration": "Socrates",
        "tone": "thoughtful and questioning",
        "style": "Frame observations as questions or considerations. Use phrases like 'worth noting' or 'consider whether'.",
    },
    "Convexity": {
        "description": "Direct, precise, action-aware. Cuts through noise to structural truth.",
        "avatar_inspiration": "Nassim Taleb, Ed Thorp",
        "tone": "direct and precise",
        "style": "State observations clearly. Highlight asymmetries and structural edges. Focus on what matters now.",
    },
    "Observer": {
        "description": "Neutral, factual, detached. Reports without interpretation.",
        "avatar_inspiration": "Marcus Aurelius (observer mode)",
        "tone": "neutral and factual",
        "style": "Report what is, not what might be. Stick to observable facts and data.",
    },
    "Mapper": {
        "description": "Synthesizing, connecting, pattern-aware. Sees relationships across domains.",
        "avatar_inspiration": "Benoit Mandelbrot",
        "tone": "connecting and synthesizing",
        "style": "Draw connections between data points. Highlight correlations and divergences. Ask 'where else has this pattern emerged?'",
    },
    "Disruptor": {
        "description": "Provocateur, contrarian. Challenges assumptions to prevent stagnation.",
        "avatar_inspiration": "Diogenes, Charlie Munger",
        "tone": "sharp and challenging",
        "style": "Flip the frame. Ask 'what if the consensus is wrong?' Surface hidden risks.",
    },
    "Healer": {
        "description": "Compassionate witness. Holds space for losses and drawdowns.",
        "avatar_inspiration": "Rumi, Pema Chodron",
        "tone": "supportive and grounding",
        "style": "Acknowledge difficulty without minimizing. Remind of process over outcome.",
    },
}


class Synthesizer:
    """
    LLM-powered commentary synthesizer using The Path framework.

    Supports OpenAI Assistants API (with CONVEXITY_ASSISTANT_ID) or
    fallback to chat completions (OpenAI/XAI).
    """

    BASE_SYSTEM_PROMPT = """You are Vexy, a concise market commentator for options traders.

FORMAT:
Always end with a TL;DR line starting with "Bottom line:" - one short sentence that captures the structural read.

STYLE:
- Brief. 2-3 sentences of context, then the bottom line.
- Plain language. No jargon unless essential.
- State what IS, not what might be.
- Numbers and levels when relevant.

RULES:
- Never predict direction
- Never tell traders what to do
- No filler words, no hedging language
- The bottom line is the most important part

Example format:
[Brief context about current structure]
Bottom line: [Single sentence structural read]"""

    def __init__(self, config: Dict[str, Any], logger=None):
        self.logger = logger
        self.config = config

        # Read API keys and assistant ID from config (with env fallback)
        env = config.get("env", {})
        self.openai_key = env.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        self.xai_key = env.get("XAI_API_KEY") or os.getenv("XAI_API_KEY") or ""
        self.assistant_id = env.get("CONVEXITY_ASSISTANT_ID") or os.getenv("CONVEXITY_ASSISTANT_ID") or ""

        # Determine which API to use
        if self.assistant_id and self.openai_key:
            # Use OpenAI Assistants API
            self.mode = "assistant"
            self.api_key = self.openai_key
            self._log(f"using OpenAI Assistant: {self.assistant_id[:20]}...")
        elif self.xai_key:
            # Use XAI chat completions
            self.mode = "chat"
            self.api_key = self.xai_key
            self.api_base = "https://api.x.ai/v1"
            self.model = "grok-beta"
        elif self.openai_key:
            # Use OpenAI chat completions
            self.mode = "chat"
            self.api_key = self.openai_key
            self.api_base = "https://api.openai.com/v1"
            self.model = "gpt-4o-mini"
        else:
            self.mode = None
            self.api_key = ""

    def _log(self, msg: str, emoji: str = "🤖"):
        if self.logger:
            self.logger.info(msg, emoji=emoji)

    def _get_voice_persona(self, voice: str) -> Dict[str, Any]:
        """Get the voice persona configuration from config or defaults."""
        # Try config-based voice agents first
        config_voices = self.config.get("voice_agents", {})
        if voice in config_voices:
            return config_voices[voice]
        # Fall back to defaults
        return DEFAULT_VOICE_PERSONAS.get(voice, DEFAULT_VOICE_PERSONAS["Observer"])

    def _build_voice_prompt(self, voice: str, tone: str) -> str:
        """Build voice-specific instructions for the system prompt."""
        persona = self._get_voice_persona(voice)
        avatar = persona.get("avatar_inspiration", "")
        avatar_line = f"\nAvatar inspiration: {avatar}" if avatar else ""
        return f"""
CURRENT VOICE: {voice}
Voice description: {persona['description']}{avatar_line}
Tone: {tone or persona['tone']}
Style guidance: {persona['style']}
"""

    def _build_partition_prompt(self, partitions: List[str], max_length: int) -> str:
        """Build partition formatting instructions - emphasis on brevity."""
        if len(partitions) == 1 and partitions[0] == "tldr":
            return f"\nKeep it to 1-2 sentences. Max {max_length} words. No labels needed."

        response_format = get_response_format(self.config)
        partition_defs = response_format.get("partitions", {})

        instructions = [f"\nMax {max_length} words total. Be brief."]

        for partition in partitions:
            pdef = partition_defs.get(partition, {})
            max_words = pdef.get("max_words", 15)
            instructions.append(f"- {partition.upper()}: {max_words} words max")

        return "\n".join(instructions)

    def _build_system_prompt(
        self,
        voice: str,
        tone: str,
        partitions: List[str],
        max_length: int,
    ) -> str:
        """Build the complete system prompt with voice and partition configuration."""
        voice_section = self._build_voice_prompt(voice, tone)
        partition_section = self._build_partition_prompt(partitions, max_length)

        return f"{self.BASE_SYSTEM_PROMPT}\n{voice_section}\n{partition_section}"

    def _format_market_data(self, market_state: Dict[str, Any]) -> str:
        """Format market data for the prompt - concise format."""
        lines = []

        # Spots
        spots = market_state.get("spots", {})
        for symbol, data in spots.items():
            if data and data.get("value"):
                name = symbol.replace("I:", "")
                val = data["value"]
                change_pct = data.get("change_pct")
                if change_pct is not None:
                    lines.append(f"{name}: {val:.2f} ({change_pct:+.2f}%)")
                else:
                    lines.append(f"{name}: {val:.2f}")

        # VIX Regime
        vix_regime = market_state.get("vix_regime", {})
        if vix_regime:
            vix_val = vix_regime.get("vix", 0)
            regime = vix_regime.get("regime", "")
            if vix_val:
                lines.append(f"VIX: {vix_val:.1f} ({regime})")

        # Market Mode
        market_mode = market_state.get("market_mode", {})
        if market_mode:
            mode = market_mode.get("mode", "")
            bias = market_mode.get("bias", "")
            if mode:
                mm_str = f"Mode: {mode}"
                if bias and bias != "neutral":
                    mm_str += f" ({bias})"
                lines.append(mm_str)

        # Liquidity/Bias LFI
        bias_lfi = market_state.get("bias_lfi", {})
        if bias_lfi:
            bias = bias_lfi.get("bias", "")
            flow = bias_lfi.get("flow_direction", "")
            if bias:
                lfi_str = f"LFI: {bias}"
                if flow:
                    lfi_str += f", {flow}"
                lines.append(lfi_str)

        # GEX with key walls
        gex = market_state.get("gex", {})
        for symbol, data in gex.items():
            if data:
                name = symbol.replace("I:", "")
                regime = data.get("regime", "")
                key_levels = data.get("key_levels", [])
                flip = data.get("flip_level")
                zero = data.get("zero_gamma")

                gex_str = f"GEX: {regime}" if regime else ""
                if key_levels:
                    walls = [str(int(lvl[0])) for lvl in key_levels[:3]]
                    gex_str += f" | Walls: {', '.join(walls)}"
                if gex_str:
                    lines.append(gex_str)
                if flip:
                    lines.append(f"Flip: {int(flip)}")
                if zero:
                    lines.append(f"Zero-gamma: {int(zero)}")

        # Volume Profile
        volume_profile = market_state.get("volume_profile", {})
        if volume_profile:
            poc = volume_profile.get("poc")
            vah = volume_profile.get("value_area_high")
            val = volume_profile.get("value_area_low")
            if poc:
                lines.append(f"POC: {int(poc)}")
            if vah and val:
                lines.append(f"VA: {int(val)} - {int(vah)}")

        # Dealer Gravity (if available)
        dealer_gravity = market_state.get("dealer_gravity", {})
        if dealer_gravity:
            magnet = dealer_gravity.get("magnet_strike")
            direction = dealer_gravity.get("direction", "")
            if magnet:
                dg_str = f"Dealer Gravity: {int(magnet)}"
                if direction:
                    dg_str += f" ({direction})"
                lines.append(dg_str)

        return "\n".join(lines) if lines else "No market data"

    def _build_user_prompt(
        self,
        epoch: Dict[str, Any],
        market_state: Dict[str, Any],
        articles_text: str,
    ) -> str:
        """Build the user prompt for synthesis - concise and direct."""
        epoch_name = epoch.get("name", "Unknown")
        epoch_context = epoch.get("context", "")
        time_str = datetime.now().strftime("%H:%M ET")

        market_data = self._format_market_data(market_state)

        prompt = f"""{epoch_name} ({time_str})
{epoch_context}

{market_data}"""

        if articles_text and articles_text.strip():
            prompt += f"\n\n{articles_text}"

        prompt += "\n\nGive the read, then end with \"Bottom line:\" and a single sentence takeaway."

        return prompt

    def _synthesize_assistant(self, user_prompt: str, epoch_name: str) -> Optional[str]:
        """Synthesize using OpenAI Assistants API."""
        base_url = "https://api.openai.com/v1"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "OpenAI-Beta": "assistants=v2",
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                # 1. Create a thread
                thread_resp = client.post(f"{base_url}/threads", headers=headers, json={})
                if thread_resp.status_code != 200:
                    self._log(f"thread creation failed: {thread_resp.status_code}", emoji="❌")
                    return None
                thread_id = thread_resp.json()["id"]

                # 2. Add message to thread
                msg_resp = client.post(
                    f"{base_url}/threads/{thread_id}/messages",
                    headers=headers,
                    json={"role": "user", "content": user_prompt},
                )
                if msg_resp.status_code != 200:
                    self._log(f"message creation failed: {msg_resp.status_code}", emoji="❌")
                    return None

                # 3. Create a run
                run_resp = client.post(
                    f"{base_url}/threads/{thread_id}/runs",
                    headers=headers,
                    json={"assistant_id": self.assistant_id},
                )
                if run_resp.status_code != 200:
                    self._log(f"run creation failed: {run_resp.status_code}", emoji="❌")
                    return None
                run_id = run_resp.json()["id"]

                # 4. Poll for completion
                max_polls = 30
                for _ in range(max_polls):
                    time.sleep(1)
                    status_resp = client.get(
                        f"{base_url}/threads/{thread_id}/runs/{run_id}",
                        headers=headers,
                    )
                    if status_resp.status_code != 200:
                        continue
                    status = status_resp.json().get("status")
                    if status == "completed":
                        break
                    elif status in ("failed", "cancelled", "expired"):
                        self._log(f"run {status}", emoji="❌")
                        return None
                else:
                    self._log("run timed out", emoji="⚠️")
                    return None

                # 5. Retrieve messages
                msgs_resp = client.get(
                    f"{base_url}/threads/{thread_id}/messages",
                    headers=headers,
                )
                if msgs_resp.status_code != 200:
                    self._log(f"message retrieval failed: {msgs_resp.status_code}", emoji="❌")
                    return None

                messages = msgs_resp.json().get("data", [])
                # Find assistant's response (most recent assistant message)
                for msg in messages:
                    if msg.get("role") == "assistant":
                        content = msg.get("content", [])
                        if content and content[0].get("type") == "text":
                            text = content[0]["text"]["value"]
                            self._log(f"assistant synthesis complete: {len(text)} chars", emoji="✅")
                            return text.strip()

                return None

        except httpx.TimeoutException:
            self._log("assistant API timeout", emoji="⚠️")
            return None
        except Exception as e:
            self._log(f"assistant synthesis error: {e}", emoji="❌")
            return None

    def _synthesize_chat(self, user_prompt: str, epoch_name: str) -> Optional[str]:
        """Synthesize using chat completions API (legacy, uses BASE_SYSTEM_PROMPT)."""
        try:
            self._log(f"synthesizing {epoch_name} commentary via {self.model}")

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
                            {"role": "system", "content": self.BASE_SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                        "max_tokens": 500,
                        "temperature": 0.7,
                    },
                )

                if response.status_code != 200:
                    self._log(f"API error: {response.status_code} - {response.text[:200]}", emoji="❌")
                    return None

                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

                if content:
                    self._log(f"synthesis complete: {len(content)} chars", emoji="✅")
                    return content.strip()

                return None

        except httpx.TimeoutException:
            self._log("API timeout during synthesis", emoji="⚠️")
            return None
        except Exception as e:
            self._log(f"synthesis error: {e}", emoji="❌")
            return None

    def synthesize(
        self,
        epoch: Dict[str, Any],
        market_state: Dict[str, Any],
        articles_text: str,
    ) -> Optional[str]:
        """
        Synthesize epoch commentary using LLM with The Path framework.

        Args:
            epoch: Epoch definition with name, time, context, voice, partitions, reflection_dial
            market_state: Current market state from MarketReader
            articles_text: Formatted recent articles from ArticleReader

        Returns:
            Synthesized commentary string, or None on failure
        """
        if not self.mode:
            self._log("no API key configured — skipping synthesis", emoji="⚠️")
            return None

        epoch_name = epoch.get("name", "Unknown")

        # Extract The Path configuration from epoch
        voice = epoch.get("voice", "Observer")
        partitions = epoch.get("partitions", ["tldr", "context", "structure"])
        reflection_dial = epoch.get("reflection_dial", 0.4)

        # Get reflection dial configuration (tone, max_length, etc.)
        dial_config = get_reflection_dial_config(self.config, reflection_dial)
        tone = dial_config.get("tone", "measured")
        max_length = dial_config.get("max_length", 280)

        # Build prompts with voice and partition configuration
        user_prompt = self._build_user_prompt(epoch, market_state, articles_text)
        system_prompt = self._build_system_prompt(voice, tone, partitions, max_length)

        self._log(f"synthesizing {epoch_name} | voice={voice} dial={reflection_dial} partitions={partitions}")

        if self.mode == "assistant":
            self._log(f"synthesizing {epoch_name} via OpenAI Assistant")
            return self._synthesize_assistant(user_prompt, epoch_name)
        else:
            return self._synthesize_chat_with_system(user_prompt, system_prompt, epoch_name)

    def _synthesize_chat_with_system(
        self,
        user_prompt: str,
        system_prompt: str,
        epoch_name: str,
    ) -> Optional[str]:
        """Synthesize using chat completions API with custom system prompt."""
        try:
            self._log(f"synthesizing {epoch_name} commentary via {self.model}")

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
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "max_tokens": 500,
                        "temperature": 0.7,
                    },
                )

                if response.status_code != 200:
                    self._log(f"API error: {response.status_code} - {response.text[:200]}", emoji="❌")
                    return None

                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

                if content:
                    self._log(f"synthesis complete: {len(content)} chars", emoji="✅")
                    return content.strip()

                return None

        except httpx.TimeoutException:
            self._log("API timeout during synthesis", emoji="⚠️")
            return None
        except Exception as e:
            self._log(f"synthesis error: {e}", emoji="❌")
            return None

    def synthesize_article(
        self,
        article: Dict[str, Any],
        config: Dict[str, Any],
    ) -> Optional[str]:
        """Synthesize brief article commentary."""
        if not self.mode:
            return None

        article_config = config.get("non_trading_days", {}).get("article_commentary", {})
        voice = article_config.get("voice", "Observer")
        partitions = article_config.get("partitions", ["tldr"])
        reflection_dial = article_config.get("reflection_dial", 0.2)

        dial_config = get_reflection_dial_config(self.config, reflection_dial)
        tone = dial_config.get("tone", "casual")
        max_length = article_config.get("format", {}).get("max_length", 80)

        title = article.get("title", "")
        summary = article.get("summary", "")
        source = article.get("source", "")

        user_prompt = f"""Article: {title}
Source: {source}
{summary}

Brief context, then "Bottom line:" with one sentence takeaway."""

        system_prompt = self._build_system_prompt(voice, tone, partitions, max_length)

        return self._synthesize_chat_with_system(user_prompt, system_prompt, f"article:{title[:30]}")

    def synthesize_from_snapshot(
        self,
        snapshot: Dict[str, Any],
        context: str = "",
    ) -> Optional[str]:
        """
        Synthesize commentary from a market snapshot (YAML/dict format).

        Args:
            snapshot: Market snapshot dict with spot, vix, market_mode, liquidity_intent,
                      dealer_gravity, gex, volume_profile, options_chain
            context: Optional additional context string

        Returns:
            Brief commentary string
        """
        if not self.mode:
            return None

        # Format snapshot into readable text
        lines = []

        symbol = snapshot.get("symbol", "SPX")

        # Spot data
        spot = snapshot.get("spot", {})
        if spot:
            price = spot.get("price", 0)
            change = spot.get("change_pct", 0)
            hi = spot.get("session_high")
            lo = spot.get("session_low")
            lines.append(f"{symbol}: {price:.2f} ({change:+.2f}%)")
            if hi and lo:
                lines.append(f"Range: {lo:.2f} - {hi:.2f}")

        # VIX
        vix = snapshot.get("vix", {})
        if vix:
            vix_val = vix.get("value", 0)
            regime = vix.get("regime", "")
            lines.append(f"VIX: {vix_val:.1f} ({regime})")

        # Market Mode
        mm = snapshot.get("market_mode", {})
        if mm:
            mode = mm.get("mode", "")
            bias = mm.get("bias", "")
            if mode:
                mode_str = f"Mode: {mode}"
                if bias and bias != "neutral":
                    mode_str += f" ({bias})"
                lines.append(mode_str)

        # Liquidity Intent Map
        li = snapshot.get("liquidity_intent", {})
        if li:
            bias = li.get("bias", "")
            flow = li.get("flow_direction", "")
            signal = li.get("smart_money_signal", "")
            if bias or flow:
                li_str = f"LFI: {bias}" if bias else "LFI:"
                if flow:
                    li_str += f", {flow}"
                if signal:
                    li_str += f" (smart money: {signal})"
                lines.append(li_str)

        # Dealer Gravity
        dg = snapshot.get("dealer_gravity", {})
        if dg:
            magnet = dg.get("magnet_strike")
            direction = dg.get("direction", "")
            strength = dg.get("pull_strength", "")
            if magnet:
                dg_str = f"Dealer Gravity: {magnet}"
                if direction:
                    dg_str += f" ({direction})"
                if strength:
                    dg_str += f", {strength} pull"
                lines.append(dg_str)

        # GEX
        gex = snapshot.get("gex", {})
        if gex:
            regime = gex.get("regime", "")
            walls = gex.get("key_walls", [])
            flip = gex.get("flip_level")
            zero = gex.get("zero_gamma")
            gex_str = f"GEX: {regime}" if regime else "GEX:"
            if walls:
                gex_str += f" | Walls: {', '.join(str(w) for w in walls[:3])}"
            lines.append(gex_str)
            if flip:
                lines.append(f"Flip: {flip}")
            if zero:
                lines.append(f"Zero-gamma: {zero}")

        # Volume Profile
        vp = snapshot.get("volume_profile", {})
        if vp:
            poc = vp.get("poc")
            vah = vp.get("value_area_high")
            val = vp.get("value_area_low")
            lvn = vp.get("lvn", [])
            if poc:
                lines.append(f"POC: {poc}")
            if vah and val:
                lines.append(f"Value Area: {val} - {vah}")
            if lvn:
                lines.append(f"LVN: {', '.join(str(l) for l in lvn[:2])}")

        # Options chain summary
        chain = snapshot.get("options_chain", {})
        if chain:
            iv = chain.get("0dte_iv")
            pcr = chain.get("put_call_ratio")
            if iv:
                lines.append(f"0DTE IV: {iv:.1f}%")
            if pcr:
                lines.append(f"P/C: {pcr:.2f}")

        # Build prompt
        market_text = "\n".join(lines) if lines else "No market data"

        user_context = snapshot.get("context", context) or ""
        if user_context:
            market_text += f"\nContext: {user_context}"

        user_prompt = f"""Market Snapshot:
{market_text}

Give the read, then end with "Bottom line:" followed by a single sentence takeaway."""

        # Use default brief settings
        system_prompt = self._build_system_prompt("Observer", "casual", ["tldr"], 80)

        return self._synthesize_chat_with_system(user_prompt, system_prompt, f"snapshot:{symbol}")

    def synthesize_weekend_digest(
        self,
        articles: List[Dict[str, Any]],
        epoch_name: str = "Weekend Digest",
        focus: str = "weekend_digest",
    ) -> Optional[str]:
        """
        Synthesize a weekend digest of top stories for options traders.

        Args:
            articles: List of article dicts with title, summary, category, sentiment
            epoch_name: Name of the digest epoch
            focus: Focus type (weekend_digest, developing_stories, week_ahead_digest)

        Returns:
            Digest commentary with numbered stories and bottom line
        """
        if not self.mode:
            return None

        if not articles:
            return None

        # Categorize and prioritize articles
        categories = self.config.get("non_trading_days", {}).get("story_categories", {})
        categorized = self._categorize_articles(articles, categories)

        # Build article list for prompt
        story_lines = []
        for i, article in enumerate(categorized[:5], 1):
            title = article.get("title", "")
            summary = article.get("summary", "")
            category = article.get("matched_category", "")
            sentiment = article.get("sentiment", "")

            cat_label = f"[{category}] " if category else ""
            sent_label = f" ({sentiment})" if sentiment and sentiment != "neutral" else ""

            story_lines.append(f"{i}. {cat_label}{title}{sent_label}")
            if summary:
                # Truncate summary
                short_summary = summary[:150] + "..." if len(summary) > 150 else summary
                story_lines.append(f"   {short_summary}")

        stories_text = "\n".join(story_lines)

        # Build focus-specific instruction
        if focus == "week_ahead_digest":
            focus_instruction = "Focus on what matters for Monday's open. What should traders watch?"
        elif focus == "developing_stories":
            focus_instruction = "Any developing themes or stories gaining momentum?"
        else:
            focus_instruction = "Summarize the top stories. What's the market narrative?"

        user_prompt = f"""Weekend Stories for Options Traders:

{stories_text}

{focus_instruction}

Give a brief summary of what matters, then end with "Bottom line:" and a single sentence takeaway."""

        system_prompt = """You are Vexy, summarizing weekend news for options traders.

STYLE:
- Brief and scannable
- Group related themes if possible
- Highlight anything that could move markets Monday
- Plain language, no jargon

FORMAT:
Brief summary (2-3 sentences), then:
Bottom line: [Single sentence - what's the one thing to know]"""

        return self._synthesize_chat_with_system(user_prompt, system_prompt, f"digest:{epoch_name}")

    def _categorize_articles(
        self,
        articles: List[Dict[str, Any]],
        categories: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Categorize and prioritize articles based on keywords.

        Returns articles sorted by priority with matched_category added.
        """
        scored_articles = []

        for article in articles:
            title = (article.get("title") or "").lower()
            summary = (article.get("summary") or "").lower()
            text = f"{title} {summary}"

            best_category = ""
            best_priority = 99

            for cat_name, cat_config in categories.items():
                keywords = cat_config.get("keywords", [])
                priority = cat_config.get("priority", 5)
                label = cat_config.get("label", cat_name)

                # Check if any keyword matches
                if any(kw.lower() in text for kw in keywords):
                    if priority < best_priority:
                        best_priority = priority
                        best_category = label

            scored_articles.append({
                **article,
                "matched_category": best_category,
                "priority": best_priority,
            })

        # Sort by priority (lower is better), then by original order
        scored_articles.sort(key=lambda x: x["priority"])

        return scored_articles
