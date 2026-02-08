#!/usr/bin/env python3
"""
prompt_admin.py — Admin API for Vexy Prompt Management

Provides endpoints for viewing and editing outlet prompts without code deploys.
Prompts are stored in a JSON file that overrides the defaults.

Admin-only access.
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime, UTC

# Storage location for custom prompts
PROMPTS_FILE = Path.home() / ".fotw" / "vexy_prompts.json"


def _ensure_dir():
    """Ensure the storage directory exists."""
    PROMPTS_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_custom_prompts() -> Dict[str, str]:
    """Load custom prompts from file."""
    if not PROMPTS_FILE.exists():
        return {}
    try:
        with open(PROMPTS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_custom_prompts(prompts: Dict[str, str]):
    """Save custom prompts to file."""
    _ensure_dir()
    with open(PROMPTS_FILE, "w") as f:
        json.dump(prompts, f, indent=2)


def get_prompt(outlet: str) -> str:
    """
    Get the active prompt for an outlet.
    Returns custom prompt if set, otherwise returns default.
    """
    # Check for custom prompt first
    custom = _load_custom_prompts()
    if outlet in custom:
        return custom[outlet]

    # Fall back to defaults
    from services.vexy_ai.outlet_prompts import get_outlet_prompt
    return get_outlet_prompt(outlet)


def set_prompt(outlet: str, prompt: str) -> bool:
    """
    Set a custom prompt for an outlet.
    """
    custom = _load_custom_prompts()
    custom[outlet] = prompt
    custom[f"{outlet}_updated"] = datetime.now(UTC).isoformat()
    _save_custom_prompts(custom)
    return True


def reset_prompt(outlet: str) -> bool:
    """
    Reset an outlet to use the default prompt.
    """
    custom = _load_custom_prompts()
    if outlet in custom:
        del custom[outlet]
        if f"{outlet}_updated" in custom:
            del custom[f"{outlet}_updated"]
        _save_custom_prompts(custom)
    return True


def get_all_prompts() -> Dict[str, Dict]:
    """
    Get all prompts (both defaults and custom) for admin UI.
    """
    from services.vexy_ai.outlet_prompts import (
        CHAT_BASE_PROMPT,
        ROUTINE_BASE_PROMPT,
        PROCESS_BASE_PROMPT,
        JOURNAL_BASE_PROMPT,
    )
    from services.vexy_ai.tier_config import (
        OBSERVER_PROMPT,
        ACTIVATOR_PROMPT,
        NAVIGATOR_PROMPT,
        ADMIN_PROMPT,
    )

    custom = _load_custom_prompts()

    return {
        "outlets": {
            "chat": {
                "default": CHAT_BASE_PROMPT,
                "custom": custom.get("chat"),
                "active": custom.get("chat") or CHAT_BASE_PROMPT,
                "updated": custom.get("chat_updated"),
            },
            "routine": {
                "default": ROUTINE_BASE_PROMPT,
                "custom": custom.get("routine"),
                "active": custom.get("routine") or ROUTINE_BASE_PROMPT,
                "updated": custom.get("routine_updated"),
            },
            "process": {
                "default": PROCESS_BASE_PROMPT,
                "custom": custom.get("process"),
                "active": custom.get("process") or PROCESS_BASE_PROMPT,
                "updated": custom.get("process_updated"),
            },
            "journal": {
                "default": JOURNAL_BASE_PROMPT,
                "custom": custom.get("journal"),
                "active": custom.get("journal") or JOURNAL_BASE_PROMPT,
                "updated": custom.get("journal_updated"),
            },
        },
        "tiers": {
            "observer": {
                "default": OBSERVER_PROMPT,
                "custom": custom.get("tier_observer"),
                "active": custom.get("tier_observer") or OBSERVER_PROMPT,
                "updated": custom.get("tier_observer_updated"),
            },
            "activator": {
                "default": ACTIVATOR_PROMPT,
                "custom": custom.get("tier_activator"),
                "active": custom.get("tier_activator") or ACTIVATOR_PROMPT,
                "updated": custom.get("tier_activator_updated"),
            },
            "navigator": {
                "default": NAVIGATOR_PROMPT,
                "custom": custom.get("tier_navigator"),
                "active": custom.get("tier_navigator") or NAVIGATOR_PROMPT,
                "updated": custom.get("tier_navigator_updated"),
            },
            "administrator": {
                "default": ADMIN_PROMPT,
                "custom": custom.get("tier_administrator"),
                "active": custom.get("tier_administrator") or ADMIN_PROMPT,
                "updated": custom.get("tier_administrator_updated"),
            },
        },
    }


def get_tier_prompt(tier: str) -> str:
    """
    Get the active prompt for a tier.
    Returns custom prompt if set, otherwise returns default.
    """
    custom = _load_custom_prompts()
    key = f"tier_{tier}"
    if key in custom:
        return custom[key]

    # Fall back to defaults
    from services.vexy_ai.tier_config import get_tier_config
    return get_tier_config(tier).system_prompt_suffix


def set_tier_prompt(tier: str, prompt: str) -> bool:
    """
    Set a custom prompt for a tier.
    """
    custom = _load_custom_prompts()
    key = f"tier_{tier}"
    custom[key] = prompt
    custom[f"{key}_updated"] = datetime.now(UTC).isoformat()
    _save_custom_prompts(custom)
    return True


def reset_tier_prompt(tier: str) -> bool:
    """
    Reset a tier to use the default prompt.
    """
    custom = _load_custom_prompts()
    key = f"tier_{tier}"
    if key in custom:
        del custom[key]
        if f"{key}_updated" in custom:
            del custom[f"{key}_updated"]
        _save_custom_prompts(custom)
    return True
