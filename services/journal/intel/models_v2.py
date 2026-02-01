# services/journal/intel/models_v2.py
"""Data models for the FOTW Trade Log system (v2)."""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List
import json
import uuid


@dataclass
class TradeLog:
    """A trade log container with immutable starting parameters."""
    id: str
    name: str
    user_id: int  # Foreign key to users.id

    # Immutable Starting Parameters (frozen at creation)
    starting_capital: int  # cents
    risk_per_trade: Optional[int] = None  # cents (optional)
    max_position_size: Optional[int] = None  # optional constraint

    # Metadata
    intent: Optional[str] = None  # why this log exists
    constraints: Optional[str] = None  # JSON: position limits, etc.
    regime_assumptions: Optional[str] = None  # market context
    notes: Optional[str] = None

    # Status
    is_active: int = 1  # soft delete

    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def new_id() -> str:
        """Generate a new log ID."""
        return str(uuid.uuid4())

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'TradeLog':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format with dollars instead of cents."""
        d = self.to_dict()
        d['starting_capital_dollars'] = d['starting_capital'] / 100
        if d['risk_per_trade']:
            d['risk_per_trade_dollars'] = d['risk_per_trade'] / 100
        return d


@dataclass
class Trade:
    """A single trade record belonging to a log."""
    id: str
    log_id: str

    # Strategy Reference (inherits geometry)
    symbol: str  # "SPX"
    underlying: str  # "I:SPX"
    strategy: str  # single/vertical/butterfly/iron_condor
    side: str  # call/put/both
    strike: float
    width: Optional[int] = None  # for spreads
    dte: Optional[int] = None
    quantity: int = 1

    # Entry (always present)
    entry_time: str = ""
    entry_price: int = 0  # cents
    entry_spot: Optional[float] = None
    entry_iv: Optional[float] = None

    # Exit (null until closed)
    exit_time: Optional[str] = None
    exit_price: Optional[int] = None  # cents
    exit_spot: Optional[float] = None

    # Risk Parameters
    planned_risk: Optional[int] = None  # cents (max loss)
    max_profit: Optional[int] = None  # cents (from tile)
    max_loss: Optional[int] = None  # cents (from tile)

    # Calculated (after close)
    pnl: Optional[int] = None  # cents
    r_multiple: Optional[float] = None  # pnl / planned_risk

    # State
    status: str = "open"  # open/closed

    # Metadata
    notes: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    source: str = "manual"  # manual/heatmap/risk_graph
    playbook_id: Optional[str] = None

    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def new_id() -> str:
        """Generate a new trade ID."""
        return str(uuid.uuid4())

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        d = asdict(self)
        d['tags'] = json.dumps(d['tags']) if d['tags'] else '[]'
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'Trade':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        if isinstance(d.get('tags'), str):
            d['tags'] = json.loads(d['tags']) if d['tags'] else []
        elif d.get('tags') is None:
            d['tags'] = []
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format with dollars."""
        d = asdict(self)
        d['entry_price_dollars'] = d['entry_price'] / 100 if d['entry_price'] else 0
        if d['exit_price']:
            d['exit_price_dollars'] = d['exit_price'] / 100
        if d['pnl'] is not None:
            d['pnl_dollars'] = d['pnl'] / 100
        if d['planned_risk']:
            d['planned_risk_dollars'] = d['planned_risk'] / 100
        if d['max_profit']:
            d['max_profit_dollars'] = d['max_profit'] / 100
        if d['max_loss']:
            d['max_loss_dollars'] = d['max_loss'] / 100
        return d

    def calculate_pnl(self) -> None:
        """Calculate P&L when trade is closed."""
        if self.exit_price is not None and self.entry_price is not None:
            # P&L = (exit - entry) * quantity (already in cents)
            self.pnl = (self.exit_price - self.entry_price) * self.quantity
            # Calculate R-multiple if planned_risk exists
            if self.planned_risk and self.planned_risk > 0:
                self.r_multiple = self.pnl / self.planned_risk


@dataclass
class TradeEvent:
    """A lifecycle event for a trade (open, adjust, close)."""
    id: str
    trade_id: str

    event_type: str  # open/adjust/close
    event_time: str

    # Event-specific data
    price: Optional[int] = None  # cents
    spot: Optional[float] = None
    quantity_change: Optional[int] = None  # +/- for adjustments
    notes: Optional[str] = None

    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def new_id() -> str:
        """Generate a new event ID."""
        return str(uuid.uuid4())

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'TradeEvent':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format."""
        d = self.to_dict()
        if d['price']:
            d['price_dollars'] = d['price'] / 100
        return d


@dataclass
class LogAnalytics:
    """Performance analytics for a trade log."""
    log_id: str
    log_name: str

    # Time & Scale
    span_days: int = 0
    total_trades: int = 0
    trades_per_week: float = 0.0

    # Capital & Returns
    starting_capital: int = 0  # cents
    current_equity: int = 0  # cents
    net_profit: int = 0  # cents
    total_return_percent: float = 0.0

    # Win/Loss Distribution
    open_trades: int = 0
    closed_trades: int = 0
    winners: int = 0
    losers: int = 0
    breakeven: int = 0
    win_rate: float = 0.0
    avg_win: int = 0  # cents
    avg_loss: int = 0  # cents
    win_loss_ratio: float = 0.0

    # Risk & Asymmetry
    avg_risk: int = 0  # cents
    largest_win: int = 0  # cents
    largest_loss: int = 0  # cents
    largest_win_pct_gross: float = 0.0
    largest_loss_pct_gross: float = 0.0

    # Gross P&L
    gross_profit: int = 0  # cents
    gross_loss: int = 0  # cents
    avg_net_profit: int = 0  # cents (net_profit / closed_trades)

    # System Health
    profit_factor: float = 0.0
    max_drawdown_pct: float = 0.0
    avg_r_multiple: float = 0.0
    avg_r2r: float = 0.0  # average reward-to-risk ratio
    sharpe_ratio: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    def to_api_dict(self) -> dict:
        """Convert to API response format with dollars."""
        d = self.to_dict()
        d['starting_capital_dollars'] = d['starting_capital'] / 100
        d['current_equity_dollars'] = d['current_equity'] / 100
        d['net_profit_dollars'] = d['net_profit'] / 100
        d['avg_win_dollars'] = d['avg_win'] / 100
        d['avg_loss_dollars'] = d['avg_loss'] / 100
        d['avg_risk_dollars'] = d['avg_risk'] / 100
        d['largest_win_dollars'] = d['largest_win'] / 100
        d['largest_loss_dollars'] = d['largest_loss'] / 100
        d['gross_profit_dollars'] = d['gross_profit'] / 100
        d['gross_loss_dollars'] = d['gross_loss'] / 100
        d['avg_net_profit_dollars'] = d['avg_net_profit'] / 100
        return d


@dataclass
class EquityPoint:
    """A single point on the equity curve."""
    time: str
    value: int  # cents
    trade_id: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DrawdownPoint:
    """A single point on the drawdown curve."""
    time: str
    drawdown_pct: float  # percentage from peak
    peak: int  # cents
    current: int  # cents

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Symbol:
    """A tradeable symbol with its multiplier/Big Point Value."""
    symbol: str  # Ticker symbol (SPX, ES, AAPL)
    name: str  # Full name (S&P 500 Index)
    asset_type: str  # index_option, future, stock, etf_option
    multiplier: int  # Contract multiplier / Big Point Value
    enabled: bool = True
    is_default: bool = False  # True for built-in symbols
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'Symbol':
        d = dict(d)
        # Handle SQLite integer booleans
        if 'enabled' in d:
            d['enabled'] = bool(d['enabled'])
        if 'is_default' in d:
            d['is_default'] = bool(d['is_default'])
        return cls(**d)


@dataclass
class Setting:
    """A configuration setting with category and scope."""
    key: str  # Setting key (e.g., 'default_risk_per_trade')
    value: str  # JSON-encoded value
    category: str  # symbols, user, ai, display, trading
    scope: str = 'global'  # global or log_id for per-log settings
    description: Optional[str] = None
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'Setting':
        d = dict(d)
        return cls(**d)

    def get_value(self):
        """Parse the JSON value."""
        try:
            return json.loads(self.value)
        except (json.JSONDecodeError, TypeError):
            return self.value

    def set_value(self, val):
        """Encode value as JSON."""
        self.value = json.dumps(val)


# ==================== Journal Models ====================

@dataclass
class JournalEntry:
    """A daily journal entry anchored to a calendar date."""
    id: str
    user_id: int
    entry_date: str  # YYYY-MM-DD (one entry per date)
    content: Optional[str] = None  # Rich text (HTML/Markdown)
    is_playbook_material: bool = False
    tags: List[str] = field(default_factory=list)  # List of tag IDs
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def new_id() -> str:
        """Generate a new entry ID."""
        return str(uuid.uuid4())

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        d = asdict(self)
        d['is_playbook_material'] = 1 if d['is_playbook_material'] else 0
        d['tags'] = json.dumps(d['tags']) if d['tags'] else '[]'
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'JournalEntry':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        if 'is_playbook_material' in d:
            d['is_playbook_material'] = bool(d['is_playbook_material'])
        if isinstance(d.get('tags'), str):
            d['tags'] = json.loads(d['tags']) if d['tags'] else []
        elif d.get('tags') is None:
            d['tags'] = []
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format."""
        return asdict(self)


@dataclass
class JournalRetrospective:
    """A weekly or monthly retrospective review."""
    id: str
    user_id: int
    retro_type: str  # 'weekly' | 'monthly'
    period_start: str  # YYYY-MM-DD
    period_end: str  # YYYY-MM-DD
    content: Optional[str] = None
    is_playbook_material: bool = False
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def new_id() -> str:
        """Generate a new retrospective ID."""
        return str(uuid.uuid4())

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        d = asdict(self)
        d['is_playbook_material'] = 1 if d['is_playbook_material'] else 0
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'JournalRetrospective':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        if 'is_playbook_material' in d:
            d['is_playbook_material'] = bool(d['is_playbook_material'])
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format."""
        return asdict(self)


@dataclass
class JournalTradeRef:
    """A reference linking a journal entry/retrospective to a trade."""
    id: str
    source_type: str  # 'entry' | 'retrospective'
    source_id: str  # FK to entries or retrospectives
    trade_id: str  # FK to trades
    note: Optional[str] = None  # Optional context for this reference
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def new_id() -> str:
        """Generate a new trade ref ID."""
        return str(uuid.uuid4())

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'JournalTradeRef':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format."""
        return asdict(self)


@dataclass
class JournalAttachment:
    """A file attachment for a journal entry or retrospective."""
    id: str
    source_type: str  # 'entry' | 'retrospective'
    source_id: str
    filename: str
    file_path: str  # Storage path
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def new_id() -> str:
        """Generate a new attachment ID."""
        return str(uuid.uuid4())

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'JournalAttachment':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format (excludes file_path for security)."""
        d = asdict(self)
        d.pop('file_path', None)  # Don't expose internal path
        return d


# ==================== Playbook Models ====================

@dataclass
class PlaybookEntry:
    """A distilled piece of trading wisdom in the Playbook."""
    id: str
    user_id: int
    
    # Core content
    title: str
    entry_type: str  # pattern, rule, warning, filter, constraint
    description: str
    
    # Status
    status: str = "draft"  # draft, active, retired
    
    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def new_id() -> str:
        """Generate a new playbook entry ID."""
        return str(uuid.uuid4())

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'PlaybookEntry':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format."""
        return asdict(self)


@dataclass
class PlaybookSourceRef:
    """A reference linking a Playbook entry to its source material."""
    id: str
    playbook_entry_id: str
    source_type: str  # 'entry' | 'retrospective' | 'trade'
    source_id: str
    note: Optional[str] = None  # Optional context about why this source matters
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def new_id() -> str:
        """Generate a new source ref ID."""
        return str(uuid.uuid4())

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'PlaybookSourceRef':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format."""
        return asdict(self)


@dataclass
class Tag:
    """A semantic tag representing trader vocabulary.

    Tags are personal markers that answer "Why did this matter to me?"
    They form the foundation layer for the Playbook system.
    """
    id: str
    user_id: int
    name: str  # Short, human-readable (e.g., "overtrading")
    description: Optional[str] = None  # What this tag means to the trader
    is_retired: bool = False  # Hidden from suggestions but preserved on history
    is_example: bool = False  # True for seeded example tags
    usage_count: int = 0  # Read-only, auto-incremented when tag is applied
    last_used_at: Optional[str] = None  # Auto-updated when tag is applied
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def new_id() -> str:
        """Generate a new tag ID."""
        return str(uuid.uuid4())

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        d = asdict(self)
        d['is_retired'] = 1 if d['is_retired'] else 0
        d['is_example'] = 1 if d['is_example'] else 0
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'Tag':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        # Handle MySQL integer booleans
        if 'is_retired' in d:
            d['is_retired'] = bool(d['is_retired'])
        if 'is_example' in d:
            d['is_example'] = bool(d['is_example'])
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format."""
        d = asdict(self)
        # Booleans stay as booleans for API
        return d
