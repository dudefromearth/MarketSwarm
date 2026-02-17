"""
AFI (Antifragile Index) — Data Contracts
v1.0.0

Frozen dataclasses for AFI computation results.
All types are immutable after creation.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class TrendSignal(Enum):
    IMPROVING = "improving"
    STABLE = "stable"
    DECAYING = "decaying"


@dataclass(frozen=True)
class AFIComponents:
    """Normalized component scores (0-1 each) for hover breakdown."""
    r_slope: float
    ltc: float
    sharpe: float
    dd_containment: float

    def __post_init__(self):
        for field_name in ("r_slope", "sharpe", "ltc", "dd_containment"):
            v = getattr(self, field_name)
            if not isinstance(v, (int, float)) or math.isnan(v):
                raise ValueError(f"{field_name} must be a finite number, got {v}")


@dataclass(frozen=True)
class AFIResult:
    """Complete AFI computation output."""
    afi_score: float            # 300-900 soft-compressed (after RB dampening in v1, raw in v2)
    afi_raw: float              # before RB dampening
    wss: float                  # Weighted Structural Score (pre-compression)
    components: AFIComponents   # individual metric values (for hover tooltip)
    robustness: float           # RB score (0-100+)
    trend: TrendSignal          # recent WSS slope direction
    is_provisional: bool        # trade_count < 20 or active_days < 30
    trade_count: int
    active_days: int
    computed_at: datetime
    afi_version: int = 1        # 1 = recency-weighted + dampened, 2 = equal-weight + no dampening
