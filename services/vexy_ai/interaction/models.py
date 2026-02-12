"""
Interaction Models — Pydantic models for the two-layer interaction system.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# =============================================================================
# REQUEST
# =============================================================================

class InteractionRequest(BaseModel):
    """Input to the interaction system from any surface."""
    surface: str                                    # "chat" | "routine" | "journal" | "playbook"
    message: str
    reflection_dial: float = 0.6
    context: Optional[Dict[str, Any]] = None
    user_profile: Optional[Dict[str, Any]] = None
    user_tier: Optional[str] = None                 # Admin override only

    # Surface-specific optional fields
    market_context: Optional[Dict[str, Any]] = None
    user_context: Optional[Dict[str, Any]] = None
    open_loops: Optional[Dict[str, Any]] = None


# =============================================================================
# DIALOG LAYER RESPONSE
# =============================================================================

class DialogNext(BaseModel):
    """What the frontend should do after receiving the ACK."""
    action: str                                     # "stream" | "done" | "none"
    job_id: Optional[str] = None
    channel: Optional[str] = None                   # "vexy_interaction:{userId}"


class DialogResponse(BaseModel):
    """Fast ACK from the Dialog Layer (<250ms, no LLM)."""
    interaction_id: str                             # UUID
    status: str                                     # "proceed" | "clarify" | "refuse" | "silence"
    message: Optional[str] = None                   # ACK text or refusal text
    next: Optional[DialogNext] = None               # What to do next
    ui_hints: Optional[Dict[str, Any]] = None
    tier: str
    remaining_today: int = -1


# =============================================================================
# SSE PROGRESS EVENTS
# =============================================================================

class InteractionProgressEvent(BaseModel):
    """Published to SSE during cognition. Frontend renders stage progress."""
    event: str = "stage"
    job_id: str
    stage: str                                      # "hydrate_echo", "select_playbooks", etc.
    stage_index: int
    stage_count: int
    message: str                                    # Human-readable stage description
    ts: int = Field(default_factory=lambda: int(time.time() * 1000))


class InteractionResultEvent(BaseModel):
    """Published to SSE when cognition completes."""
    event: str = "result"
    job_id: str
    interaction_id: str
    text: str
    agent: str
    agent_blend: List[str] = []
    tokens_used: int = 0
    elevation_hint: Optional[str] = None
    remaining_today: int = -1
    ts: int = Field(default_factory=lambda: int(time.time() * 1000))


class InteractionErrorEvent(BaseModel):
    """Published to SSE when cognition fails."""
    event: str = "error"
    job_id: str
    interaction_id: str
    error: str
    recoverable: bool = True
    ts: int = Field(default_factory=lambda: int(time.time() * 1000))


# =============================================================================
# ELEVATION
# =============================================================================

class ElevationHint(BaseModel):
    """Subtle tier upgrade messaging (never urgent, never manipulative)."""
    message: str
    target_tier: str = "activator"
