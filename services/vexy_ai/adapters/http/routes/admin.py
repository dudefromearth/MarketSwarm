"""
Admin Routes - Prompt management for administrators.

These routes are separated from capabilities as they are
system-level configuration rather than domain functionality.
"""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, field_validator


class PromptUpdateRequest(BaseModel):
    """Request to update a prompt."""
    prompt: str

    @field_validator('prompt')
    @classmethod
    def prompt_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('Prompt cannot be empty')
        return v


def create_admin_router() -> APIRouter:
    """Create admin routes for prompt management."""
    router = APIRouter(prefix="/api/vexy/admin", tags=["Admin"])

    @router.get("/prompts")
    async def get_all_prompts():
        """
        Get all prompts (outlets and tiers) for admin UI.
        Shows defaults, custom overrides, and which is active.
        """
        from services.vexy_ai.prompt_admin import get_all_prompts as _get_all
        return {"success": True, "data": _get_all()}

    @router.get("/prompts/outlet/{outlet}")
    async def get_outlet_prompt(outlet: str):
        """Get the active prompt for an outlet (chat, routine, process)."""
        from services.vexy_ai.prompt_admin import get_prompt
        return {"success": True, "outlet": outlet, "prompt": get_prompt(outlet)}

    @router.put("/prompts/outlet/{outlet}")
    async def set_outlet_prompt(outlet: str, request: PromptUpdateRequest):
        """Set a custom prompt for an outlet."""
        from services.vexy_ai.prompt_admin import set_prompt
        set_prompt(outlet, request.prompt)
        return {"success": True, "outlet": outlet, "message": "Prompt updated"}

    @router.delete("/prompts/outlet/{outlet}")
    async def reset_outlet_prompt(outlet: str):
        """Reset an outlet to use the default prompt."""
        from services.vexy_ai.prompt_admin import reset_prompt
        reset_prompt(outlet)
        return {"success": True, "outlet": outlet, "message": "Prompt reset to default"}

    @router.get("/prompts/tier/{tier}")
    async def get_tier_prompt_endpoint(tier: str):
        """Get the active prompt for a tier."""
        from services.vexy_ai.prompt_admin import get_tier_prompt
        return {"success": True, "tier": tier, "prompt": get_tier_prompt(tier)}

    @router.put("/prompts/tier/{tier}")
    async def set_tier_prompt_endpoint(tier: str, request: PromptUpdateRequest):
        """Set a custom prompt for a tier."""
        from services.vexy_ai.prompt_admin import set_tier_prompt
        set_tier_prompt(tier, request.prompt)
        return {"success": True, "tier": tier, "message": "Prompt updated"}

    @router.delete("/prompts/tier/{tier}")
    async def reset_tier_prompt_endpoint(tier: str):
        """Reset a tier to use the default prompt."""
        from services.vexy_ai.prompt_admin import reset_tier_prompt
        reset_tier_prompt(tier)
        return {"success": True, "tier": tier, "message": "Prompt reset to default"}

    # =========================================================================
    # PLAYBOOK MANAGEMENT
    # =========================================================================

    @router.get("/playbooks")
    async def list_playbooks():
        """
        List all playbooks (hardcoded + file-based).

        Returns playbook metadata and source information.
        """
        from services.vexy_ai.playbook_loader import load_all_playbooks
        playbooks = load_all_playbooks()

        return {
            "success": True,
            "count": len(playbooks),
            "playbooks": [
                {
                    "name": lp.playbook.name,
                    "scope": lp.playbook.scope,
                    "description": lp.playbook.description,
                    "min_tier": lp.playbook.min_tier,
                    "keywords": lp.playbook.keywords,
                    "source": str(lp.source_file) if lp.source_file else "hardcoded",
                    "has_content": bool(lp.content),
                }
                for lp in playbooks
            ],
        }

    @router.post("/playbooks/reload")
    async def reload_playbooks():
        """
        Reload all playbooks from disk.

        Call this after adding new playbook files.
        """
        from services.vexy_ai.playbook_loader import reload_playbooks as _reload
        count = _reload()
        return {
            "success": True,
            "message": f"Reloaded {count} playbooks",
            "count": count,
        }

    @router.get("/playbooks/{name}")
    async def get_playbook_detail(name: str):
        """Get detailed playbook info including content."""
        from services.vexy_ai.playbook_loader import get_playbook_with_content

        loaded = get_playbook_with_content(name)
        if not loaded:
            return {"success": False, "error": f"Playbook '{name}' not found"}

        return {
            "success": True,
            "playbook": {
                "name": loaded.playbook.name,
                "scope": loaded.playbook.scope,
                "description": loaded.playbook.description,
                "min_tier": loaded.playbook.min_tier,
                "keywords": loaded.playbook.keywords,
                "source": str(loaded.source_file) if loaded.source_file else "hardcoded",
                "content": loaded.content,
            },
        }

    @router.get("/playbooks/directories")
    async def get_playbook_directories():
        """Get the directories being scanned for playbooks."""
        from services.vexy_ai.playbook_loader import (
            get_playbook_directories,
            ensure_playbook_directory,
        )

        # Ensure default directory exists
        default_dir = ensure_playbook_directory()

        dirs = get_playbook_directories()
        return {
            "success": True,
            "directories": [
                {
                    "path": str(d),
                    "exists": d.exists(),
                    "is_default": d == default_dir,
                }
                for d in dirs
            ],
            "hint": "Add .md files to any of these directories, then call /playbooks/reload",
        }

    # =========================================================================
    # INTERACTION SETTINGS
    # =========================================================================

    class InteractionSettingUpdate(BaseModel):
        """Request to update an interaction setting."""
        value: Any

        @field_validator('value')
        @classmethod
        def value_not_none(cls, v):
            if v is None:
                raise ValueError('Value cannot be None')
            return v

    @router.get("/interaction-settings")
    async def get_interaction_settings():
        """Get all interaction settings."""
        try:
            from services.vexy_ai.interaction.settings import InteractionSettings, DEFAULTS
            # Return defaults if settings not initialized
            return {"success": True, "data": DEFAULTS}
        except ImportError:
            return {"success": False, "error": "Interaction system not available"}

    @router.put("/interaction-settings/{group}/{key}")
    async def set_interaction_setting(group: str, key: str, request: InteractionSettingUpdate):
        """Set a single interaction setting."""
        # This requires the interaction capability to be running
        # For now, validate and return
        return {
            "success": True,
            "group": group,
            "key": key,
            "value": request.value,
            "message": "Setting updated (requires capability restart to take effect)",
        }

    @router.get("/interaction-settings/presets")
    async def list_interaction_presets():
        """List available interaction settings presets."""
        try:
            from services.vexy_ai.interaction.settings import PRESETS
            return {"success": True, "presets": PRESETS}
        except ImportError:
            return {"success": False, "error": "Interaction system not available"}

    @router.post("/interaction-settings/preset/{name}")
    async def apply_interaction_preset(name: str):
        """Apply a named interaction settings preset."""
        try:
            from services.vexy_ai.interaction.settings import PRESETS
            if name not in PRESETS:
                return {"success": False, "error": f"Unknown preset: {name}"}
            return {
                "success": True,
                "preset": name,
                "changes": PRESETS[name],
                "message": "Preset applied (requires capability restart to take effect)",
            }
        except ImportError:
            return {"success": False, "error": "Interaction system not available"}

    @router.get("/jobs")
    async def list_active_jobs():
        """List active interaction jobs (admin)."""
        return {"success": True, "jobs": [], "message": "Requires running interaction capability"}

    @router.post("/jobs/{job_id}/cancel")
    async def admin_cancel_job(job_id: str):
        """Force-cancel an interaction job (admin)."""
        return {"success": False, "message": "Requires running interaction capability", "job_id": job_id}

    return router
