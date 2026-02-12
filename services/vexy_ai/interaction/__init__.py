"""
Vexy Interaction Layer — Two-layer architecture for async Vexy interactions.

Layer 1 (Dialog): Fast deterministic ACK (<250ms), no LLM
Layer 2 (Cognition): Async kernel reasoning with stage-based SSE progress
"""

from .models import (
    InteractionRequest,
    DialogResponse,
    DialogNext,
    InteractionProgressEvent,
    InteractionResultEvent,
    InteractionErrorEvent,
    ElevationHint,
)
from .dialog_layer import DialogLayer
from .job_manager import JobManager
from .cognition_layer import CognitionLayer

__all__ = [
    "InteractionRequest",
    "DialogResponse",
    "DialogNext",
    "InteractionProgressEvent",
    "InteractionResultEvent",
    "InteractionErrorEvent",
    "ElevationHint",
    "DialogLayer",
    "JobManager",
    "CognitionLayer",
]
