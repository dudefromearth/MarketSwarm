"""
Chat Capability Models - Pydantic request/response models.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, field_validator


class ChatContext(BaseModel):
    """
    Comprehensive context provided with chat message.

    Includes market data, positions, trading activity, alerts,
    risk graph state, and UI state for full situational awareness.
    """
    # Market data
    market_data: Optional[Dict[str, Any]] = None

    # User's open positions
    positions: Optional[List[Dict[str, Any]]] = None

    # Trading activity summary
    trading: Optional[Dict[str, Any]] = None

    # Alert state
    alerts: Optional[Dict[str, Any]] = None

    # Risk graph summary
    risk: Optional[Dict[str, Any]] = None

    # Current UI state
    ui: Optional[Dict[str, Any]] = None


class UserProfile(BaseModel):
    """User profile information for personalized responses."""
    display_name: Optional[str] = None
    user_id: Optional[int] = None
    is_admin: bool = False
    preferences: Optional[Dict[str, Any]] = None


class VexyChatRequest(BaseModel):
    """Request model for Vexy chat endpoint."""
    message: str
    reflection_dial: float = 0.6
    context: Optional[ChatContext] = None
    user_tier: Optional[str] = None  # Override tier (admin only)
    user_profile: Optional[UserProfile] = None  # User identity for personalization

    @field_validator('message')
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('Message cannot be empty')
        if len(v) > 10000:
            raise ValueError('Message too long (max 10000 characters)')
        return v.strip()

    @field_validator('reflection_dial')
    @classmethod
    def reflection_dial_in_range(cls, v: float) -> float:
        if v < 0.0 or v > 1.0:
            raise ValueError('Reflection dial must be between 0.0 and 1.0')
        return v


class VexyChatResponse(BaseModel):
    """Response model for Vexy chat endpoint."""
    response: str
    agent: Optional[str] = None
    echo_updated: bool = False
    tokens_used: int = 0
    remaining_today: int = -1
