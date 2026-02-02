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
