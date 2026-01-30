"""
ADI Data Models - AI Data Interface.

"Screens are for humans. Data is for machines."

The ADI provides canonical market structure data in machine-readable format
for AI assistants (Vexy, personal AI, etc.) to consume.

Based on TraderDH's ADI specification.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Literal
from datetime import datetime
from enum import Enum
import uuid


# Schema version for ADI exports
SCHEMA_VERSION = "gamma_snapshot_v1.0"


class ExportFormat(str, Enum):
    """Supported ADI export formats."""
    JSON = "json"
    CSV = "csv"
    TEXT = "text"


@dataclass
class PriceState:
    """Current price state."""
    spot_price: Optional[float] = None
    session_high: Optional[float] = None
    session_low: Optional[float] = None
    vwap: Optional[float] = None
    distance_from_vwap: Optional[float] = None
    intraday_range: Optional[float] = None
    realized_vol_intra: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "spot_price": self.spot_price,
            "session_high": self.session_high,
            "session_low": self.session_low,
            "vwap": self.vwap,
            "distance_from_vwap": self.distance_from_vwap,
            "intraday_range": self.intraday_range,
            "realized_vol_intra": self.realized_vol_intra,
        }


@dataclass
class VolatilityState:
    """Current volatility state."""
    call_iv_atm: Optional[float] = None
    put_iv_atm: Optional[float] = None
    iv_skew: Optional[float] = None
    iv_rv_ratio: Optional[float] = None
    vol_regime: Optional[str] = None  # low/normal/elevated/high

    def to_dict(self) -> Dict[str, Any]:
        return {
            "call_iv_atm": self.call_iv_atm,
            "put_iv_atm": self.put_iv_atm,
            "iv_skew": self.iv_skew,
            "iv_rv_ratio": self.iv_rv_ratio,
            "vol_regime": self.vol_regime,
        }


@dataclass
class GammaStructure:
    """Gamma/dealer structure state."""
    net_gex: Optional[float] = None
    zero_gamma_level: Optional[float] = None
    active_gamma_magnet: Optional[float] = None
    gex_ratio: Optional[float] = None
    call_gamma_total: Optional[float] = None
    put_gamma_total: Optional[float] = None
    high_gamma_strikes: List[float] = field(default_factory=list)
    gamma_flip_level: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "net_gex": self.net_gex,
            "zero_gamma_level": self.zero_gamma_level,
            "active_gamma_magnet": self.active_gamma_magnet,
            "gex_ratio": self.gex_ratio,
            "call_gamma_total": self.call_gamma_total,
            "put_gamma_total": self.put_gamma_total,
            "high_gamma_strikes": self.high_gamma_strikes,
            "gamma_flip_level": self.gamma_flip_level,
        }


@dataclass
class AuctionStructure:
    """Volume profile / auction structure state."""
    poc: Optional[float] = None
    value_area_high: Optional[float] = None
    value_area_low: Optional[float] = None
    rotation_state: Optional[str] = None  # balance/initiative_up/initiative_down
    auction_state: Optional[str] = None
    hvns: List[float] = field(default_factory=list)
    lvns: List[float] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "poc": self.poc,
            "value_area_high": self.value_area_high,
            "value_area_low": self.value_area_low,
            "rotation_state": self.rotation_state,
            "auction_state": self.auction_state,
            "hvns": self.hvns,
            "lvns": self.lvns,
        }


@dataclass
class Microstructure:
    """Order flow / microstructure state."""
    bid_ask_imbalance: Optional[float] = None
    aggressive_flow: Optional[str] = None  # buy/sell/neutral
    absorption_detected: Optional[bool] = None
    sweep_detected: Optional[bool] = None
    liquidity_state: Optional[str] = None  # normal/thin/vacuum

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bid_ask_imbalance": self.bid_ask_imbalance,
            "aggressive_flow": self.aggressive_flow,
            "absorption_detected": self.absorption_detected,
            "sweep_detected": self.sweep_detected,
            "liquidity_state": self.liquidity_state,
        }


@dataclass
class SessionContext:
    """Session / time context."""
    minutes_since_open: Optional[int] = None
    minutes_to_close: Optional[int] = None
    session_phase: Optional[str] = None  # pre_market/open/midday/late/after_hours
    is_rth: bool = True
    day_of_week: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "minutes_since_open": self.minutes_since_open,
            "minutes_to_close": self.minutes_to_close,
            "session_phase": self.session_phase,
            "is_rth": self.is_rth,
            "day_of_week": self.day_of_week,
        }


@dataclass
class MELScores:
    """MEL scores snapshot for ADI."""
    gamma_effectiveness: Optional[float] = None
    gamma_state: Optional[str] = None
    volume_profile_effectiveness: Optional[float] = None
    volume_profile_state: Optional[str] = None
    liquidity_effectiveness: Optional[float] = None
    liquidity_state: Optional[str] = None
    volatility_effectiveness: Optional[float] = None
    volatility_state: Optional[str] = None
    session_effectiveness: Optional[float] = None
    session_state: Optional[str] = None
    global_structure_integrity: Optional[float] = None
    coherence_state: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gamma_effectiveness": self.gamma_effectiveness,
            "gamma_state": self.gamma_state,
            "volume_profile_effectiveness": self.volume_profile_effectiveness,
            "volume_profile_state": self.volume_profile_state,
            "liquidity_effectiveness": self.liquidity_effectiveness,
            "liquidity_state": self.liquidity_state,
            "volatility_effectiveness": self.volatility_effectiveness,
            "volatility_state": self.volatility_state,
            "session_effectiveness": self.session_effectiveness,
            "session_state": self.session_state,
            "global_structure_integrity": self.global_structure_integrity,
            "coherence_state": self.coherence_state,
        }


@dataclass
class ADIDelta:
    """Delta changes from previous snapshot."""
    spot_price: Optional[float] = None
    net_gex: Optional[float] = None
    zero_gamma: Optional[float] = None
    global_integrity: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "spot_price": self.spot_price,
            "net_gex": self.net_gex,
            "zero_gamma": self.zero_gamma,
            "global_integrity": self.global_integrity,
        }


@dataclass
class UserContext:
    """Optional user-specific context."""
    selected_tile: Optional[Dict[str, Any]] = None
    risk_graph_strategies: List[Dict[str, Any]] = field(default_factory=list)
    active_alerts: List[Dict[str, Any]] = field(default_factory=list)
    open_trades: List[Dict[str, Any]] = field(default_factory=list)
    active_log_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected_tile": self.selected_tile,
            "risk_graph_strategies": self.risk_graph_strategies,
            "active_alerts": self.active_alerts,
            "open_trades": self.open_trades,
            "active_log_id": self.active_log_id,
        }


@dataclass
class AIStructureSnapshot:
    """
    Complete AI Structure Snapshot - the canonical ADI output.

    This is the machine-readable market state that AI assistants consume.
    All fields are factual observations, not interpretations.
    """
    # Metadata
    timestamp_utc: datetime
    symbol: str
    session: str  # RTH/ETH/GLOBEX
    dte: Optional[int] = None
    event_flags: List[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION
    snapshot_id: str = field(default_factory=lambda: f"adi_{uuid.uuid4().hex[:12]}")

    # Market state sections
    price_state: PriceState = field(default_factory=PriceState)
    volatility_state: VolatilityState = field(default_factory=VolatilityState)
    gamma_structure: GammaStructure = field(default_factory=GammaStructure)
    auction_structure: AuctionStructure = field(default_factory=AuctionStructure)
    microstructure: Microstructure = field(default_factory=Microstructure)
    session_context: SessionContext = field(default_factory=SessionContext)

    # MEL scores
    mel_scores: MELScores = field(default_factory=MELScores)

    # Delta from previous
    delta: Optional[ADIDelta] = None

    # Optional user context
    user_context: Optional[UserContext] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON export."""
        return {
            "metadata": {
                "timestamp_utc": self.timestamp_utc.isoformat(),
                "symbol": self.symbol,
                "session": self.session,
                "dte": self.dte,
                "event_flags": self.event_flags,
                "schema_version": self.schema_version,
                "snapshot_id": self.snapshot_id,
            },
            "price_state": self.price_state.to_dict(),
            "volatility_state": self.volatility_state.to_dict(),
            "gamma_structure": self.gamma_structure.to_dict(),
            "auction_structure": self.auction_structure.to_dict(),
            "microstructure": self.microstructure.to_dict(),
            "session_context": self.session_context.to_dict(),
            "mel_scores": self.mel_scores.to_dict(),
            "delta": self.delta.to_dict() if self.delta else None,
            "user_context": self.user_context.to_dict() if self.user_context else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AIStructureSnapshot":
        """Deserialize from dictionary."""
        meta = data.get("metadata", {})

        return cls(
            timestamp_utc=datetime.fromisoformat(meta["timestamp_utc"]),
            symbol=meta["symbol"],
            session=meta["session"],
            dte=meta.get("dte"),
            event_flags=meta.get("event_flags", []),
            schema_version=meta.get("schema_version", SCHEMA_VERSION),
            snapshot_id=meta.get("snapshot_id", ""),
            price_state=PriceState(**data.get("price_state", {})),
            volatility_state=VolatilityState(**data.get("volatility_state", {})),
            gamma_structure=GammaStructure(**data.get("gamma_structure", {})),
            auction_structure=AuctionStructure(**data.get("auction_structure", {})),
            microstructure=Microstructure(**data.get("microstructure", {})),
            session_context=SessionContext(**data.get("session_context", {})),
            mel_scores=MELScores(**data.get("mel_scores", {})),
            delta=ADIDelta(**data["delta"]) if data.get("delta") else None,
            user_context=UserContext(**data["user_context"]) if data.get("user_context") else None,
        )


def generate_snapshot_id() -> str:
    """Generate unique snapshot ID."""
    return f"adi_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
