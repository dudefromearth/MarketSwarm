# services/journal/intel/models.py
"""Data models for the journal service."""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List
import json
import uuid


@dataclass
class Trade:
    """A single trade record."""
    id: str
    user_id: str

    # Position details
    symbol: str
    underlying: str
    strategy: str  # single/vertical/butterfly
    side: str  # call/put
    dte: Optional[int]
    strike: float
    width: int
    quantity: int

    # Entry
    entry_time: str
    entry_price: float
    entry_spot: Optional[float]

    # Exit (nullable until closed)
    exit_time: Optional[str] = None
    exit_price: Optional[float] = None
    exit_spot: Optional[float] = None

    # Calculated
    pnl: Optional[float] = None
    pnl_percent: Optional[float] = None
    max_profit: Optional[float] = None
    max_loss: Optional[float] = None

    # Status
    status: str = "open"  # open/closed/expired

    # Metadata
    notes: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    playbook_id: Optional[str] = None
    source: str = "manual"  # manual/heatmap

    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def new_id() -> str:
        """Generate a new trade ID."""
        return str(uuid.uuid4())

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        d = asdict(self)
        d['tags'] = json.dumps(d['tags']) if d['tags'] else '[]'
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'Trade':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)  # Copy to avoid mutating original
        if isinstance(d.get('tags'), str):
            d['tags'] = json.loads(d['tags']) if d['tags'] else []
        elif d.get('tags') is None:
            d['tags'] = []
        return cls(**d)

    def calculate_pnl(self) -> None:
        """Calculate P&L when trade is closed."""
        if self.exit_price is not None and self.entry_price is not None:
            # P&L per contract = (exit - entry) * 100
            self.pnl = (self.exit_price - self.entry_price) * 100 * self.quantity
            if self.entry_price > 0:
                self.pnl_percent = ((self.exit_price - self.entry_price) / self.entry_price) * 100


@dataclass
class AnalyticsSummary:
    """Performance analytics summary."""
    total_trades: int = 0
    open_trades: int = 0
    closed_trades: int = 0

    winners: int = 0
    losers: int = 0
    breakeven: int = 0

    total_pnl: float = 0.0
    total_pnl_percent: float = 0.0

    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0

    largest_win: float = 0.0
    largest_loss: float = 0.0
    avg_trade: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class EquityPoint:
    """A single point on the equity curve."""
    time: str
    value: float
    trade_id: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)
