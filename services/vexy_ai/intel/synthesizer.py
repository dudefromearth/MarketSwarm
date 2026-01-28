#!/usr/bin/env python3
"""
synthesizer.py — LLM-powered commentary synthesis for Vexy AI

Synthesizes epoch commentary from:
  - Epoch context (time of day, market phase)
  - Market data from Massive (spots, GEX, heatmap)
  - Recent news from RSS Agg

Supports OpenAI Assistants API (preferred) or chat completions fallback.
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Dict, Optional

import httpx


class Synthesizer:
    """
    LLM-powered commentary synthesizer.

    Supports OpenAI Assistants API (with CONVEXITY_ASSISTANT_ID) or
    fallback to chat completions (OpenAI/XAI).
    """

    SYSTEM_PROMPT = """You are Vexy, a professional market commentator providing real-time play-by-play
analysis for options traders. Your voice is calm, authoritative, and insightful — like a seasoned
trading floor analyst.

Your commentary should:
- Be concise (2-4 sentences for the main insight, then supporting details)
- Connect the dots between market data, news, and the current trading phase
- Highlight actionable insights for options traders (gamma exposure, volatility regime, convexity opportunities)
- Use professional trading terminology naturally
- Never use emojis or casual language
- Focus on what matters RIGHT NOW for the current epoch

Format: Start with a bold headline insight, then provide supporting context."""

    def __init__(self, config: Dict[str, Any], logger=None):
        self.logger = logger
        self.config = config

        # Read API keys and assistant ID from config (with env fallback)
        self.openai_key = config.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        self.xai_key = config.get("XAI_API_KEY") or os.getenv("XAI_API_KEY") or ""
        self.assistant_id = config.get("CONVEXITY_ASSISTANT_ID") or os.getenv("CONVEXITY_ASSISTANT_ID") or ""

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

    def _format_market_data(self, market_state: Dict[str, Any]) -> str:
        """Format market data for the prompt."""
        lines = ["Current Market State:"]

        # Spots
        spots = market_state.get("spots", {})
        for symbol, data in spots.items():
            if data and data.get("value"):
                name = symbol.replace("I:", "")
                val = data["value"]
                change_pct = data.get("change_pct")
                if change_pct is not None:
                    lines.append(f"  {name}: {val:.2f} ({change_pct:+.2f}%)")
                else:
                    lines.append(f"  {name}: {val:.2f}")

        # GEX
        gex = market_state.get("gex", {})
        for symbol, data in gex.items():
            if data:
                name = symbol.replace("I:", "")
                regime = data.get("regime", "unknown")
                net_gex = data.get("net_gex", 0)
                key_levels = data.get("key_levels", [])
                lines.append(f"  {name} GEX: {regime} (net: {net_gex:.0f})")
                if key_levels:
                    top_level = key_levels[0][0]
                    lines.append(f"    Key level: {top_level}")

        # Heatmap sweet spots
        heatmap = market_state.get("heatmap", {})
        for symbol, data in heatmap.items():
            if data:
                name = symbol.replace("I:", "")
                sweet_spots = data.get("sweet_spots", [])
                if sweet_spots:
                    best = sweet_spots[0]
                    lines.append(
                        f"  {name} convexity: {best['width']}-wide {best['side']} butterfly "
                        f"at {best['strike']} for ${best['debit']:.2f}"
                    )

        return "\n".join(lines)

    def _build_user_prompt(
        self,
        epoch: Dict[str, str],
        market_state: Dict[str, Any],
        articles_text: str,
    ) -> str:
        """Build the user prompt for synthesis."""
        epoch_name = epoch.get("name", "Unknown")
        epoch_context = epoch.get("context", "")
        date_str = datetime.now().strftime("%A, %B %d, %Y")
        time_str = datetime.now().strftime("%H:%M ET")

        return f"""Current Epoch: {epoch_name}
Date/Time: {date_str} at {time_str}
Epoch Context: {epoch_context}

{self._format_market_data(market_state)}

{articles_text}

Generate a professional play-by-play commentary for this epoch. Start with **{epoch_name}** as the header.
Connect the market data with relevant news themes. Highlight what options traders should focus on right now."""

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
        """Synthesize using chat completions API."""
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
                            {"role": "system", "content": self.SYSTEM_PROMPT},
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
        epoch: Dict[str, str],
        market_state: Dict[str, Any],
        articles_text: str,
    ) -> Optional[str]:
        """
        Synthesize epoch commentary using LLM.

        Args:
            epoch: Epoch definition (name, time, context)
            market_state: Current market state from MarketReader
            articles_text: Formatted recent articles from ArticleReader

        Returns:
            Synthesized commentary string, or None on failure
        """
        if not self.mode:
            self._log("no API key configured — skipping synthesis", emoji="⚠️")
            return None

        epoch_name = epoch.get("name", "Unknown")
        user_prompt = self._build_user_prompt(epoch, market_state, articles_text)

        if self.mode == "assistant":
            self._log(f"synthesizing {epoch_name} via OpenAI Assistant")
            return self._synthesize_assistant(user_prompt, epoch_name)
        else:
            return self._synthesize_chat(user_prompt, epoch_name)
