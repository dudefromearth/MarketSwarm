"""
ConversationCache — Trim, tag, and store conversation exchanges in Echo Redis.

Tier limits:
- Observer: 5 conversations
- Activator: 15 conversations
- Navigator: 25 conversations
- Administrator: 50 conversations

Each exchange is trimmed (doctrine preamble stripped, compressed to ~500 tokens)
and auto-tagged (bias, playbook, gate, etc.).
"""

import re
import time
from typing import Any, Dict, List, Optional

from .echo_redis import EchoRedisClient


# Tier-based conversation limits
TIER_CONVERSATION_LIMITS = {
    "observer": 5,
    "observer_restricted": 3,
    "activator": 15,
    "navigator": 25,
    "coaching": 25,
    "administrator": 50,
}

# Auto-tag patterns (keyword → tag)
AUTO_TAG_PATTERNS = {
    r"\b(fomo|chasing|revenge)\b": "bias",
    r"\b(playbook|structure|framework)\b": "playbook",
    r"\b(gate|block|refuse|redirect)\b": "gate",
    r"\b(tension|conflict|pull)\b": "tension",
    r"\b(loss|drawdown|tilt)\b": "pressure",
    r"\b(routine|morning|process)\b": "routine",
    r"\b(position|trade|entry|exit)\b": "trade",
    r"\b(vix|gamma|gex|dealer)\b": "market_structure",
}

# Preamble patterns to strip from Vexy responses
PREAMBLE_PATTERNS = [
    r"^## .*?Mode.*?\n",
    r"^You are in .*? mode\..*?\n",
    r"^---\n",
]

MAX_EXCHANGE_TOKENS = 500  # Approximate target


class ConversationCache:
    """Manages conversation exchanges in the hot tier."""

    def __init__(self, echo_client: EchoRedisClient, logger: Any):
        self._echo = echo_client
        self._logger = logger

    async def store_exchange(
        self,
        user_id: int,
        tier: str,
        surface: str,
        user_message: str,
        vexy_response: str,
        outlet: str = "chat",
    ) -> bool:
        """
        Store a trimmed and tagged conversation exchange.

        Returns True if stored, False if echo unavailable or error.
        """
        if not self._echo.available:
            return False

        # Trim
        trimmed_user = self._trim_message(user_message, max_chars=800)
        trimmed_vexy = self._trim_response(vexy_response, max_chars=1200)

        # Auto-tag
        combined = f"{user_message} {vexy_response}".lower()
        tags = self._auto_tag(combined)

        exchange = {
            "ts": time.time(),
            "surface": surface,
            "outlet": outlet,
            "user_message": trimmed_user,
            "vexy_response": trimmed_vexy,
            "tags": tags,
        }

        max_conversations = TIER_CONVERSATION_LIMITS.get(tier.lower(), 5)
        return await self._echo.write_conversation(user_id, exchange, max_conversations)

    async def get_recent(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent conversation exchanges."""
        return await self._echo.read_conversations(user_id, limit)

    def _trim_message(self, text: str, max_chars: int = 800) -> str:
        """Trim user message to approximate token budget."""
        if not text:
            return ""
        text = text.strip()
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "..."

    def _trim_response(self, text: str, max_chars: int = 1200) -> str:
        """Trim Vexy response: strip doctrine preamble, compress."""
        if not text:
            return ""
        text = text.strip()

        # Strip preamble patterns
        for pattern in PREAMBLE_PATTERNS:
            text = re.sub(pattern, "", text, flags=re.MULTILINE)

        text = text.strip()
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "..."

    def _auto_tag(self, text: str) -> List[str]:
        """Auto-tag conversation based on keyword patterns."""
        tags = set()
        for pattern, tag in AUTO_TAG_PATTERNS.items():
            if re.search(pattern, text, re.IGNORECASE):
                tags.add(tag)
        return sorted(tags)
