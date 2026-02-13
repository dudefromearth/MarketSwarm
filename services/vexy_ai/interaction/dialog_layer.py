"""
Dialog Layer — Fast deterministic classification engine.

Pure-function classifier. Zero IO, zero LLM calls.
Returns ACK in <250ms with one of: PROCEED, CLARIFY, REFUSE, SILENCE.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from .models import DialogResponse, DialogNext, InteractionRequest


# Surface → required context keys (if missing → CLARIFY)
SURFACE_CONTEXT_REQUIREMENTS: Dict[str, list] = {
    "routine": ["market_context"],
    "journal": [],
    "playbook": [],
    "chat": [],
}

# Surfaces available per tier
SURFACE_ACCESS: Dict[str, list] = {
    "observer": ["chat"],
    "observer_restricted": ["chat"],
    "activator": ["chat", "journal", "playbook"],
    "navigator": ["chat", "journal", "playbook", "routine"],
    "coaching": ["chat", "journal", "playbook", "routine"],
    "administrator": ["chat", "journal", "playbook", "routine"],
}

# Features blocked per tier (observer asking for strategy → REFUSE)
BLOCKED_INTENTS: Dict[str, list] = {
    "observer": ["strategy", "execution", "playbook_detail", "campaign"],
    "observer_restricted": ["strategy", "execution", "playbook_detail", "campaign", "echo", "continuity"],
}

# Keywords that hint at blocked intent (lightweight, no NLP)
INTENT_KEYWORDS: Dict[str, list] = {
    "strategy": ["strategy", "how do i trade", "entry", "exit", "strike", "expiration"],
    "execution": ["execute", "step by step", "walkthrough", "do this"],
    "playbook_detail": ["explain the playbook", "playbook details", "show me the playbook"],
    "campaign": ["campaign", "orchestrate", "multi-leg"],
    "echo": ["remember", "last time", "you said before", "continuity"],
    "continuity": ["pick up where", "we discussed", "follow up on"],
}


class DialogLayer:
    """
    Pure-function classification engine for interaction requests.

    No IO, no LLM — only deterministic rules.
    """

    def classify(
        self,
        request: InteractionRequest,
        user_id: int,
        resolved_tier: str,
        remaining_today: int,
        active_job_id: Optional[str] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> DialogResponse:
        """
        Classify an interaction request and return an immediate ACK.

        Args:
            request: The interaction request
            user_id: Internal DB user ID
            resolved_tier: Tier after trial check
            remaining_today: Messages remaining today (-1 = unlimited)
            active_job_id: If user already has an active job for this surface
            settings: Admin interaction settings (if any)

        Returns:
            DialogResponse with status and next action
        """
        interaction_id = str(uuid.uuid4())
        channel = f"vexy_interaction:{user_id}"

        # --- De-duplication: active job for this user+surface ---
        if active_job_id:
            return DialogResponse(
                interaction_id=interaction_id,
                status="proceed",
                message="Continuing previous reflection...",
                next=DialogNext(action="stream", job_id=active_job_id, channel=channel),
                tier=resolved_tier,
                remaining_today=remaining_today,
            )

        # --- Rate limit check ---
        if remaining_today == 0:
            return DialogResponse(
                interaction_id=interaction_id,
                status="refuse",
                message="Rate limit reached. Take a breath — try again in a bit.",
                tier=resolved_tier,
                remaining_today=0,
            )

        # --- Surface validation ---
        allowed_surfaces = SURFACE_ACCESS.get(resolved_tier, ["chat"])
        if request.surface not in allowed_surfaces:
            return DialogResponse(
                interaction_id=interaction_id,
                status="refuse",
                message=f"The {request.surface} surface opens at a deeper tier.",
                tier=resolved_tier,
                remaining_today=remaining_today,
            )

        # --- Surface disabled by admin ---
        if settings:
            surfaces_settings = settings.get("surfaces", {})
            if surfaces_settings.get(f"{request.surface}_disabled"):
                return DialogResponse(
                    interaction_id=interaction_id,
                    status="silence",
                    message=None,
                    tier=resolved_tier,
                    remaining_today=remaining_today,
                )

        # --- Missing required context ---
        required = SURFACE_CONTEXT_REQUIREMENTS.get(request.surface, [])
        for key in required:
            value = getattr(request, key, None) or (request.context or {}).get(key)
            if not value:
                return DialogResponse(
                    interaction_id=interaction_id,
                    status="clarify",
                    message=f"I need market context to reflect in {request.surface} mode.",
                    tier=resolved_tier,
                    remaining_today=remaining_today,
                )

        # --- Blocked intent check (observer tiers) ---
        blocked = BLOCKED_INTENTS.get(resolved_tier, [])
        if blocked:
            detected = self._detect_blocked_intent(request.message, blocked)
            if detected:
                return DialogResponse(
                    interaction_id=interaction_id,
                    status="refuse",
                    message=self._get_refusal_message(detected, resolved_tier),
                    tier=resolved_tier,
                    remaining_today=remaining_today,
                )

        # --- Empty message ---
        if not request.message.strip():
            return DialogResponse(
                interaction_id=interaction_id,
                status="silence",
                message=None,
                tier=resolved_tier,
                remaining_today=remaining_today,
            )

        # --- PROCEED: everything checks out ---
        return DialogResponse(
            interaction_id=interaction_id,
            status="proceed",
            message="Reflecting...",
            next=DialogNext(action="stream", job_id=None, channel=channel),
            tier=resolved_tier,
            remaining_today=remaining_today,
        )

    def _detect_blocked_intent(self, message: str, blocked_intents: list) -> Optional[str]:
        """Check if the message hints at a blocked intent."""
        msg_lower = message.lower()
        for intent in blocked_intents:
            keywords = INTENT_KEYWORDS.get(intent, [])
            for keyword in keywords:
                if keyword in msg_lower:
                    return intent
        return None

    def _get_refusal_message(self, intent: str, tier: str) -> str:
        """Get a calm, non-manipulative refusal message."""
        messages = {
            "strategy": "That depth of reflection opens at a deeper tier.",
            "execution": "Step-by-step execution lives in the Playbooks.",
            "playbook_detail": "Playbook internals hold the structure this question reaches for.",
            "campaign": "Campaign orchestration becomes available at Activator level.",
            "echo": "Continuity across sessions opens at Activator.",
            "continuity": "Full continuity available at a deeper tier.",
        }
        return messages.get(intent, "That depth of reflection isn't available in this mode.")
