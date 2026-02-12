"""
Interaction Settings — Admin-tunable configuration stored in Redis hashes.

Settings are loaded into memory at boot and refreshed on admin update.
Multi-node ready (Redis-backed, not env vars).
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional


# Redis hash keys for settings groups
SETTINGS_KEYS = {
    "interaction": "vexy:settings:interaction",
    "elevation": "vexy:settings:elevation",
    "tiers": "vexy:settings:tiers",
    "surfaces": "vexy:settings:surfaces",
}

# Default settings
DEFAULTS: Dict[str, Dict[str, Any]] = {
    "interaction": {
        "validation_mode": "observe",
        "enabled": True,
        "timeout_seconds": 30,
        "max_message_length": 2000,
    },
    "elevation": {
        "enabled": True,
        "frequency": "hourly",
        "cooldown_seconds": 3600,
    },
    "tiers": {
        "observer_max_tokens": 300,
        "observer_restricted_max_tokens": 150,
        "activator_max_tokens": 600,
        "navigator_max_tokens": 600,
    },
    "surfaces": {
        "chat_disabled": False,
        "routine_disabled": False,
        "journal_disabled": False,
        "playbook_disabled": False,
    },
}

# Presets: named configurations that overwrite matching keys
PRESETS: Dict[str, Dict[str, Dict[str, Any]]] = {
    "trial-friendly": {
        "elevation": {"enabled": True, "cooldown_seconds": 1800},
        "tiers": {"observer_max_tokens": 400},
    },
    "conversion-optimized": {
        "elevation": {"enabled": True, "cooldown_seconds": 900},
        "tiers": {"observer_max_tokens": 250, "observer_restricted_max_tokens": 100},
    },
    "conservative": {
        "elevation": {"enabled": False},
        "tiers": {"observer_max_tokens": 300},
    },
    "performance-first": {
        "interaction": {"timeout_seconds": 20},
        "tiers": {
            "observer_max_tokens": 200,
            "activator_max_tokens": 400,
            "navigator_max_tokens": 500,
        },
    },
    "diagnostic": {
        "interaction": {"validation_mode": "enforce"},
        "elevation": {"enabled": False},
    },
}


class InteractionSettings:
    """
    Admin-tunable interaction settings backed by Redis hashes.

    Loaded into memory at boot, refreshed on admin update.
    """

    def __init__(self, buses: Any, logger: Any):
        self._buses = buses
        self._logger = logger
        self._cache: Dict[str, Dict[str, Any]] = {}

    async def load(self) -> None:
        """Load all settings from Redis into memory cache."""
        for group, redis_key in SETTINGS_KEYS.items():
            try:
                raw = await self._buses.market.hgetall(redis_key)
                if raw:
                    # Parse JSON values
                    parsed = {}
                    for k, v in raw.items():
                        try:
                            parsed[k] = json.loads(v)
                        except (json.JSONDecodeError, TypeError):
                            parsed[k] = v
                    self._cache[group] = parsed
                else:
                    self._cache[group] = dict(DEFAULTS.get(group, {}))
            except Exception as e:
                self._logger.warning(f"Failed to load settings '{group}': {e}")
                self._cache[group] = dict(DEFAULTS.get(group, {}))

        self._logger.info("Interaction settings loaded", emoji="⚙️")

    def get(self, group: str, key: Optional[str] = None) -> Any:
        """
        Get a setting value.

        Args:
            group: Settings group ("interaction", "elevation", "tiers", "surfaces")
            key: Specific key within the group. If None, returns entire group.
        """
        group_data = self._cache.get(group, DEFAULTS.get(group, {}))
        if key is None:
            return group_data
        return group_data.get(key, DEFAULTS.get(group, {}).get(key))

    def get_all(self) -> Dict[str, Dict[str, Any]]:
        """Get all settings groups."""
        result = {}
        for group in SETTINGS_KEYS:
            result[group] = self._cache.get(group, DEFAULTS.get(group, {}))
        return result

    async def set(self, group: str, key: str, value: Any) -> None:
        """Set a single setting value."""
        redis_key = SETTINGS_KEYS.get(group)
        if not redis_key:
            raise ValueError(f"Unknown settings group: {group}")

        # Update Redis
        json_value = json.dumps(value) if not isinstance(value, str) else value
        await self._buses.market.hset(redis_key, key, json_value)

        # Update cache
        if group not in self._cache:
            self._cache[group] = dict(DEFAULTS.get(group, {}))
        self._cache[group][key] = value

    async def apply_preset(self, preset_name: str) -> Dict[str, Any]:
        """Apply a named preset, overwriting matching keys."""
        preset = PRESETS.get(preset_name)
        if not preset:
            raise ValueError(f"Unknown preset: {preset_name}")

        applied = {}
        for group, settings in preset.items():
            for key, value in settings.items():
                await self.set(group, key, value)
                applied[f"{group}.{key}"] = value

        return applied

    @staticmethod
    def list_presets() -> Dict[str, Dict[str, Dict[str, Any]]]:
        """List all available presets."""
        return dict(PRESETS)
