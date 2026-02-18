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
    afi_version: int = 1        # 1 = recency-weighted + dampened, 2 = equal-weight, 3 = credibility-gated
    cps: float = 0.0            # v3: Convexity amplifier (1.0-1.25), 0 for v1/v2
    repeatability: float = 1.0  # v3: Repeatability multiplier (1.0-~1.15)
    capital_status: str = "unverified"   # v1.1: verified | unverified
    leaderboard_eligible: bool = False   # v1.1: capital-gated eligibility


@dataclass(frozen=True)
class AFIComponentsV4:
    """v4 normalized component scores (0-1 each)."""
    daily_sharpe: float         # normalized lifetime daily equity Sharpe
    drawdown_resilience: float  # normalized drawdown depth/recovery composite
    payoff_asymmetry: float     # normalized avg_win / avg_loss ratio
    recovery_velocity: float    # normalized speed from trough to new high

    def __post_init__(self):
        for field_name in ("daily_sharpe", "drawdown_resilience", "payoff_asymmetry", "recovery_velocity"):
            v = getattr(self, field_name)
            if not isinstance(v, (int, float)) or math.isnan(v):
                raise ValueError(f"{field_name} must be a finite number, got {v}")


@dataclass(frozen=True)
class AFIResultV4:
    """AFI v4 dual-index computation output."""
    afi_m: float                    # 300-900 momentum index (rolling daily Sharpe)
    afi_r: float                    # 300-900 robustness index (primary)
    composite: float                # 0.65 × AFI_R + 0.35 × AFI_M
    raw_afi_m: float                # pre-compression AFI-M (for tuning)
    raw_afi_r: float                # pre-compression AFI-R (for tuning)
    raw_sharpe_lifetime: float      # raw daily Sharpe before normalization
    components: AFIComponentsV4     # individual metric values
    confidence: float               # sqrt(N/(N+50)) × sqrt(D/(D+30))
    trend: TrendSignal              # recent WSS slope direction
    is_provisional: bool            # trade_count < 50 or active_days < 30
    trade_count: int
    active_days: int
    computed_at: datetime
    afi_version: int = 4
    capital_status: str = "unverified"
    leaderboard_eligible: bool = False
