"""
Commentary Capability Models - Data structures for commentary system.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class Epoch(BaseModel):
    """Epoch definition for scheduled commentary."""
    name: str
    time: str  # HH:MM format
    context: Optional[str] = None
    voice: str = "Observer"
    partitions: List[str] = []
    reflection_dial: float = 0.4
    type: str = "standard"  # standard, digest
    prompt_focus: Optional[str] = None


class CommentaryPayload(BaseModel):
    """Payload for published commentary."""
    kind: str  # "epoch" or "event"
    text: str
    meta: Dict[str, Any]
    ts: str
    voice: str = "anchor"


class MarketEvent(BaseModel):
    """Market event that triggers commentary."""
    type: str  # gamma_squeeze, volume_spike, etc.
    id: str  # Unique per day
    commentary: str
    level: str = "info"  # info, warning, critical
    symbol: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class CommentaryStatusResponse(BaseModel):
    """Response for commentary status endpoint."""
    running: bool
    last_epoch: Optional[str] = None
    last_epoch_time: Optional[str] = None
    epochs_enabled: bool
    events_enabled: bool
    intel_enabled: bool
    schedule_type: str  # trading, non-trading
    next_epoch: Optional[str] = None


class TodayMessagesResponse(BaseModel):
    """Response for today's messages endpoint."""
    messages: List[Dict[str, Any]]
    count: int
