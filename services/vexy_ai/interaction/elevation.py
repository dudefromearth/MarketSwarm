"""
Elevation Engine — Subtle tier upgrade messaging.

Rules: never urgent, never manipulative, max 1 line, not during silence.
Redis cooldown prevents over-showing.
"""

from __future__ import annotations

import random
from typing import Any, Optional

# Templates per tier — calm, structural, non-pushy
TEMPLATES = {
    "observer": [
        "Playbooks hold the structure this question is reaching for.",
        "This depth of reflection opens at Activator.",
        "Campaign orchestration becomes available at Activator level.",
        "Echo continuity — where sessions remember — opens at Activator.",
    ],
    "observer_restricted": [
        "Activator holds the depth this moment asks for.",
        "Full continuity available at Activator tier.",
        "The reflection you're reaching for lives at a deeper level.",
    ],
    "activator": [
        "Full agent deployment and VIX-scaled intensity open at Navigator.",
        "Despair loop detection and FP-Protocol live at Navigator level.",
        "30-day Echo depth and cross-session synthesis open at Navigator.",
    ],
}

# Cooldown: 1 hour between elevation hints per user
COOLDOWN_SECONDS = 3600
COOLDOWN_KEY_PREFIX = "vexy:elevation:cooldown"


class ElevationEngine:
    """
    Generates subtle elevation hints with Redis-backed cooldown.
    """

    def __init__(self, buses: Any, logger: Any):
        self._buses = buses
        self._logger = logger

    async def get_hint(self, user_id: int, tier: str) -> Optional[str]:
        """
        Get an elevation hint for the user, respecting cooldown.

        Returns:
            Message string or None if on cooldown or no hint available.
        """
        templates = TEMPLATES.get(tier)
        if not templates:
            return None

        # Check cooldown
        cooldown_key = f"{COOLDOWN_KEY_PREFIX}:{user_id}"
        existing = await self._buses.market.get(cooldown_key)
        if existing:
            return None

        # Pick a random template
        message = random.choice(templates)

        # Set cooldown
        await self._buses.market.set(cooldown_key, "1", ex=COOLDOWN_SECONDS)

        return message
