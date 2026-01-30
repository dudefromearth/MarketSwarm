"""
MEL Data Models - Model Effectiveness Layer

Defines the core data structures for tracking model validity and effectiveness.
Based on TraderDH's MEL specification.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Literal, Any
from datetime import datetime
from enum import Enum
import uuid


class ModelState(str, Enum):
    """Model trust state based on effectiveness score."""
    VALID = "VALID"        # >= 70% - Model reliable, safe to use
    DEGRADED = "DEGRADED"  # 50-69% - Model accuracy reduced, use with caution
    REVOKED = "REVOKED"    # < 50%  - Model unreliable, do not trust


class Trend(str, Enum):
    """Model effectiveness trend."""
    IMPROVING = "improving"
    STABLE = "stable"
    DEGRADING = "degrading"


class Confidence(str, Enum):
    """Confidence level in the effectiveness score."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CoherenceState(str, Enum):
    """Cross-model coherence state."""
    STABLE = "STABLE"         # Models generally agree, signals reinforce
    MIXED = "MIXED"           # Some disagreement, selective trust needed
    COLLAPSING = "COLLAPSING" # Models contradict, no clear signal
    RECOVERED = "RECOVERED"   # Previously collapsing, now stabilizing


class Session(str, Enum):
    """Market session identifier."""
    RTH = "RTH"       # Regular Trading Hours
    ETH = "ETH"       # Extended Trading Hours
    GLOBEX = "GLOBEX" # Overnight Globex


@dataclass
class MELModelScore:
    """
    Effectiveness score for a single market model.

    Represents how well a model (gamma, volume profile, etc.) is
    performing at describing/predicting market behavior.
    """
    effectiveness: float  # 0-100
    trend: Trend
    state: ModelState
    confidence: Confidence
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "effectiveness": self.effectiveness,
            "trend": self.trend.value,
            "state": self.state.value,
            "confidence": self.confidence.value,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MELModelScore":
        return cls(
            effectiveness=data["effectiveness"],
            trend=Trend(data["trend"]),
            state=ModelState(data["state"]),
            confidence=Confidence(data["confidence"]),
            detail=data.get("detail", {}),
        )


@dataclass
class MELDelta:
    """Delta from previous MEL snapshot for tracking changes."""
    gamma_effectiveness: float = 0.0
    volume_profile_effectiveness: float = 0.0
    liquidity_effectiveness: float = 0.0
    volatility_effectiveness: float = 0.0
    session_effectiveness: float = 0.0
    global_integrity: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "gamma_effectiveness": self.gamma_effectiveness,
            "volume_profile_effectiveness": self.volume_profile_effectiveness,
            "liquidity_effectiveness": self.liquidity_effectiveness,
            "volatility_effectiveness": self.volatility_effectiveness,
            "session_effectiveness": self.session_effectiveness,
            "global_integrity": self.global_integrity,
        }


@dataclass
class MELSnapshot:
    """
    Complete MEL snapshot representing model validity at a point in time.

    This is the primary output of the MEL calculation engine.
    """
    timestamp_utc: datetime
    snapshot_id: str
    session: Session
    event_flags: List[str]

    # Individual model scores
    gamma: MELModelScore
    volume_profile: MELModelScore
    liquidity: MELModelScore
    volatility: MELModelScore
    session_structure: MELModelScore

    # Cross-model analysis
    cross_model_coherence: float  # 0-100
    coherence_state: CoherenceState

    # Global composite
    global_structure_integrity: float  # 0-100

    # Change tracking
    delta: Optional[MELDelta] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp_utc": self.timestamp_utc.isoformat(),
            "snapshot_id": self.snapshot_id,
            "session": self.session.value,
            "event_flags": self.event_flags,
            "gamma": self.gamma.to_dict(),
            "volume_profile": self.volume_profile.to_dict(),
            "liquidity": self.liquidity.to_dict(),
            "volatility": self.volatility.to_dict(),
            "session_structure": self.session_structure.to_dict(),
            "cross_model_coherence": self.cross_model_coherence,
            "coherence_state": self.coherence_state.value,
            "global_structure_integrity": self.global_structure_integrity,
            "delta": self.delta.to_dict() if self.delta else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MELSnapshot":
        return cls(
            timestamp_utc=datetime.fromisoformat(data["timestamp_utc"]),
            snapshot_id=data["snapshot_id"],
            session=Session(data["session"]),
            event_flags=data["event_flags"],
            gamma=MELModelScore.from_dict(data["gamma"]),
            volume_profile=MELModelScore.from_dict(data["volume_profile"]),
            liquidity=MELModelScore.from_dict(data["liquidity"]),
            volatility=MELModelScore.from_dict(data["volatility"]),
            session_structure=MELModelScore.from_dict(data["session_structure"]),
            cross_model_coherence=data["cross_model_coherence"],
            coherence_state=CoherenceState(data["coherence_state"]),
            global_structure_integrity=data["global_structure_integrity"],
            delta=MELDelta(**data["delta"]) if data.get("delta") else None,
        )

    def get_state_summary(self) -> str:
        """Get a compact state summary string."""
        state_chars = {
            ModelState.VALID: "✓",
            ModelState.DEGRADED: "⚠",
            ModelState.REVOKED: "✗",
        }
        return (
            f"MEL:{self.global_structure_integrity:.0f}% | "
            f"Γ:{self.gamma.effectiveness:.0f}{state_chars[self.gamma.state]} | "
            f"VP:{self.volume_profile.effectiveness:.0f}{state_chars[self.volume_profile.state]} | "
            f"LIQ:{self.liquidity.effectiveness:.0f}{state_chars[self.liquidity.state]} | "
            f"VOL:{self.volatility.effectiveness:.0f}{state_chars[self.volatility.state]} | "
            f"SES:{self.session_structure.effectiveness:.0f}{state_chars[self.session_structure.state]}"
        )


@dataclass
class MELConfig:
    """Configuration for MEL calculation engine."""
    # Thresholds
    valid_threshold: float = 70.0
    degraded_threshold: float = 50.0

    # Global integrity weights
    weights: Dict[str, float] = field(default_factory=lambda: {
        "gamma": 0.30,
        "volume_profile": 0.25,
        "liquidity": 0.20,
        "volatility": 0.15,
        "session": 0.10,
    })

    # Coherence multipliers
    coherence_multipliers: Dict[str, float] = field(default_factory=lambda: {
        "STABLE": 1.0,
        "MIXED": 0.85,
        "COLLAPSING": 0.60,
        "RECOVERED": 0.90,
    })

    # Calculation settings
    snapshot_interval_ms: int = 5000
    history_retention_days: int = 365

    # Feature flags
    alert_on_revoked: bool = True
    visual_de_emphasis: bool = True


# ========== Event Flag Types ==========

class EventFlag:
    """Known event flags that can override model validity."""
    FOMC = "FOMC"
    CPI = "CPI"
    NFP = "NFP"
    PCE = "PCE"
    GDP = "GDP"
    EARNINGS = "EARNINGS"
    OPEX = "OPEX"
    GEOPOLITICAL = "GEOPOLITICAL"
    FLASH_CRASH = "FLASH_CRASH"

    @classmethod
    def all_scheduled(cls) -> List[str]:
        return [cls.FOMC, cls.CPI, cls.NFP, cls.PCE, cls.GDP, cls.EARNINGS, cls.OPEX]

    @classmethod
    def all_unscheduled(cls) -> List[str]:
        return [cls.GEOPOLITICAL, cls.FLASH_CRASH]


def generate_snapshot_id() -> str:
    """Generate a unique snapshot ID."""
    return f"mel_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
