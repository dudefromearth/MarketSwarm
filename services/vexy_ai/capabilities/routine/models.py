"""
Routine Capability Models - Pydantic request/response models.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class MarketContext(BaseModel):
    """Market context for routine briefings."""
    globex_summary: Optional[str] = None
    vix_level: Optional[float] = None
    vix_regime: Optional[str] = None
    gex_posture: Optional[str] = None
    market_mode: Optional[str] = None
    market_mode_score: Optional[float] = None
    directional_strength: Optional[float] = None
    lfi_score: Optional[float] = None
    spx_value: Optional[float] = None
    spx_change_percent: Optional[float] = None
    opex_proximity: Optional[int] = None
    macro_events_today: Optional[List[Dict[str, Any]]] = None


class UserContext(BaseModel):
    """User context for routine briefings."""
    focus: Optional[str] = None
    energy: Optional[str] = None
    emotional_load: Optional[str] = None
    intent: Optional[str] = None
    intent_note: Optional[str] = None
    free_text: Optional[str] = None


class OpenLoops(BaseModel):
    """Open loops (tensions) for routine briefings."""
    open_trades: int = 0
    unjournaled_closes: int = 0
    armed_alerts: int = 0


class RoutineBriefingRequest(BaseModel):
    """Request for routine briefing."""
    mode: str = "routine"
    timestamp: Optional[str] = None
    market_context: Optional[MarketContext] = None
    user_context: Optional[UserContext] = None
    open_loops: Optional[OpenLoops] = None
    user_id: Optional[int] = None


class RoutineBriefingResponse(BaseModel):
    """Response for routine briefing."""
    briefing_id: str
    mode: str
    narrative: str
    generated_at: str
    model: str


class RoutineOrientationRequest(BaseModel):
    """Request for routine orientation (Mode A)."""
    vix_level: Optional[float] = None
    vix_regime: Optional[str] = None


class RoutineOrientationResponse(BaseModel):
    """Response for routine orientation."""
    orientation: Optional[str]  # None = silence is valid
    context_phase: str
    generated_at: str


class MarketReadinessResponse(BaseModel):
    """Response for market readiness artifact."""
    success: bool
    data: Dict[str, Any]
    error: Optional[str] = None


class MarketStateEventItem(BaseModel):
    """Single economic event."""
    time_et: str
    name: str
    impact: str


class MarketStateBigPicture(BaseModel):
    """Big Picture Volatility lens."""
    vix: float
    regime_key: str
    regime_label: str
    decay_profile: str
    gamma_sensitivity: str


class MarketStateLocalVol(BaseModel):
    """Localized Volatility lens."""
    dealer_posture: str
    intraday_expansion_probability: str
    localized_vol_label: str


class MarketStateEventEnergy(BaseModel):
    """Event Risk & Potential Energy lens."""
    events: List[MarketStateEventItem]
    event_posture: str


class MarketStateConvexity(BaseModel):
    """Convexity Temperature lens."""
    temperature: str
    summary: str


class MarketStateResponse(BaseModel):
    """SoM v2 — State of the Market response."""
    schema_version: str
    generated_at: str
    context_phase: str
    big_picture_volatility: Optional[MarketStateBigPicture] = None
    localized_volatility: Optional[MarketStateLocalVol] = None
    event_energy: Optional[MarketStateEventEnergy] = None
    convexity_temperature: Optional[MarketStateConvexity] = None


class LogHealthSignal(BaseModel):
    """Log health signal for routine context."""
    type: str
    severity: str
    value: Optional[Any] = None
    message: str


class LogHealthContextRequest(BaseModel):
    """Request to ingest log health context."""
    user_id: int
    routine_date: str  # YYYY-MM-DD format
    signals: List[LogHealthSignal]


class LogHealthContextResponse(BaseModel):
    """Response for log health context ingestion."""
    success: bool
    message: str
    signal_count: int
