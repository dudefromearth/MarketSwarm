#!/usr/bin/env python3
"""
synthesizer.py — LLM-powered commentary synthesis for Vexy AI

Synthesizes epoch commentary from:
  - Epoch context (time of day, market phase)
  - Market data from Massive (spots, GEX, heatmap)
  - Recent news from RSS Agg
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx


class Synthesizer:
    """
    LLM-powered commentary synthesizer.

    Supports OpenAI and XAI (Grok) APIs.
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

    def __init__(self, logger=None):
        self.logger = logger
        self.api_key = os.getenv("OPENAI_API_KEY") or os.getenv("XAI_API_KEY")
        self.api_base = self._get_api_base()
        self.model = self._get_model()

    def _get_api_base(self) -> str:
        """Determine API base URL based on available keys."""
        if os.getenv("XAI_API_KEY"):
            return "https://api.x.ai/v1"
        return "https://api.openai.com/v1"

    def _get_model(self) -> str:
        """Determine model based on API."""
        if os.getenv("XAI_API_KEY"):
            return "grok-beta"
        return "gpt-4o-mini"

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
        if not self.api_key:
            self._log("no API key configured — skipping synthesis", emoji="⚠️")
            return None

        epoch_name = epoch.get("name", "Unknown")
        epoch_context = epoch.get("context", "")
        date_str = datetime.now().strftime("%A, %B %d, %Y")
        time_str = datetime.now().strftime("%H:%M ET")

        # Build the user prompt
        user_prompt = f"""Current Epoch: {epoch_name}
Date/Time: {date_str} at {time_str}
Epoch Context: {epoch_context}

{self._format_market_data(market_state)}

{articles_text}

Generate a professional play-by-play commentary for this epoch. Start with **{epoch_name}** as the header.
Connect the market data with relevant news themes. Highlight what options traders should focus on right now."""

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
