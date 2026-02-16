# services/journal/intel/models_v2.py
"""Data models for the FOTW Trade Log system (v2)."""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List
import json
import uuid


@dataclass
class TradeLog:
    """A trade log container with immutable starting parameters.

    Lifecycle States:
    - active: Participates in daily workflow, alerts, ML
    - archived: Read-only, excluded from alerts/ML by default
    - retired: Frozen + hidden, preserved in cold storage
    """
    id: str
    name: str
    user_id: int  # Foreign key to users.id

    # Immutable Starting Parameters (frozen at creation)
    starting_capital: int  # cents
    risk_per_trade: Optional[int] = None  # cents (optional)
    max_position_size: Optional[int] = None  # optional constraint

    # Metadata
    intent: Optional[str] = None  # why this log exists
    description: Optional[str] = None  # human-readable purpose
    constraints: Optional[str] = None  # JSON: position limits, etc.
    regime_assumptions: Optional[str] = None  # market context
    notes: Optional[str] = None

    # Lifecycle State (replaces is_active)
    lifecycle_state: str = 'active'  # 'active', 'archived', 'retired'
    is_active: int = 1  # legacy field, derived from lifecycle_state
    archived_at: Optional[str] = None
    retired_at: Optional[str] = None
    retire_scheduled_at: Optional[str] = None  # 7-day grace period

    # ML/Alert inclusion (can override defaults for archived logs)
    ml_included: int = 1  # whether to include in ML training

    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def new_id() -> str:
        """Generate a new log ID."""
        return str(uuid.uuid4())

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        d = asdict(self)
        # Sync is_active with lifecycle_state for backwards compatibility
        d['is_active'] = 1 if self.lifecycle_state == 'active' else 0
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'TradeLog':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        # Handle datetime conversions
        for field_name in ['archived_at', 'retired_at', 'retire_scheduled_at', 'created_at', 'updated_at']:
            if isinstance(d.get(field_name), datetime):
                d[field_name] = d[field_name].isoformat()
        # Default lifecycle_state based on is_active if not present
        if 'lifecycle_state' not in d or d.get('lifecycle_state') is None:
            d['lifecycle_state'] = 'active' if d.get('is_active', 1) else 'archived'
        # Remove unknown fields
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        d = {k: v for k, v in d.items() if k in known_fields}
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format with dollars instead of cents."""
        d = self.to_dict()
        d['starting_capital_dollars'] = d['starting_capital'] / 100
        if d['risk_per_trade']:
            d['risk_per_trade_dollars'] = d['risk_per_trade'] / 100
        # Add computed fields
        d['is_read_only'] = self.lifecycle_state != 'active'
        d['can_receive_imports'] = self.lifecycle_state != 'retired'
        return d

    def can_archive(self) -> tuple[bool, Optional[str]]:
        """Check if this log can be archived. Returns (can_archive, reason)."""
        if self.lifecycle_state != 'active':
            return False, f"Log is already {self.lifecycle_state}"
        # Note: Caller must check for open positions and pending alerts
        return True, None

    def can_retire(self) -> tuple[bool, Optional[str]]:
        """Check if this log can be retired. Returns (can_retire, reason)."""
        if self.lifecycle_state == 'retired':
            return False, "Log is already retired"
        if self.lifecycle_state != 'archived':
            return False, "Log must be archived before retiring"
        return True, None


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
    entry_mode: str = "instant"  # instant/freeform/simulated
    immutable_at: Optional[str] = None  # Timestamp when sim trade became locked

    # Expiration lifecycle
    expiration_date: Optional[str] = None   # DATETIME in DB, ISO string in Python. UTC.
    auto_close_reason: Optional[str] = None # 'expiration' when auto-expired by sweeper

    # Metadata
    notes: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    source: str = "manual"  # manual/heatmap/risk_graph
    playbook_id: Optional[str] = None
    import_batch_id: Optional[str] = None

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
class TradeCorrection:
    """Auditable correction to a locked simulated trade."""
    id: int  # Auto-increment ID
    trade_id: str

    # What was corrected
    field_name: str
    original_value: Optional[str] = None
    corrected_value: str = ""
    correction_reason: str = ""

    # Audit trail
    corrected_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    corrected_by: Optional[int] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'TradeCorrection':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format."""
        return self.to_dict()


@dataclass
class Order:
    """A pending order in the order queue for simulated trading."""
    id: int  # Auto-increment ID
    user_id: int

    # Order details
    order_type: str  # entry/exit
    symbol: str
    direction: str  # long/short

    # Limit order parameters
    limit_price: float  # in dollars
    quantity: int = 1

    # Trade reference (for exit orders)
    trade_id: Optional[str] = None

    # Trade parameters (for entry orders)
    strategy: Optional[str] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    notes: Optional[str] = None

    # Order lifecycle
    status: str = "pending"  # pending/filled/cancelled/expired
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    expires_at: Optional[str] = None  # End of trading day if not set
    filled_at: Optional[str] = None
    filled_price: Optional[float] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'Order':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format."""
        return self.to_dict()


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


VALID_TAG_CATEGORIES = {'behavior', 'process', 'context', 'insight', 'state', 'strategy', 'custom'}
VALID_TAG_SCOPES = {'routine', 'journal', 'process', 'retro', 'strategy', 'global'}
DEFAULT_SCOPES_BY_CATEGORY = {
    'state': ['routine'],
    'behavior': ['journal', 'retro', 'process'],
    'process': ['journal', 'retro', 'process'],
    'context': ['journal', 'retro', 'strategy'],
    'insight': ['retro', 'journal'],
    'strategy': ['strategy'],
    'custom': ['journal'],
}


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
    category: str = 'custom'  # behavior, process, context, insight, state, strategy, custom
    group: Optional[str] = None      # 'sleep','focus','distractions','body','friction'
    system: bool = False              # system tags can't be deleted/renamed
    is_locked: bool = False           # locked tags can't be edited (name/category/scopes)
    visibility_scopes: List[str] = field(default_factory=lambda: ['journal'])
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
        d['system'] = 1 if d['system'] else 0
        d['is_locked'] = 1 if d['is_locked'] else 0
        d['visibility_scopes'] = json.dumps(d['visibility_scopes'])
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
        if 'system' in d:
            d['system'] = bool(d['system'])
        if 'is_locked' in d:
            d['is_locked'] = bool(d['is_locked'])
        # Parse visibility_scopes from JSON string
        scopes = d.get('visibility_scopes', '[]')
        if isinstance(scopes, str):
            try:
                d['visibility_scopes'] = json.loads(scopes)
            except (json.JSONDecodeError, TypeError):
                d['visibility_scopes'] = ['journal']
        # Default category to 'custom' for legacy NULL values
        if d.get('category') is None:
            d['category'] = 'custom'
        d.setdefault('category', 'custom')
        d.setdefault('group', None)
        d.setdefault('system', False)
        d.setdefault('is_locked', False)
        d.setdefault('visibility_scopes', ['journal'])
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format."""
        d = asdict(self)
        # Booleans stay as booleans for API
        return d


# ==================== Alert Models ====================

@dataclass
class Alert:
    """A server-side alert for awareness mechanisms.

    Alerts exist to protect attention, support routine, and surface moments
    worth noticing. They are NOT execution signals - they are awareness mechanisms.

    Intent Classes:
    - informational: "Something changed" (e.g., price crossed a level)
    - reflective: "Worth noticing" (e.g., trade closed, pattern recurrence)
    - protective: "Attention, not action" (e.g., risk envelope degraded)
    """
    id: str
    user_id: int

    # Core fields
    type: str  # price, debit, profit_target, trailing_stop, ai_theta_gamma, ai_sentiment, ai_risk_zone, time_boundary, trade_closed
    intent_class: str  # informational, reflective, protective
    condition: str  # above, below, at, outside_zone, inside_zone
    target_value: Optional[float] = None
    behavior: str = 'once_only'  # remove_on_hit, once_only, repeat
    priority: str = 'medium'  # low, medium, high, critical (internal only, no UX change)

    # Source reference
    source_type: str = 'symbol'  # strategy, symbol, portfolio
    source_id: str = ''  # strategy UUID or symbol like "I:SPX"

    # Strategy-specific (nullable)
    strategy_id: Optional[str] = None
    entry_debit: Optional[float] = None

    # AI-specific (nullable)
    min_profit_threshold: Optional[float] = None
    zone_low: Optional[float] = None
    zone_high: Optional[float] = None
    ai_confidence: Optional[float] = None
    ai_reasoning: Optional[str] = None

    # Trailing stop specific
    high_water_mark: Optional[float] = None

    # Butterfly entry detection
    entry_support_type: Optional[str] = None  # gex|hvn|poc|val|zero_gamma
    entry_support_level: Optional[float] = None
    entry_reversal_confirmed: bool = False
    entry_target_strike: Optional[float] = None
    entry_target_width: Optional[int] = None

    # Butterfly profit management
    mgmt_activation_threshold: Optional[float] = None  # default 0.75
    mgmt_high_water_mark: Optional[float] = None
    mgmt_initial_dte: Optional[int] = None
    mgmt_initial_gamma: Optional[float] = None
    mgmt_risk_score: Optional[float] = None
    mgmt_recommendation: Optional[str] = None  # HOLD|EXIT|TIGHTEN
    mgmt_last_assessment: Optional[str] = None

    # State
    enabled: bool = True
    triggered: bool = False
    trigger_count: int = 0
    triggered_at: Optional[str] = None

    # Display
    label: Optional[str] = None
    color: str = '#3b82f6'  # blue default

    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def new_id() -> str:
        """Generate a new alert ID."""
        return str(uuid.uuid4())

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        d = asdict(self)
        d['enabled'] = 1 if d['enabled'] else 0
        d['triggered'] = 1 if d['triggered'] else 0
        d['entry_reversal_confirmed'] = 1 if d['entry_reversal_confirmed'] else 0
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'Alert':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        # Handle MySQL integer booleans
        if 'enabled' in d:
            d['enabled'] = bool(d['enabled'])
        if 'triggered' in d:
            d['triggered'] = bool(d['triggered'])
        if 'entry_reversal_confirmed' in d:
            d['entry_reversal_confirmed'] = bool(d['entry_reversal_confirmed'])
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format with camelCase keys."""
        return {
            'id': self.id,
            'userId': self.user_id,
            'type': self.type,
            'intentClass': self.intent_class,
            'condition': self.condition,
            'targetValue': self.target_value,
            'behavior': self.behavior,
            'priority': self.priority,
            'sourceType': self.source_type,
            'sourceId': self.source_id,
            'strategyId': self.strategy_id,
            'entryDebit': self.entry_debit,
            'minProfitThreshold': self.min_profit_threshold,
            'zoneLow': self.zone_low,
            'zoneHigh': self.zone_high,
            'aiConfidence': self.ai_confidence,
            'aiReasoning': self.ai_reasoning,
            'highWaterMark': self.high_water_mark,
            # Butterfly entry detection
            'entrySupportType': self.entry_support_type,
            'entrySupportLevel': self.entry_support_level,
            'entryReversalConfirmed': self.entry_reversal_confirmed,
            'entryTargetStrike': self.entry_target_strike,
            'entryTargetWidth': self.entry_target_width,
            # Butterfly profit management
            'mgmtActivationThreshold': self.mgmt_activation_threshold,
            'mgmtHighWaterMark': self.mgmt_high_water_mark,
            'mgmtInitialDte': self.mgmt_initial_dte,
            'mgmtInitialGamma': self.mgmt_initial_gamma,
            'mgmtRiskScore': self.mgmt_risk_score,
            'mgmtRecommendation': self.mgmt_recommendation,
            'mgmtLastAssessment': self.mgmt_last_assessment,
            # State
            'enabled': self.enabled,
            'triggered': self.triggered,
            'triggerCount': self.trigger_count,
            'triggeredAt': self.triggered_at,
            'label': self.label,
            'color': self.color,
            'createdAt': self.created_at,
            'updatedAt': self.updated_at,
        }


# ==================== Prompt Alert Models ====================

@dataclass
class PromptAlert:
    """A prompt-driven strategy alert that uses natural language to define conditions.

    Prompt alerts let traders describe, in natural language, when a strategy stops
    behaving as designed. AI parses the prompt into semantic zones and evaluates
    against a captured reference state.

    Stages flow: watching -> update -> warn -> accomplished
    """
    id: str
    user_id: int
    strategy_id: str

    # Prompt content
    prompt_text: str
    prompt_version: int = 1

    # AI-parsed semantic zones (JSON strings)
    parsed_reference_logic: Optional[str] = None
    parsed_deviation_logic: Optional[str] = None
    parsed_evaluation_mode: Optional[str] = None  # regular, threshold, event
    parsed_stage_thresholds: Optional[str] = None

    # User declarations
    confidence_threshold: str = 'medium'  # high, medium, low

    # Orchestration
    orchestration_mode: str = 'parallel'  # parallel, overlapping, sequential
    orchestration_group_id: Optional[str] = None
    sequence_order: int = 0
    activates_after_alert_id: Optional[str] = None

    # State
    lifecycle_state: str = 'active'  # active, dormant, accomplished
    current_stage: str = 'watching'  # watching, update, warn, accomplished

    # Last evaluation
    last_ai_confidence: Optional[float] = None
    last_ai_reasoning: Optional[str] = None
    last_evaluation_at: Optional[str] = None

    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    activated_at: Optional[str] = None
    accomplished_at: Optional[str] = None

    @staticmethod
    def new_id() -> str:
        """Generate a new prompt alert ID."""
        return str(uuid.uuid4())

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'PromptAlert':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format with camelCase keys."""
        return {
            'id': self.id,
            'userId': self.user_id,
            'strategyId': self.strategy_id,
            'promptText': self.prompt_text,
            'promptVersion': self.prompt_version,
            'parsedReferenceLogic': json.loads(self.parsed_reference_logic) if self.parsed_reference_logic else None,
            'parsedDeviationLogic': json.loads(self.parsed_deviation_logic) if self.parsed_deviation_logic else None,
            'parsedEvaluationMode': self.parsed_evaluation_mode,
            'parsedStageThresholds': json.loads(self.parsed_stage_thresholds) if self.parsed_stage_thresholds else None,
            'confidenceThreshold': self.confidence_threshold,
            'orchestrationMode': self.orchestration_mode,
            'orchestrationGroupId': self.orchestration_group_id,
            'sequenceOrder': self.sequence_order,
            'activatesAfterAlertId': self.activates_after_alert_id,
            'lifecycleState': self.lifecycle_state,
            'currentStage': self.current_stage,
            'lastAiConfidence': self.last_ai_confidence,
            'lastAiReasoning': self.last_ai_reasoning,
            'lastEvaluationAt': self.last_evaluation_at,
            'createdAt': self.created_at,
            'updatedAt': self.updated_at,
            'activatedAt': self.activated_at,
            'accomplishedAt': self.accomplished_at,
        }


@dataclass
class PromptAlertVersion:
    """Version history for prompt alert edits (silent versioning)."""
    id: str
    prompt_alert_id: str
    version: int
    prompt_text: str
    parsed_zones: Optional[str] = None  # JSON snapshot of all parsed zones
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def new_id() -> str:
        """Generate a new version ID."""
        return str(uuid.uuid4())

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'PromptAlertVersion':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format."""
        return {
            'id': self.id,
            'promptAlertId': self.prompt_alert_id,
            'version': self.version,
            'promptText': self.prompt_text,
            'parsedZones': json.loads(self.parsed_zones) if self.parsed_zones else None,
            'createdAt': self.created_at,
        }


@dataclass
class ReferenceStateSnapshot:
    """A captured RiskGraph state at prompt alert creation or sequential activation.

    This snapshot serves as the baseline against which deviations are measured.
    """
    id: str
    prompt_alert_id: str

    # Greeks
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None

    # P&L
    expiration_breakevens: Optional[str] = None  # JSON array
    theoretical_breakevens: Optional[str] = None  # JSON array
    max_profit: Optional[float] = None
    max_loss: Optional[float] = None
    pnl_at_spot: Optional[float] = None

    # Market
    spot_price: Optional[float] = None
    vix: Optional[float] = None
    market_regime: Optional[str] = None

    # Strategy
    dte: Optional[int] = None
    debit: Optional[float] = None
    strike: Optional[float] = None
    width: Optional[int] = None
    side: Optional[str] = None

    captured_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def new_id() -> str:
        """Generate a new snapshot ID."""
        return str(uuid.uuid4())

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'ReferenceStateSnapshot':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format."""
        return {
            'id': self.id,
            'promptAlertId': self.prompt_alert_id,
            'delta': self.delta,
            'gamma': self.gamma,
            'theta': self.theta,
            'expirationBreakevens': json.loads(self.expiration_breakevens) if self.expiration_breakevens else None,
            'theoreticalBreakevens': json.loads(self.theoretical_breakevens) if self.theoretical_breakevens else None,
            'maxProfit': self.max_profit,
            'maxLoss': self.max_loss,
            'pnlAtSpot': self.pnl_at_spot,
            'spotPrice': self.spot_price,
            'vix': self.vix,
            'marketRegime': self.market_regime,
            'dte': self.dte,
            'debit': self.debit,
            'strike': self.strike,
            'width': self.width,
            'side': self.side,
            'capturedAt': self.captured_at,
        }


@dataclass
class PromptAlertTrigger:
    """Historical record of prompt alert stage transitions."""
    id: str
    prompt_alert_id: str
    version_at_trigger: int
    stage: str  # watching, update, warn, accomplished
    ai_confidence: Optional[float] = None
    ai_reasoning: Optional[str] = None
    market_snapshot: Optional[str] = None  # JSON snapshot of market state
    triggered_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def new_id() -> str:
        """Generate a new trigger ID."""
        return str(uuid.uuid4())

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'PromptAlertTrigger':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format."""
        return {
            'id': self.id,
            'promptAlertId': self.prompt_alert_id,
            'versionAtTrigger': self.version_at_trigger,
            'stage': self.stage,
            'aiConfidence': self.ai_confidence,
            'aiReasoning': self.ai_reasoning,
            'marketSnapshot': json.loads(self.market_snapshot) if self.market_snapshot else None,
            'triggeredAt': self.triggered_at,
        }


# =============================================================================
# Trade Idea Tracking Models (Feedback Optimization Loop)
# =============================================================================

@dataclass
class TrackedIdea:
    """A tracked trade idea for analytics and feedback optimization."""
    id: str

    # Entry Context
    symbol: str
    entry_rank: int
    entry_time: str
    entry_ts: int
    entry_spot: float
    entry_vix: float
    entry_regime: str

    # Trade Parameters (required)
    strategy: str
    side: str
    strike: float
    width: int
    dte: int
    debit: float
    max_profit_theoretical: float

    # Time Context (optional)
    entry_hour: Optional[float] = None  # Decimal hour (e.g., 14.5 = 2:30 PM)
    entry_day_of_week: Optional[int] = None  # 0=Monday, 4=Friday

    # GEX Context (optional)
    entry_gex_flip: Optional[float] = None  # Gamma flip level
    entry_gex_call_wall: Optional[float] = None  # Call wall / resistance
    entry_gex_put_wall: Optional[float] = None  # Put wall / support

    # Trade Parameters (optional)
    r2r_predicted: Optional[float] = None
    campaign: Optional[str] = None

    # Max Profit Tracking
    max_pnl: float = 0.0
    max_pnl_time: Optional[str] = None
    max_pnl_spot: Optional[float] = None
    max_pnl_dte: Optional[int] = None

    # Settlement
    settlement_time: Optional[str] = None
    settlement_spot: Optional[float] = None
    final_pnl: Optional[float] = None
    is_winner: Optional[bool] = None
    pnl_captured_pct: Optional[float] = None
    r2r_achieved: Optional[float] = None

    # Scoring Context (for feedback analysis)
    score_total: Optional[float] = None
    score_regime: Optional[float] = None
    score_r2r: Optional[float] = None
    score_convexity: Optional[float] = None
    score_campaign: Optional[float] = None
    score_decay: Optional[float] = None
    score_edge: Optional[float] = None

    # Parameter Version
    params_version: Optional[int] = None

    # Metadata
    edge_cases: Optional[str] = None  # JSON array
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        d = asdict(self)
        if d.get('is_winner') is not None:
            d['is_winner'] = 1 if d['is_winner'] else 0
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'TrackedIdea':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        if 'is_winner' in d and d['is_winner'] is not None:
            d['is_winner'] = bool(d['is_winner'])
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format."""
        return {
            'id': self.id,
            'symbol': self.symbol,
            'entryRank': self.entry_rank,
            'entryTime': self.entry_time,
            'entrySpot': self.entry_spot,
            'entryVix': self.entry_vix,
            'entryRegime': self.entry_regime,
            # Time context
            'entryHour': self.entry_hour,
            'entryDayOfWeek': self.entry_day_of_week,
            # GEX context
            'entryGexFlip': self.entry_gex_flip,
            'entryGexCallWall': self.entry_gex_call_wall,
            'entryGexPutWall': self.entry_gex_put_wall,
            # Trade params
            'strategy': self.strategy,
            'side': self.side,
            'strike': self.strike,
            'width': self.width,
            'dte': self.dte,
            'debit': self.debit,
            'maxProfitTheoretical': self.max_profit_theoretical,
            'r2rPredicted': self.r2r_predicted,
            'campaign': self.campaign,
            'maxPnl': self.max_pnl,
            'maxPnlTime': self.max_pnl_time,
            'maxPnlSpot': self.max_pnl_spot,
            'maxPnlDte': self.max_pnl_dte,
            'settlementTime': self.settlement_time,
            'settlementSpot': self.settlement_spot,
            'finalPnl': self.final_pnl,
            'isWinner': self.is_winner,
            'pnlCapturedPct': self.pnl_captured_pct,
            'r2rAchieved': self.r2r_achieved,
            'scores': {
                'total': self.score_total,
                'regime': self.score_regime,
                'r2r': self.score_r2r,
                'convexity': self.score_convexity,
                'campaign': self.score_campaign,
                'decay': self.score_decay,
                'edge': self.score_edge,
            },
            'paramsVersion': self.params_version,
            'edgeCases': json.loads(self.edge_cases) if self.edge_cases else [],
            'createdAt': self.created_at,
        }


@dataclass
class SelectorParams:
    """Versioned scoring parameters for the Trade Selector algorithm."""
    id: Optional[int] = None
    version: int = 1

    # Status
    status: str = 'draft'  # draft, active, testing, retired
    name: Optional[str] = None
    description: Optional[str] = None

    # Scoring Weights (JSON)
    weights: str = '{}'  # JSON object

    # Regime Thresholds (JSON)
    regime_thresholds: Optional[str] = None  # JSON object

    # Performance Metrics (updated by feedback loop)
    total_ideas: int = 0
    win_count: int = 0
    win_rate: Optional[float] = None
    avg_pnl: Optional[float] = None
    avg_capture_rate: Optional[float] = None

    # A/B Testing
    ab_test_group: Optional[str] = None
    ab_test_id: Optional[str] = None

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    activated_at: Optional[str] = None
    retired_at: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        d = asdict(self)
        # Remove id if None (for inserts)
        if d['id'] is None:
            del d['id']
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'SelectorParams':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        return cls(**d)

    def get_weights(self) -> dict:
        """Parse and return weights as dict."""
        return json.loads(self.weights) if self.weights else {}

    def get_regime_thresholds(self) -> dict:
        """Parse and return regime thresholds as dict."""
        return json.loads(self.regime_thresholds) if self.regime_thresholds else {}

    def to_api_dict(self) -> dict:
        """Convert to API response format."""
        return {
            'id': self.id,
            'version': self.version,
            'status': self.status,
            'name': self.name,
            'description': self.description,
            'weights': self.get_weights(),
            'regimeThresholds': self.get_regime_thresholds(),
            'performance': {
                'totalIdeas': self.total_ideas,
                'winCount': self.win_count,
                'winRate': self.win_rate,
                'avgPnl': self.avg_pnl,
                'avgCaptureRate': self.avg_capture_rate,
            },
            'abTest': {
                'group': self.ab_test_group,
                'id': self.ab_test_id,
            } if self.ab_test_id else None,
            'createdAt': self.created_at,
            'activatedAt': self.activated_at,
            'retiredAt': self.retired_at,
        }


# =============================================================================
# Risk Graph Service Models
# =============================================================================

@dataclass
class RiskGraphStrategy:
    """A risk graph strategy belonging to a user.

    Represents a single options strategy (single, vertical, or butterfly)
    being tracked on the risk graph for P&L analysis.
    """
    id: str
    user_id: int

    # Strategy geometry
    symbol: str = 'SPX'
    underlying: str = 'I:SPX'
    strategy: str = 'butterfly'  # single, vertical, butterfly
    side: str = 'call'  # call, put
    strike: float = 0.0
    width: Optional[int] = None
    dte: int = 0
    expiration: str = ''  # YYYY-MM-DD
    debit: Optional[float] = None

    # Display state
    visible: bool = True
    sort_order: int = 0
    color: Optional[str] = None
    label: Optional[str] = None

    # State
    added_at: int = 0  # Unix timestamp (ms)
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def new_id() -> str:
        """Generate a new strategy ID."""
        return str(uuid.uuid4())

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        d = asdict(self)
        d['visible'] = 1 if d['visible'] else 0
        d['is_active'] = 1 if d['is_active'] else 0
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'RiskGraphStrategy':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        if 'visible' in d:
            d['visible'] = bool(d['visible'])
        if 'is_active' in d:
            d['is_active'] = bool(d['is_active'])
        # Handle expiration as date or string
        if 'expiration' in d and d['expiration'] is not None:
            if hasattr(d['expiration'], 'isoformat'):
                d['expiration'] = d['expiration'].isoformat()
            else:
                d['expiration'] = str(d['expiration'])
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format with camelCase keys."""
        return {
            'id': self.id,
            'userId': self.user_id,
            'symbol': self.symbol,
            'underlying': self.underlying,
            'strategy': self.strategy,
            'side': self.side,
            'strike': self.strike,
            'width': self.width,
            'dte': self.dte,
            'expiration': self.expiration,
            'debit': self.debit,
            'visible': self.visible,
            'sortOrder': self.sort_order,
            'color': self.color,
            'label': self.label,
            'addedAt': self.added_at,
            'isActive': self.is_active,
            'createdAt': self.created_at,
            'updatedAt': self.updated_at,
        }


@dataclass
class RiskGraphStrategyVersion:
    """Version history for risk graph strategy changes (audit trail)."""
    id: Optional[int] = None
    strategy_id: str = ''
    version: int = 1
    debit: Optional[float] = None
    visible: bool = True
    label: Optional[str] = None
    change_type: str = 'created'  # created, debit_updated, visibility_toggled, edited, deleted
    change_reason: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        d = asdict(self)
        d['visible'] = 1 if d['visible'] else 0
        if d['id'] is None:
            del d['id']
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'RiskGraphStrategyVersion':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        if 'visible' in d:
            d['visible'] = bool(d['visible'])
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format."""
        return {
            'id': self.id,
            'strategyId': self.strategy_id,
            'version': self.version,
            'debit': self.debit,
            'visible': self.visible,
            'label': self.label,
            'changeType': self.change_type,
            'changeReason': self.change_reason,
            'createdAt': self.created_at,
        }


@dataclass
class RiskGraphTemplate:
    """A saved template for quickly adding strategies to the risk graph.

    Templates store relative positions (strike offset from ATM) rather than
    absolute strikes, making them reusable across different market conditions.
    """
    id: str
    user_id: int
    name: str
    description: Optional[str] = None

    # Template geometry (strike is relative to ATM)
    symbol: str = 'SPX'
    strategy: str = 'butterfly'  # single, vertical, butterfly
    side: str = 'call'  # call, put
    strike_offset: int = 0  # Offset from ATM (e.g., -10 = 10 points below)
    width: Optional[int] = None
    dte_target: int = 0  # Target DTE
    debit_estimate: Optional[float] = None

    # Sharing
    is_public: bool = False
    share_code: Optional[str] = None
    use_count: int = 0

    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def new_id() -> str:
        """Generate a new template ID."""
        return str(uuid.uuid4())

    @staticmethod
    def generate_share_code() -> str:
        """Generate a unique share code."""
        import secrets
        return secrets.token_urlsafe(12)[:16]

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        d = asdict(self)
        d['is_public'] = 1 if d['is_public'] else 0
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'RiskGraphTemplate':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        if 'is_public' in d:
            d['is_public'] = bool(d['is_public'])
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format with camelCase keys."""
        return {
            'id': self.id,
            'userId': self.user_id,
            'name': self.name,
            'description': self.description,
            'symbol': self.symbol,
            'strategy': self.strategy,
            'side': self.side,
            'strikeOffset': self.strike_offset,
            'width': self.width,
            'dteTarget': self.dte_target,
            'debitEstimate': self.debit_estimate,
            'isPublic': self.is_public,
            'shareCode': self.share_code,
            'useCount': self.use_count,
            'createdAt': self.created_at,
        }


# =============================================================================
# Import Batches - Reversible Import Provenance
# =============================================================================

@dataclass
class ImportBatch:
    """A transactional boundary for imported trades/positions.

    All imported entities carry a nullable import_batch_id that links
    to this table. Manual trades have import_batch_id = NULL.

    Reverting a batch soft-deletes all associated entities without
    affecting manual trades or user-created data.
    """
    id: str
    user_id: int

    # Source identification
    source: str  # 'broker_csv', 'tos_export', 'ml_backfill', 'simulator', 'custom'
    source_label: Optional[str] = None  # Human-readable label
    source_metadata: Optional[dict] = None  # File name, broker, date range, etc.

    # Counts (denormalized for fast display)
    trade_count: int = 0
    position_count: int = 0

    # Status
    status: str = 'active'  # 'active' or 'reverted'

    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    reverted_at: Optional[str] = None

    @staticmethod
    def new_id() -> str:
        """Generate a new batch ID."""
        return str(uuid.uuid4())

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'source': self.source,
            'source_label': self.source_label,
            'source_metadata': json.dumps(self.source_metadata) if self.source_metadata else None,
            'trade_count': self.trade_count,
            'position_count': self.position_count,
            'status': self.status,
            'created_at': self.created_at,
            'reverted_at': self.reverted_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'ImportBatch':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        # Parse JSON fields
        if isinstance(d.get('source_metadata'), str):
            d['source_metadata'] = json.loads(d['source_metadata']) if d['source_metadata'] else None
        # Convert datetime to ISO string
        if isinstance(d.get('created_at'), datetime):
            d['created_at'] = d['created_at'].isoformat()
        if isinstance(d.get('reverted_at'), datetime):
            d['reverted_at'] = d['reverted_at'].isoformat()
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format."""
        return {
            'id': self.id,
            'userId': self.user_id,
            'source': self.source,
            'sourceLabel': self.source_label,
            'sourceMetadata': self.source_metadata,
            'tradeCount': self.trade_count,
            'positionCount': self.position_count,
            'status': self.status,
            'createdAt': self.created_at,
            'revertedAt': self.reverted_at,
        }


# =============================================================================
# TradeLog Service Layer - Normalized Position Model
# =============================================================================

@dataclass
class Position:
    """A position aggregate - core entity for tracking trades.

    This replaces the flattened Trade model with a normalized structure
    that properly handles multi-leg strategies and multiple fills.
    """
    id: str
    user_id: int
    status: str  # 'planned', 'open', 'closed'
    symbol: str  # e.g., 'SPX'
    underlying: str  # e.g., 'I:SPX'
    version: int = 1

    opened_at: Optional[str] = None
    closed_at: Optional[str] = None
    tags: Optional[List[str]] = None
    campaign_id: Optional[str] = None

    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # Denormalized for convenience (not stored, joined in queries)
    legs: Optional[List['Leg']] = None
    fills: Optional[List['Fill']] = None

    @staticmethod
    def new_id() -> str:
        """Generate a new position ID."""
        return str(uuid.uuid4())

    def to_dict(self) -> dict:
        """Convert to dictionary for storage (excludes denormalized fields)."""
        d = {
            'id': self.id,
            'user_id': self.user_id,
            'status': self.status,
            'symbol': self.symbol,
            'underlying': self.underlying,
            'version': self.version,
            'opened_at': self.opened_at,
            'closed_at': self.closed_at,
            'tags': json.dumps(self.tags) if self.tags else None,
            'campaign_id': self.campaign_id,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'Position':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        # Parse JSON fields
        if isinstance(d.get('tags'), str):
            d['tags'] = json.loads(d['tags']) if d['tags'] else None
        # Convert datetime to ISO string
        if isinstance(d.get('opened_at'), datetime):
            d['opened_at'] = d['opened_at'].isoformat()
        if isinstance(d.get('closed_at'), datetime):
            d['closed_at'] = d['closed_at'].isoformat()
        if isinstance(d.get('created_at'), datetime):
            d['created_at'] = d['created_at'].isoformat()
        if isinstance(d.get('updated_at'), datetime):
            d['updated_at'] = d['updated_at'].isoformat()
        # Remove denormalized fields if present
        d.pop('legs', None)
        d.pop('fills', None)
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format with camelCase keys."""
        result = {
            'id': self.id,
            'userId': self.user_id,
            'status': self.status,
            'symbol': self.symbol,
            'underlying': self.underlying,
            'version': self.version,
            'openedAt': self.opened_at,
            'closedAt': self.closed_at,
            'tags': self.tags,
            'campaignId': self.campaign_id,
            'createdAt': self.created_at,
            'updatedAt': self.updated_at,
        }
        if self.legs is not None:
            result['legs'] = [leg.to_api_dict() for leg in self.legs]
        if self.fills is not None:
            result['fills'] = [fill.to_api_dict() for fill in self.fills]
        return result


@dataclass
class Leg:
    """An individual option/stock/future leg of a position."""
    id: str
    position_id: str
    instrument_type: str  # 'option', 'stock', 'future'
    expiry: Optional[str] = None  # Date string 'YYYY-MM-DD'
    strike: Optional[float] = None
    right: Optional[str] = None  # 'call', 'put'
    quantity: int = 0  # positive = long, negative = short

    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def new_id() -> str:
        """Generate a new leg ID."""
        return str(uuid.uuid4())

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            'id': self.id,
            'position_id': self.position_id,
            'instrument_type': self.instrument_type,
            'expiry': self.expiry,
            'strike': self.strike,
            'right': self.right,
            'quantity': self.quantity,
            'created_at': self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'Leg':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        # Convert date to string
        if isinstance(d.get('expiry'), datetime):
            d['expiry'] = d['expiry'].strftime('%Y-%m-%d')
        elif hasattr(d.get('expiry'), 'isoformat'):  # date object
            d['expiry'] = d['expiry'].isoformat()
        if isinstance(d.get('created_at'), datetime):
            d['created_at'] = d['created_at'].isoformat()
        if d.get('strike') is not None:
            d['strike'] = float(d['strike'])
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format with camelCase keys."""
        return {
            'id': self.id,
            'positionId': self.position_id,
            'instrumentType': self.instrument_type,
            'expiry': self.expiry,
            'strike': self.strike,
            'right': self.right,
            'quantity': self.quantity,
            'createdAt': self.created_at,
        }


@dataclass
class Fill:
    """A price/quantity execution record for a leg."""
    id: str
    leg_id: str
    price: float  # dollars (not cents)
    quantity: int
    occurred_at: str  # market reality - when it actually happened
    recorded_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())  # system reality

    @staticmethod
    def new_id() -> str:
        """Generate a new fill ID."""
        return str(uuid.uuid4())

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            'id': self.id,
            'leg_id': self.leg_id,
            'price': self.price,
            'quantity': self.quantity,
            'occurred_at': self.occurred_at,
            'recorded_at': self.recorded_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'Fill':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        if isinstance(d.get('occurred_at'), datetime):
            d['occurred_at'] = d['occurred_at'].isoformat()
        if isinstance(d.get('recorded_at'), datetime):
            d['recorded_at'] = d['recorded_at'].isoformat()
        if d.get('price') is not None:
            d['price'] = float(d['price'])
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format with camelCase keys."""
        return {
            'id': self.id,
            'legId': self.leg_id,
            'price': self.price,
            'quantity': self.quantity,
            'occurredAt': self.occurred_at,
            'recordedAt': self.recorded_at,
        }


@dataclass
class PositionEvent:
    """An event in the position event log for SSE replay."""
    id: Optional[int] = None  # Auto-increment
    event_id: str = ''
    event_seq: int = 0
    event_type: str = ''  # 'PositionCreated', 'FillRecorded', etc.
    aggregate_type: str = 'position'  # 'position' or 'order'
    aggregate_id: str = ''
    aggregate_version: int = 1
    user_id: int = 0
    payload: Optional[dict] = None
    occurred_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def new_event_id() -> str:
        """Generate a new event ID."""
        return str(uuid.uuid4())

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            'event_id': self.event_id,
            'event_seq': self.event_seq,
            'event_type': self.event_type,
            'aggregate_type': self.aggregate_type,
            'aggregate_id': self.aggregate_id,
            'aggregate_version': self.aggregate_version,
            'user_id': self.user_id,
            'payload': json.dumps(self.payload) if self.payload else '{}',
            'occurred_at': self.occurred_at,
            'created_at': self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'PositionEvent':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        if isinstance(d.get('payload'), str):
            d['payload'] = json.loads(d['payload']) if d['payload'] else {}
        if isinstance(d.get('occurred_at'), datetime):
            d['occurred_at'] = d['occurred_at'].isoformat()
        if isinstance(d.get('created_at'), datetime):
            d['created_at'] = d['created_at'].isoformat()
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format (SSE envelope)."""
        return {
            'event_id': self.event_id,
            'event_seq': self.event_seq,
            'type': self.event_type,
            'aggregate_type': self.aggregate_type,
            'aggregate_id': self.aggregate_id,
            'aggregate_version': self.aggregate_version,
            'occurred_at': self.occurred_at,
            'payload': self.payload,
        }


# =============================================================================
# ML Feedback Loop Models
# =============================================================================

@dataclass
class MLDecision:
    """An immutable decision record for ML scoring reproducibility.

    Every scoring decision is logged here to enable full reproducibility later.
    Given an ml_decisions.id, you can reconstruct exact feature values and model used.
    """
    id: Optional[int] = None  # Auto-increment
    idea_id: str = ''
    decision_time: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # Model identification (for exact reproducibility)
    model_id: Optional[int] = None
    model_version: Optional[int] = None
    selector_params_version: int = 1
    feature_snapshot_id: Optional[int] = None

    # Scores
    original_score: float = 0.0  # rule-based
    ml_score: Optional[float] = None  # ML contribution
    final_score: float = 0.0  # blended

    # Experiment tracking
    experiment_id: Optional[int] = None
    experiment_arm: Optional[str] = None  # 'champion' or 'challenger'

    # Action taken
    action_taken: str = 'ranked'  # ranked, presented, traded, dismissed

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        d = asdict(self)
        if d.get('id') is None:
            del d['id']
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'MLDecision':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        if isinstance(d.get('decision_time'), datetime):
            d['decision_time'] = d['decision_time'].isoformat()
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format."""
        return {
            'id': self.id,
            'ideaId': self.idea_id,
            'decisionTime': self.decision_time,
            'modelId': self.model_id,
            'modelVersion': self.model_version,
            'selectorParamsVersion': self.selector_params_version,
            'featureSnapshotId': self.feature_snapshot_id,
            'originalScore': self.original_score,
            'mlScore': self.ml_score,
            'finalScore': self.final_score,
            'experimentId': self.experiment_id,
            'experimentArm': self.experiment_arm,
            'actionTaken': self.action_taken,
        }


@dataclass
class PnLEvent:
    """An append-only P&L event for accurate path reconstruction.

    P&L deltas, not cumulative values, for precise equity curve computation.
    """
    id: Optional[int] = None  # Auto-increment
    event_time: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    idea_id: str = ''
    trade_id: Optional[str] = None
    strategy_id: Optional[str] = None

    # P&L delta (not cumulative)
    pnl_delta: float = 0.0
    fees: float = 0.0
    slippage: float = 0.0

    # Context
    underlying_price: float = 0.0
    event_type: str = 'mark'  # mark, fill, settlement, adjustment

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        d = asdict(self)
        if d.get('id') is None:
            del d['id']
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'PnLEvent':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        if isinstance(d.get('event_time'), datetime):
            d['event_time'] = d['event_time'].isoformat()
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format."""
        return {
            'id': self.id,
            'eventTime': self.event_time,
            'ideaId': self.idea_id,
            'tradeId': self.trade_id,
            'strategyId': self.strategy_id,
            'pnlDelta': self.pnl_delta,
            'fees': self.fees,
            'slippage': self.slippage,
            'underlyingPrice': self.underlying_price,
            'eventType': self.event_type,
        }


@dataclass
class DailyPerformance:
    """Materialized daily performance aggregation from pnl_events."""
    id: Optional[int] = None  # Auto-increment
    date: str = ''  # YYYY-MM-DD

    # P&L metrics
    net_pnl: float = 0.0
    gross_pnl: float = 0.0
    total_fees: float = 0.0

    # High water / drawdown
    high_water_pnl: float = 0.0
    max_drawdown: float = 0.0
    drawdown_pct: Optional[float] = None

    # Volume metrics
    trade_count: int = 0
    win_count: int = 0
    loss_count: int = 0

    # Model attribution
    primary_model_id: Optional[int] = None
    ml_contribution_pct: Optional[float] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        d = asdict(self)
        if d.get('id') is None:
            del d['id']
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'DailyPerformance':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        if hasattr(d.get('date'), 'isoformat'):
            d['date'] = d['date'].isoformat()
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format."""
        return {
            'id': self.id,
            'date': self.date,
            'netPnl': self.net_pnl,
            'grossPnl': self.gross_pnl,
            'totalFees': self.total_fees,
            'highWaterPnl': self.high_water_pnl,
            'maxDrawdown': self.max_drawdown,
            'drawdownPct': self.drawdown_pct,
            'tradeCount': self.trade_count,
            'winCount': self.win_count,
            'lossCount': self.loss_count,
            'primaryModelId': self.primary_model_id,
            'mlContributionPct': self.ml_contribution_pct,
        }


@dataclass
class MLFeatureSnapshot:
    """Feature snapshot at idea generation time for point-in-time correctness.

    Includes version tracking for all feature extractors to ensure reproducibility.
    """
    id: Optional[int] = None  # Auto-increment
    tracked_idea_id: int = 0
    snapshot_time: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # VERSIONING (critical for reproducibility)
    feature_set_version: str = 'v1.0'
    feature_extractor_version: str = 'v1.0'
    gex_calc_version: Optional[str] = None
    vix_regime_classifier_version: Optional[str] = None

    # Price Action Features
    spot_price: float = 0.0
    spot_5m_return: Optional[float] = None
    spot_15m_return: Optional[float] = None
    spot_1h_return: Optional[float] = None
    spot_1d_return: Optional[float] = None
    intraday_high: Optional[float] = None
    intraday_low: Optional[float] = None
    range_position: Optional[float] = None

    # Volatility Features
    vix_level: Optional[float] = None
    vix_regime: Optional[str] = None  # chaos, goldilocks_1, goldilocks_2, zombieland
    vix_term_slope: Optional[float] = None
    iv_rank_30d: Optional[float] = None
    iv_percentile_30d: Optional[float] = None

    # GEX Structure Features
    gex_total: Optional[float] = None
    gex_call_wall: Optional[float] = None
    gex_put_wall: Optional[float] = None
    gex_gamma_flip: Optional[float] = None
    spot_vs_call_wall: Optional[float] = None
    spot_vs_put_wall: Optional[float] = None
    spot_vs_gamma_flip: Optional[float] = None

    # Market Mode Features
    market_mode: Optional[str] = None
    bias_lfi: Optional[float] = None
    bias_direction: Optional[str] = None  # bullish, bearish, neutral

    # Time Features
    minutes_since_open: Optional[int] = None
    day_of_week: Optional[int] = None
    is_opex_week: bool = False
    days_to_monthly_opex: Optional[int] = None

    # Cross-Asset Signals
    es_futures_premium: Optional[float] = None
    tnx_level: Optional[float] = None
    dxy_level: Optional[float] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        d = asdict(self)
        if d.get('id') is None:
            del d['id']
        d['is_opex_week'] = 1 if d['is_opex_week'] else 0
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'MLFeatureSnapshot':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        if isinstance(d.get('snapshot_time'), datetime):
            d['snapshot_time'] = d['snapshot_time'].isoformat()
        if 'is_opex_week' in d:
            d['is_opex_week'] = bool(d['is_opex_week'])
        return cls(**d)

    def to_feature_dict(self) -> dict:
        """Convert to feature dictionary for ML inference."""
        return {
            'spot_price': self.spot_price,
            'spot_5m_return': self.spot_5m_return,
            'spot_15m_return': self.spot_15m_return,
            'spot_1h_return': self.spot_1h_return,
            'spot_1d_return': self.spot_1d_return,
            'range_position': self.range_position,
            'vix_level': self.vix_level,
            'vix_regime': self.vix_regime,
            'vix_term_slope': self.vix_term_slope,
            'iv_rank_30d': self.iv_rank_30d,
            'gex_total': self.gex_total,
            'spot_vs_call_wall': self.spot_vs_call_wall,
            'spot_vs_put_wall': self.spot_vs_put_wall,
            'spot_vs_gamma_flip': self.spot_vs_gamma_flip,
            'market_mode': self.market_mode,
            'bias_lfi': self.bias_lfi,
            'bias_direction': self.bias_direction,
            'minutes_since_open': self.minutes_since_open,
            'day_of_week': self.day_of_week,
            'is_opex_week': self.is_opex_week,
            'days_to_monthly_opex': self.days_to_monthly_opex,
        }


@dataclass
class TrackedIdeaSnapshot:
    """Event-based snapshot for tracked ideas.

    Snapshots are triggered by events (not time-based) to control volume.
    """
    id: Optional[int] = None  # Auto-increment
    tracked_idea_id: int = 0
    snapshot_time: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # Trigger reason
    trigger_type: str = 'periodic'  # fill, tier_boundary, stop_touch, target_touch, significant_move, periodic

    # Position state
    mark_price: float = 0.0
    underlying_price: float = 0.0
    unrealized_pnl: float = 0.0
    pnl_percent: float = 0.0

    # Greeks snapshot
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None

    # Market context at snapshot
    vix_level: Optional[float] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        d = asdict(self)
        if d.get('id') is None:
            del d['id']
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'TrackedIdeaSnapshot':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        if isinstance(d.get('snapshot_time'), datetime):
            d['snapshot_time'] = d['snapshot_time'].isoformat()
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format."""
        return {
            'id': self.id,
            'trackedIdeaId': self.tracked_idea_id,
            'snapshotTime': self.snapshot_time,
            'triggerType': self.trigger_type,
            'markPrice': self.mark_price,
            'underlyingPrice': self.underlying_price,
            'unrealizedPnl': self.unrealized_pnl,
            'pnlPercent': self.pnl_percent,
            'delta': self.delta,
            'gamma': self.gamma,
            'theta': self.theta,
            'vega': self.vega,
            'vixLevel': self.vix_level,
        }


@dataclass
class UserTradeAction:
    """User behavior tracking for trade ideas."""
    id: Optional[int] = None  # Auto-increment
    tracked_idea_id: int = 0
    user_id: int = 0
    action: str = 'viewed'  # viewed, dismissed, starred, traded, trade_closed
    action_time: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # Trade details if action = 'traded'
    fill_price: Optional[float] = None
    fill_quantity: Optional[int] = None
    trade_id: Optional[str] = None

    # Exit details if action = 'trade_closed'
    exit_price: Optional[float] = None
    realized_pnl: Optional[float] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        d = asdict(self)
        if d.get('id') is None:
            del d['id']
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'UserTradeAction':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        if isinstance(d.get('action_time'), datetime):
            d['action_time'] = d['action_time'].isoformat()
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format."""
        return {
            'id': self.id,
            'trackedIdeaId': self.tracked_idea_id,
            'userId': self.user_id,
            'action': self.action,
            'actionTime': self.action_time,
            'fillPrice': self.fill_price,
            'fillQuantity': self.fill_quantity,
            'tradeId': self.trade_id,
            'exitPrice': self.exit_price,
            'realizedPnl': self.realized_pnl,
        }


@dataclass
class MLModel:
    """A registered ML model with versioning and performance tracking."""
    id: Optional[int] = None  # Auto-increment
    model_name: str = ''
    model_version: int = 1
    model_type: str = ''  # gradient_boost, ensemble, etc.

    # Feature set version this model was trained on
    feature_set_version: str = 'v1.0'

    # Model artifacts
    model_blob: Optional[bytes] = None  # Serialized model (only loaded when needed)
    feature_list: Optional[List[str]] = None
    hyperparameters: Optional[dict] = None

    # Performance metrics
    train_auc: Optional[float] = None
    val_auc: Optional[float] = None
    train_samples: Optional[int] = None
    val_samples: Optional[int] = None

    # Calibration metrics
    brier_tier_0: Optional[float] = None
    brier_tier_1: Optional[float] = None
    brier_tier_2: Optional[float] = None
    brier_tier_3: Optional[float] = None

    # Top-k utility
    top_10_avg_pnl: Optional[float] = None
    top_20_avg_pnl: Optional[float] = None

    # Regime (optional - for regime-specific models)
    regime: Optional[str] = None

    # Deployment state
    status: str = 'training'  # training, validating, champion, challenger, retired
    deployed_at: Optional[str] = None
    retired_at: Optional[str] = None

    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        d = {
            'model_name': self.model_name,
            'model_version': self.model_version,
            'model_type': self.model_type,
            'feature_set_version': self.feature_set_version,
            'feature_list': json.dumps(self.feature_list) if self.feature_list else '[]',
            'hyperparameters': json.dumps(self.hyperparameters) if self.hyperparameters else '{}',
            'train_auc': self.train_auc,
            'val_auc': self.val_auc,
            'train_samples': self.train_samples,
            'val_samples': self.val_samples,
            'brier_tier_0': self.brier_tier_0,
            'brier_tier_1': self.brier_tier_1,
            'brier_tier_2': self.brier_tier_2,
            'brier_tier_3': self.brier_tier_3,
            'top_10_avg_pnl': self.top_10_avg_pnl,
            'top_20_avg_pnl': self.top_20_avg_pnl,
            'regime': self.regime,
            'status': self.status,
            'deployed_at': self.deployed_at,
            'retired_at': self.retired_at,
            'created_at': self.created_at,
        }
        if self.id is not None:
            d['id'] = self.id
        return d

    @classmethod
    def from_dict(cls, d: dict, include_blob: bool = False) -> 'MLModel':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        # Keep model_blob if requested, otherwise remove (too large for normal use)
        if not include_blob:
            d.pop('model_blob', None)
        if isinstance(d.get('feature_list'), str):
            d['feature_list'] = json.loads(d['feature_list']) if d['feature_list'] else []
        if isinstance(d.get('hyperparameters'), str):
            d['hyperparameters'] = json.loads(d['hyperparameters']) if d['hyperparameters'] else {}
        if isinstance(d.get('deployed_at'), datetime):
            d['deployed_at'] = d['deployed_at'].isoformat()
        if isinstance(d.get('retired_at'), datetime):
            d['retired_at'] = d['retired_at'].isoformat()
        if isinstance(d.get('created_at'), datetime):
            d['created_at'] = d['created_at'].isoformat()
        return cls(**d)

    def to_api_dict(self, include_blob: bool = False) -> dict:
        """Convert to API response format."""
        import base64

        result = {
            'id': self.id,
            'modelName': self.model_name,
            'modelVersion': self.model_version,
            'modelType': self.model_type,
            'featureSetVersion': self.feature_set_version,
            'featureList': self.feature_list,
            'hyperparameters': self.hyperparameters,
            'metrics': {
                'trainAuc': self.train_auc,
                'valAuc': self.val_auc,
                'trainSamples': self.train_samples,
                'valSamples': self.val_samples,
            },
            'calibration': {
                'brierTier0': self.brier_tier_0,
                'brierTier1': self.brier_tier_1,
                'brierTier2': self.brier_tier_2,
                'brierTier3': self.brier_tier_3,
            },
            'topKUtility': {
                'top10AvgPnl': self.top_10_avg_pnl,
                'top20AvgPnl': self.top_20_avg_pnl,
            },
            'regime': self.regime,
            'status': self.status,
            'deployedAt': self.deployed_at,
            'retiredAt': self.retired_at,
            'createdAt': self.created_at,
        }

        # Include model blob as base64 if requested and available
        if include_blob and self.model_blob:
            result['modelBlob'] = base64.b64encode(self.model_blob).decode('utf-8')

        return result


@dataclass
class MLExperiment:
    """An A/B experiment comparing champion vs challenger models."""
    id: Optional[int] = None  # Auto-increment
    experiment_name: str = ''
    description: Optional[str] = None

    champion_model_id: int = 0
    challenger_model_id: int = 0
    traffic_split: float = 0.10  # % to challenger

    # Stopping rules
    max_duration_days: int = 14
    min_samples_per_arm: int = 100
    early_stop_threshold: float = 0.01  # p-value for early stop

    # Experiment state
    status: str = 'running'  # running, concluded, aborted
    started_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    ended_at: Optional[str] = None

    # Results
    champion_samples: int = 0
    challenger_samples: int = 0
    champion_win_rate: Optional[float] = None
    challenger_win_rate: Optional[float] = None
    champion_avg_rar: Optional[float] = None  # Risk-adjusted return
    challenger_avg_rar: Optional[float] = None
    p_value: Optional[float] = None
    winner: Optional[str] = None  # champion, challenger, no_difference

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        d = asdict(self)
        if d.get('id') is None:
            del d['id']
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'MLExperiment':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        if isinstance(d.get('started_at'), datetime):
            d['started_at'] = d['started_at'].isoformat()
        if isinstance(d.get('ended_at'), datetime):
            d['ended_at'] = d['ended_at'].isoformat()
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format."""
        return {
            'id': self.id,
            'experimentName': self.experiment_name,
            'description': self.description,
            'championModelId': self.champion_model_id,
            'challengerModelId': self.challenger_model_id,
            'trafficSplit': self.traffic_split,
            'stoppingRules': {
                'maxDurationDays': self.max_duration_days,
                'minSamplesPerArm': self.min_samples_per_arm,
                'earlyStopThreshold': self.early_stop_threshold,
            },
            'status': self.status,
            'startedAt': self.started_at,
            'endedAt': self.ended_at,
            'results': {
                'championSamples': self.champion_samples,
                'challengerSamples': self.challenger_samples,
                'championWinRate': self.champion_win_rate,
                'challengerWinRate': self.challenger_win_rate,
                'championAvgRar': self.champion_avg_rar,
                'challengerAvgRar': self.challenger_avg_rar,
                'pValue': self.p_value,
                'winner': self.winner,
            },
        }


@dataclass
class PositionJournalEntry:
    """A journal entry tied to a position (TradeLog service layer)."""
    id: str
    position_id: str
    object_of_reflection: str  # required - what is being reflected upon
    bias_flags: Optional[List[str]] = None  # e.g., ['recency', 'confirmation']
    notes: Optional[str] = None
    phase: str = 'entry'  # setup, entry, management, exit, review
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def new_id() -> str:
        """Generate a new journal entry ID."""
        return str(uuid.uuid4())

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        d = asdict(self)
        d['bias_flags'] = json.dumps(d['bias_flags']) if d['bias_flags'] else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'PositionJournalEntry':
        """Create from dictionary (e.g., from database row)."""
        d = dict(d)
        if isinstance(d.get('bias_flags'), str):
            d['bias_flags'] = json.loads(d['bias_flags']) if d['bias_flags'] else None
        if isinstance(d.get('created_at'), datetime):
            d['created_at'] = d['created_at'].isoformat()
        return cls(**d)

    def to_api_dict(self) -> dict:
        """Convert to API response format."""
        return {
            'id': self.id,
            'positionId': self.position_id,
            'objectOfReflection': self.object_of_reflection,
            'biasFlags': self.bias_flags,
            'notes': self.notes,
            'phase': self.phase,
            'createdAt': self.created_at,
        }


# ==================== Edge Lab Models ====================


@dataclass
class EdgeLabSetup:
    """A structural setup record for Edge Lab retrospective analysis."""
    id: str
    user_id: int
    setup_date: str  # DATE as string
    regime: str  # e.g., 'trending', 'range_bound', 'volatile'
    gex_posture: str  # e.g., 'positive', 'negative', 'neutral'
    vol_state: str  # e.g., 'low', 'elevated', 'high', 'compressed'
    time_structure: str  # e.g., 'morning', 'midday', 'power_hour', 'close'
    heatmap_color: str  # e.g., 'green', 'red', 'yellow', 'mixed'
    position_structure: str  # e.g., 'long_fly', 'bwb', 'vertical', 'iron_condor'
    width_bucket: str  # 'narrow', 'standard', 'wide'
    directional_bias: str  # 'bullish', 'bearish', 'neutral'

    trade_id: Optional[str] = None
    position_id: Optional[str] = None
    entry_logic: Optional[str] = None
    exit_logic: Optional[str] = None
    entry_defined: int = 0
    exit_defined: int = 0
    structure_signature: Optional[str] = None
    bias_state_json: Optional[str] = None
    status: str = 'active'

    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())

    def compute_structure_signature(self) -> str:
        """Hash all 8 structural dimensions into a deterministic grouping key.

        Signature format: regime|gex_posture|vol_state|time_structure|heatmap_color|position_structure|width_bucket|directional_bias
        This prevents signatures from collapsing too broadly and enables
        meaningful Phase 2 clustering.
        """
        return '|'.join([
            self.regime or '',
            self.gex_posture or '',
            self.vol_state or '',
            self.time_structure or '',
            self.heatmap_color or '',
            self.position_structure or '',
            self.width_bucket or '',
            self.directional_bias or '',
        ])

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'user_id': self.user_id,
            'trade_id': self.trade_id,
            'position_id': self.position_id,
            'setup_date': self.setup_date,
            'regime': self.regime,
            'gex_posture': self.gex_posture,
            'vol_state': self.vol_state,
            'time_structure': self.time_structure,
            'heatmap_color': self.heatmap_color,
            'position_structure': self.position_structure,
            'width_bucket': self.width_bucket,
            'directional_bias': self.directional_bias,
            'entry_logic': self.entry_logic,
            'exit_logic': self.exit_logic,
            'entry_defined': self.entry_defined,
            'exit_defined': self.exit_defined,
            'structure_signature': self.structure_signature,
            'bias_state_json': self.bias_state_json,
            'status': self.status,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'EdgeLabSetup':
        d = dict(d)
        for f in ['setup_date']:
            if hasattr(d.get(f), 'isoformat'):
                d[f] = d[f].isoformat()
        for f in ['created_at', 'updated_at']:
            if isinstance(d.get(f), datetime):
                d[f] = d[f].isoformat()
        known = {f.name for f in cls.__dataclass_fields__.values()}
        d = {k: v for k, v in d.items() if k in known}
        return cls(**d)

    def to_api_dict(self) -> dict:
        return {
            'id': self.id,
            'userId': self.user_id,
            'tradeId': self.trade_id,
            'positionId': self.position_id,
            'setupDate': self.setup_date,
            'regime': self.regime,
            'gexPosture': self.gex_posture,
            'volState': self.vol_state,
            'timeStructure': self.time_structure,
            'heatmapColor': self.heatmap_color,
            'positionStructure': self.position_structure,
            'widthBucket': self.width_bucket,
            'directionalBias': self.directional_bias,
            'entryLogic': self.entry_logic,
            'exitLogic': self.exit_logic,
            'entryDefined': bool(self.entry_defined),
            'exitDefined': bool(self.exit_defined),
            'structureSignature': self.structure_signature,
            'biasState': json.loads(self.bias_state_json) if self.bias_state_json else None,
            'status': self.status,
            'createdAt': self.created_at,
            'updatedAt': self.updated_at,
        }


@dataclass
class EdgeLabHypothesis:
    """An immutable hypothesis record tied to a setup. Locked after trade entry."""
    id: str
    setup_id: str
    user_id: int
    thesis: str
    convexity_source: str
    failure_condition: str
    max_risk_defined: int = 0
    locked_at: Optional[str] = None
    is_locked: int = 0

    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())

    def lock(self):
        """Lock the hypothesis. Once locked, it cannot be modified."""
        if self.is_locked:
            raise ValueError("Hypothesis is already locked")
        self.is_locked = 1
        self.locked_at = datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'setup_id': self.setup_id,
            'user_id': self.user_id,
            'thesis': self.thesis,
            'convexity_source': self.convexity_source,
            'failure_condition': self.failure_condition,
            'max_risk_defined': self.max_risk_defined,
            'locked_at': self.locked_at,
            'is_locked': self.is_locked,
            'created_at': self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'EdgeLabHypothesis':
        d = dict(d)
        for f in ['locked_at', 'created_at']:
            if isinstance(d.get(f), datetime):
                d[f] = d[f].isoformat()
        known = {f.name for f in cls.__dataclass_fields__.values()}
        d = {k: v for k, v in d.items() if k in known}
        return cls(**d)

    def to_api_dict(self) -> dict:
        return {
            'id': self.id,
            'setupId': self.setup_id,
            'userId': self.user_id,
            'thesis': self.thesis,
            'convexitySource': self.convexity_source,
            'failureCondition': self.failure_condition,
            'maxRiskDefined': bool(self.max_risk_defined),
            'lockedAt': self.locked_at,
            'isLocked': bool(self.is_locked),
            'createdAt': self.created_at,
        }


@dataclass
class EdgeLabOutcome:
    """Outcome attribution record for a setup. Confirmed once, immutable after."""
    id: str
    setup_id: str
    user_id: int
    outcome_type: str  # structural_win, structural_loss, execution_error, bias_interference, regime_mismatch

    system_suggestion: Optional[str] = None
    suggestion_confidence: Optional[float] = None
    suggestion_reasoning: Optional[str] = None

    hypothesis_valid: Optional[int] = None
    structure_resolved: Optional[int] = None
    exit_per_plan: Optional[int] = None
    notes: Optional[str] = None
    # pnl_result is recorded for reference ONLY. It is NEVER used in
    # Edge Score computation, outcome classification, or any analytics formula.
    # This separation enforces process-quality measurement over profitability.
    pnl_result: Optional[float] = None

    confirmed_at: Optional[str] = None
    is_confirmed: int = 0

    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    VALID_OUTCOME_TYPES = (
        'structural_win', 'structural_loss', 'execution_error',
        'bias_interference', 'regime_mismatch',
    )

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())

    def confirm(self):
        """Confirm the outcome. Once confirmed, it cannot be modified."""
        if self.is_confirmed:
            raise ValueError("Outcome is already confirmed")
        self.is_confirmed = 1
        self.confirmed_at = datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'setup_id': self.setup_id,
            'user_id': self.user_id,
            'outcome_type': self.outcome_type,
            'system_suggestion': self.system_suggestion,
            'suggestion_confidence': self.suggestion_confidence,
            'suggestion_reasoning': self.suggestion_reasoning,
            'hypothesis_valid': self.hypothesis_valid,
            'structure_resolved': self.structure_resolved,
            'exit_per_plan': self.exit_per_plan,
            'notes': self.notes,
            'pnl_result': self.pnl_result,
            'confirmed_at': self.confirmed_at,
            'is_confirmed': self.is_confirmed,
            'created_at': self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'EdgeLabOutcome':
        d = dict(d)
        for f in ['confirmed_at', 'created_at']:
            if isinstance(d.get(f), datetime):
                d[f] = d[f].isoformat()
        if d.get('pnl_result') is not None:
            d['pnl_result'] = float(d['pnl_result'])
        if d.get('suggestion_confidence') is not None:
            d['suggestion_confidence'] = float(d['suggestion_confidence'])
        known = {f.name for f in cls.__dataclass_fields__.values()}
        d = {k: v for k, v in d.items() if k in known}
        return cls(**d)

    def to_api_dict(self) -> dict:
        return {
            'id': self.id,
            'setupId': self.setup_id,
            'userId': self.user_id,
            'outcomeType': self.outcome_type,
            'systemSuggestion': self.system_suggestion,
            'suggestionConfidence': self.suggestion_confidence,
            'suggestionReasoning': self.suggestion_reasoning,
            'hypothesisValid': self.hypothesis_valid,
            'structureResolved': self.structure_resolved,
            'exitPerPlan': self.exit_per_plan,
            'notes': self.notes,
            'pnlResult': self.pnl_result,
            'confirmedAt': self.confirmed_at,
            'isConfirmed': bool(self.is_confirmed),
            'createdAt': self.created_at,
        }


@dataclass
class EdgeLabEdgeScore:
    """Rolling window edge score snapshot."""
    id: Optional[int] = None  # AUTO_INCREMENT
    user_id: int = 0
    window_start: str = ''
    window_end: str = ''
    scope: str = 'all'

    structural_integrity: float = 0.0
    execution_discipline: float = 0.0
    bias_interference_rate: float = 0.0
    regime_alignment: float = 0.0
    final_score: float = 0.0
    sample_size: int = 0

    computed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # Minimum sample guard: never compute from noise
    MIN_SAMPLE_SIZE = 10

    @classmethod
    def compute(cls, structural_integrity: float, execution_discipline: float,
                bias_interference_rate: float, regime_alignment: float,
                sample_size: int, **kwargs) -> Optional['EdgeLabEdgeScore']:
        """Compute edge score from components.

        Formula: SI*0.35 + ED*0.30 - BI*0.15 + RA*0.20
        Returns None if sample_size < MIN_SAMPLE_SIZE (insufficient data).
        """
        if sample_size < cls.MIN_SAMPLE_SIZE:
            return None

        final = (
            structural_integrity * 0.35
            + execution_discipline * 0.30
            - bias_interference_rate * 0.15
            + regime_alignment * 0.20
        )
        return cls(
            structural_integrity=structural_integrity,
            execution_discipline=execution_discipline,
            bias_interference_rate=bias_interference_rate,
            regime_alignment=regime_alignment,
            final_score=round(final, 3),
            sample_size=sample_size,
            **kwargs,
        )

    def to_dict(self) -> dict:
        d = {
            'user_id': self.user_id,
            'window_start': self.window_start,
            'window_end': self.window_end,
            'scope': self.scope,
            'structural_integrity': self.structural_integrity,
            'execution_discipline': self.execution_discipline,
            'bias_interference_rate': self.bias_interference_rate,
            'regime_alignment': self.regime_alignment,
            'final_score': self.final_score,
            'sample_size': self.sample_size,
            'computed_at': self.computed_at,
        }
        if self.id is not None:
            d['id'] = self.id
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'EdgeLabEdgeScore':
        d = dict(d)
        for f in ['computed_at']:
            if isinstance(d.get(f), datetime):
                d[f] = d[f].isoformat()
        for f in ['window_start', 'window_end']:
            if hasattr(d.get(f), 'isoformat'):
                d[f] = d[f].isoformat()
        for f in ['structural_integrity', 'execution_discipline',
                   'bias_interference_rate', 'regime_alignment', 'final_score']:
            if d.get(f) is not None:
                d[f] = float(d[f])
        known = {f.name for f in cls.__dataclass_fields__.values()}
        d = {k: v for k, v in d.items() if k in known}
        return cls(**d)

    def to_api_dict(self) -> dict:
        return {
            'id': self.id,
            'userId': self.user_id,
            'windowStart': self.window_start,
            'windowEnd': self.window_end,
            'scope': self.scope,
            'structuralIntegrity': self.structural_integrity,
            'executionDiscipline': self.execution_discipline,
            'biasInterferenceRate': self.bias_interference_rate,
            'regimeAlignment': self.regime_alignment,
            'finalScore': self.final_score,
            'sampleSize': self.sample_size,
            'computedAt': self.computed_at,
        }


@dataclass
class EdgeLabMetric:
    """Thin container for precomputed metric JSON payloads."""
    id: Optional[int] = None  # AUTO_INCREMENT
    user_id: int = 0
    metric_type: str = ''
    scope: str = 'all'
    window_start: str = ''
    window_end: str = ''
    payload: Optional[str] = None  # JSON string
    sample_size: int = 0

    computed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        d = {
            'user_id': self.user_id,
            'metric_type': self.metric_type,
            'scope': self.scope,
            'window_start': self.window_start,
            'window_end': self.window_end,
            'payload': self.payload,
            'sample_size': self.sample_size,
            'computed_at': self.computed_at,
        }
        if self.id is not None:
            d['id'] = self.id
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'EdgeLabMetric':
        d = dict(d)
        for f in ['computed_at']:
            if isinstance(d.get(f), datetime):
                d[f] = d[f].isoformat()
        for f in ['window_start', 'window_end']:
            if hasattr(d.get(f), 'isoformat'):
                d[f] = d[f].isoformat()
        known = {f.name for f in cls.__dataclass_fields__.values()}
        d = {k: v for k, v in d.items() if k in known}
        return cls(**d)

    def to_api_dict(self) -> dict:
        return {
            'id': self.id,
            'userId': self.user_id,
            'metricType': self.metric_type,
            'scope': self.scope,
            'windowStart': self.window_start,
            'windowEnd': self.window_end,
            'payload': json.loads(self.payload) if self.payload else None,
            'sampleSize': self.sample_size,
            'computedAt': self.computed_at,
        }


def detect_signature_drift(user_id):
    """Reserved for Phase 2 — adaptive insight layer."""
    pass
