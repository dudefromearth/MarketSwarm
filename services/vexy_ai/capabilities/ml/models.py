"""
ML Capability Models - Pydantic request/response models.
"""

from typing import List, Optional
from pydantic import BaseModel


class MLStatusRequest(BaseModel):
    """Request for ML status check."""
    retrospective_count: int
    closed_trade_count: int
    distinct_period_count: int


class PatternEligibilityRequest(BaseModel):
    """Request to check pattern eligibility."""
    pattern_type: str
    sources: List[str]
    artifact_count: int
    is_template_induced: bool = False


class PatternConfirmationRequest(BaseModel):
    """Request for ML pattern confirmation."""
    pattern_id: str
    occurrences: int
    retrospective_count: int
    days_span: int
    similarity_score: float
    contradiction_ratio: float = 0.0
    market_regimes: int = 1
    stability_score: float = 0.5
    description_variance: float = 0.5
    user_has_playbooks: bool = False
    context: str = "retrospective"
    user_id: int = 1
