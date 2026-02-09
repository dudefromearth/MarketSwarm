"""
Journal Capability Models - Pydantic request/response models.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, field_validator


class JournalSynopsisRequest(BaseModel):
    """Request model for generating a Daily Synopsis."""
    trade_date: str  # ISO date string YYYY-MM-DD
    trades: List[Dict[str, Any]]
    market_context: Optional[str] = None  # e.g., "CPI released pre-market"


class JournalSynopsisResponse(BaseModel):
    """Response model for Daily Synopsis."""
    synopsis_text: str
    activity: Optional[Dict[str, Any]] = None
    rhythm: Optional[Dict[str, Any]] = None
    risk_exposure: Optional[Dict[str, Any]] = None
    context: Optional[str] = None


class JournalPromptsResponse(BaseModel):
    """Response model for reflective prompts."""
    prompts: List[Dict[str, str]]
    should_vexy_speak: bool
    vexy_reflection: Optional[str] = None


class JournalChatRequest(BaseModel):
    """Request for Vexy chat in Journal context."""
    message: str
    trade_date: str  # ISO date string
    trades: List[Dict[str, Any]]
    market_context: Optional[str] = None
    is_prepared_prompt: bool = False  # True if clicking a prepared prompt

    @field_validator('message')
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('Message cannot be empty')
        return v


class JournalChatResponse(BaseModel):
    """Response for Vexy chat in Journal context."""
    response: str
    mode: str  # "direct" or "prepared"
