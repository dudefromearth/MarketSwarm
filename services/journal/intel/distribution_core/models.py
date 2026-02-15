"""
Distribution Core v1.0.0 — Data Models

Frozen data contracts for the single authoritative distribution metric engine.
All consumers (Edge Lab, SEE, ALE, AOL) must use these models.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

R_MULTIPLE_TOLERANCE = 1e-6


class StrategyCategory(Enum):
    """Frozen strategy categories. No free-form strings."""
    CONVEX_EXPANSION = "convex_expansion"
    EVENT_COMPRESSION = "event_compression"
    PREMIUM_COLLECTION = "premium_collection"


class RegimeBucket(Enum):
    """
    FOTW structural regime classification. Fixed VIX thresholds.

    Internal (4 structural regimes for precision):
        ZOMBIELAND    : VIX ≤ 17
        GOLDILOCKS_1  : 17 < VIX ≤ 24
        GOLDILOCKS_2  : 24 < VIX ≤ 32
        CHAOS         : VIX > 32

    External/UI aggregation (3 user-facing):
        Zombieland  = ZOMBIELAND
        Goldilocks  = GOLDILOCKS_1 + GOLDILOCKS_2
        Chaos       = CHAOS
    """
    ZOMBIELAND = "zombieland"
    GOLDILOCKS_1 = "goldilocks_1"
    GOLDILOCKS_2 = "goldilocks_2"
    CHAOS = "chaos"


class OutcomeType(Enum):
    """Frozen outcome types. Strongly typed."""
    STRUCTURAL_WIN = "structural_win"
    STRUCTURAL_LOSS = "structural_loss"
    EXECUTION_ERROR = "execution_error"
    BIAS_INTERFERENCE = "bias_interference"
    REGIME_MISMATCH = "regime_mismatch"


class SessionBucket(Enum):
    """
    Intraday session phase (Time axis of the 3D convexity model).

    Controls theta velocity, gamma acceleration, reflexivity windows.
    Classified at trade entry, never retroactive.

    Phase 0: Data capture only. 3D slicing comes in Phase 1.
    """
    MORNING = "morning"
    AFTERNOON = "afternoon"
    CLOSING = "closing"


class PriceZone(Enum):
    """
    Price position relative to convexity band (Price axis of 3D model).

    Determines convex payoff geometry, break probability, tail exposure.
    Classified at trade entry, never retroactive.

    Phase 0: Data capture only. 3D slicing comes in Phase 1.
    """
    BELOW_CONVEX_BAND = "below_convex_band"
    INSIDE_CONVEX_BAND = "inside_convex_band"
    ABOVE_CONVEX_BAND = "above_convex_band"


class RollingWindow(Enum):
    """Standardized rolling windows. No arbitrary ranges in Phase 0."""
    D7 = "7D"
    D30 = "30D"
    D90 = "90D"
    D180 = "180D"


@dataclass(frozen=True)
class TradeRecord:
    """
    Standardized trade input for Distribution Core.

    Each trade maps to a 3D convexity coordinate: (T, P, Γ)
        T = SessionBucket   (time axis — Phase 0: capture only)
        P = PriceZone       (price axis — Phase 0: capture only)
        Γ = RegimeBucket    (gamma/regime axis — Phase 0: active segmentation)

    R-multiple is the base unit. No raw PnL metrics allowed.
    All coordinates captured at entry, never retroactive.
    Validates data integrity on creation.
    """
    trade_id: str
    strategy_category: StrategyCategory
    structure_signature: str
    entry_timestamp: datetime
    exit_timestamp: datetime
    risk_unit: float
    pnl_realized: float
    r_multiple: float
    regime_bucket: RegimeBucket
    session_bucket: SessionBucket
    price_zone: PriceZone
    outcome_type: OutcomeType

    def __post_init__(self):
        if self.risk_unit <= 0:
            raise ValueError(
                f"risk_unit must be > 0, got {self.risk_unit} "
                f"(trade_id={self.trade_id})"
            )
        expected_r = self.pnl_realized / self.risk_unit
        if abs(self.r_multiple - expected_r) > R_MULTIPLE_TOLERANCE:
            raise ValueError(
                f"r_multiple mismatch: got {self.r_multiple}, "
                f"expected {expected_r:.6f} (pnl/risk = "
                f"{self.pnl_realized}/{self.risk_unit}) "
                f"(trade_id={self.trade_id})"
            )


@dataclass(frozen=True)
class DrawdownProfile:
    """
    Drawdown metrics computed from cumulative R equity curve.

    UCSP Foundation: These primitives expose the compounding stability
    surface. Drawdown elasticity (E > 1 when scaling) means position
    sizing amplifies drawdowns superlinearly. The fields below let
    governance systems detect instability before it compounds.
    """
    # Core depth metrics
    max_drawdown_depth: float
    average_drawdown_depth: float

    # Duration metrics (both axes: trades and calendar days)
    max_drawdown_duration_trades: int
    max_drawdown_duration_days: int
    average_drawdown_duration_trades: float
    average_drawdown_duration_days: float

    # Recovery metrics
    average_recovery_trades: float
    average_recovery_days: float

    # Volatility of drawdown depths (stability signal)
    drawdown_volatility: float

    # Series for downstream governance (UCSP primitives)
    drawdown_depths: tuple[float, ...]
    peak_equity_series: tuple[float, ...]


@dataclass(frozen=True)
class TailContribution:
    """Right and left tail contribution to total distribution."""
    right_tail_contribution: float
    left_tail_contribution: float


@dataclass(frozen=True)
class StrategyMixExposure:
    """Normalized exposure weights per strategy category. Sums to 1."""
    convex_expansion: float
    event_compression: float
    premium_collection: float


@dataclass(frozen=True)
class DistributionResult:
    """
    Complete distribution metric bundle.

    Every bundle includes version tag and generation timestamp.
    """
    version: str
    timestamp_generated: datetime
    window: str
    trade_count: int
    skew: Optional[float]
    ltc: Optional[float]
    rocpr: Optional[float]
    avg_winner: Optional[float]
    avg_loser: Optional[float]
    avg_w_avg_l_ratio: Optional[float]
    profit_factor: Optional[float]
    tail_contribution: Optional[TailContribution]
    drawdown: Optional[DrawdownProfile]
    strategy_mix: Optional[StrategyMixExposure]
    cii: Optional[float]
    excess_kurtosis: Optional[float]
    tail_ratio: Optional[float]


@dataclass(frozen=True)
class RegimeDistributionResult:
    """
    Distribution metrics segmented by structural regime bucket.

    Four internal regimes for precision.
    Consumers can aggregate goldilocks_1 + goldilocks_2 for UI display.
    """
    zombieland: Optional[DistributionResult]
    goldilocks_1: Optional[DistributionResult]
    goldilocks_2: Optional[DistributionResult]
    chaos: Optional[DistributionResult]


@dataclass(frozen=True)
class NormalizationBounds:
    """
    Frozen normalization bounds for v1.0.0.

    No dynamic scaling. Bounds are deterministic and versioned.
    Changes require version increment.
    """
    # Skew: maps [-1, +1] → [0, 1]
    skew_min: float = -1.0
    skew_max: float = 1.0
    # LTC: already 0-1 by definition, clamped for safety
    ltc_min: float = 0.0
    ltc_max: float = 1.0
    # ROCPR: cap at 200% return on risk
    rocpr_cap: float = 2.0
    # Drawdown volatility: cap at 1.0 R-units std dev
    drawdown_vol_cap: float = 1.0
