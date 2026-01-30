"""
Commentary Data Models - AI Commentary System.

One-way contextual observations about market structure.
The AI observes and comments, users do not interact.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Literal
from datetime import datetime
from enum import Enum
import uuid


class CommentaryCategory(str, Enum):
    """Category of commentary."""
    OBSERVATION = "observation"      # Factual market observation
    DOCTRINE = "doctrine"            # FOTW doctrine reference
    MEL_WARNING = "mel_warning"      # MEL state change warning
    STRUCTURE_ALERT = "structure"    # Structure present/absent
    EVENT = "event"                  # Event flag triggered


class TriggerType(str, Enum):
    """Types of events that trigger commentary."""
    TILE_SELECTED = "tile_selected"
    SPOT_CROSSED_LEVEL = "spot_crossed_level"
    TRADE_OPENED = "trade_opened"
    TRADE_CLOSED = "trade_closed"
    ALERT_TRIGGERED = "alert_triggered"
    MEL_STATE_CHANGE = "mel_state_change"
    GLOBAL_INTEGRITY_WARNING = "global_integrity_warning"
    COHERENCE_CHANGE = "coherence_change"
    EVENT_FLAG = "event_flag"
    PERIODIC = "periodic"


@dataclass
class CommentaryTrigger:
    """A trigger event that may cause commentary."""
    type: TriggerType
    timestamp: datetime
    data: Dict[str, Any] = field(default_factory=dict)
    priority: int = 5  # 1-10, higher = more important

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "priority": self.priority,
        }


@dataclass
class CommentaryMessage:
    """A single commentary message."""
    id: str
    category: CommentaryCategory
    text: str
    timestamp: datetime
    trigger: Optional[CommentaryTrigger] = None
    mel_context: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category.value,
            "text": self.text,
            "timestamp": self.timestamp.isoformat(),
            "trigger": self.trigger.to_dict() if self.trigger else None,
            "mel_context": self.mel_context,
            "metadata": self.metadata,
        }

    @classmethod
    def create(
        cls,
        category: CommentaryCategory,
        text: str,
        trigger: Optional[CommentaryTrigger] = None,
        mel_context: Optional[Dict[str, Any]] = None,
        **metadata,
    ) -> "CommentaryMessage":
        return cls(
            id=f"cmt_{uuid.uuid4().hex[:12]}",
            category=category,
            text=text,
            timestamp=datetime.utcnow(),
            trigger=trigger,
            mel_context=mel_context,
            metadata=metadata,
        )


@dataclass
class CommentaryConfig:
    """Configuration for commentary service."""
    enabled: bool = True
    mode: Literal["one-way"] = "one-way"

    # AI provider settings
    provider: str = "openai"  # openai, grok, anthropic
    model: Optional[str] = None
    max_tokens: int = 256
    temperature: float = 0.7

    # Rate limiting
    rate_limit_per_minute: int = 10
    min_interval_seconds: float = 5.0

    # Trigger settings
    debounce_seconds: float = 2.0
    max_queue_size: int = 50

    # MEL integration
    warn_on_degraded: bool = True
    warn_on_revoked: bool = True
    require_valid_mel_for_guidance: bool = True


# ========== Trigger Definitions ==========

@dataclass
class TileSelectedTrigger(CommentaryTrigger):
    """Trigger when user selects a tile."""
    def __init__(self, tile_data: Dict[str, Any]):
        super().__init__(
            type=TriggerType.TILE_SELECTED,
            timestamp=datetime.utcnow(),
            data=tile_data,
            priority=3,
        )


@dataclass
class SpotCrossedLevelTrigger(CommentaryTrigger):
    """Trigger when spot crosses a significant level."""
    def __init__(self, level_type: str, level: float, direction: str, spot: float):
        super().__init__(
            type=TriggerType.SPOT_CROSSED_LEVEL,
            timestamp=datetime.utcnow(),
            data={
                "level_type": level_type,  # gamma, vah, val, poc, etc.
                "level": level,
                "direction": direction,  # above, below
                "spot": spot,
            },
            priority=6,
        )


@dataclass
class MELStateChangeTrigger(CommentaryTrigger):
    """Trigger when a MEL model changes state."""
    def __init__(self, model: str, from_state: str, to_state: str, score: float):
        super().__init__(
            type=TriggerType.MEL_STATE_CHANGE,
            timestamp=datetime.utcnow(),
            data={
                "model": model,
                "from_state": from_state,
                "to_state": to_state,
                "score": score,
            },
            priority=8 if to_state == "REVOKED" else 6,
        )


@dataclass
class GlobalIntegrityWarningTrigger(CommentaryTrigger):
    """Trigger when global integrity drops below threshold."""
    def __init__(self, score: float, threshold: float = 50.0):
        super().__init__(
            type=TriggerType.GLOBAL_INTEGRITY_WARNING,
            timestamp=datetime.utcnow(),
            data={
                "score": score,
                "threshold": threshold,
            },
            priority=9,
        )


@dataclass
class CoherenceChangeTrigger(CommentaryTrigger):
    """Trigger when cross-model coherence changes."""
    def __init__(self, from_state: str, to_state: str):
        super().__init__(
            type=TriggerType.COHERENCE_CHANGE,
            timestamp=datetime.utcnow(),
            data={
                "from_state": from_state,
                "to_state": to_state,
            },
            priority=7 if to_state == "COLLAPSING" else 5,
        )


@dataclass
class TradeEventTrigger(CommentaryTrigger):
    """Trigger when trade is opened or closed."""
    def __init__(self, event_type: str, trade_data: Dict[str, Any]):
        super().__init__(
            type=TriggerType.TRADE_OPENED if event_type == "opened" else TriggerType.TRADE_CLOSED,
            timestamp=datetime.utcnow(),
            data=trade_data,
            priority=4,
        )


def generate_message_id() -> str:
    """Generate unique message ID."""
    return f"cmt_{datetime.utcnow().strftime('%H%M%S')}_{uuid.uuid4().hex[:6]}"
