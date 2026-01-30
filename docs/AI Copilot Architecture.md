# MarketSwarm AI Copilot — Technical Architecture

## Overview

A **one-way contextual commentary system** deeply integrated with MarketSwarm. The Copilot provides real-time observations, FOTW doctrine context, and market insights without interactive prompting — similar to Vexy Play-by-Play.

**Key Design Principle**: The in-app AI is one-way. Two-way interactive AI is available through:
- Personal Vexy (more capable, knows the user personally)
- Top-tier FOTW membership (covers API costs)

---

## The Two-Interface Architecture

> *"Screens are for humans. Data is for machines."*
> — TraderDH, ADI Specification

Modern AI makes traditional user interfaces largely irrelevant *for machines*. When designing contemporary analytical systems — especially in markets — a single interface is no longer sufficient.

**Two interfaces are required:**

### Human Interface (HI)

Optimized for:
- Speed
- Visual clarity
- Pattern recognition
- Situational awareness

Examples:
- Gamma heatmaps
- Volume profiles
- Interactive dashboards
- Visual widgets and gauges

### AI Interface (ADI)

Optimized for:
- Precision
- Completeness
- Explicit semantics
- Zero ambiguity

Characteristics:
- No graphics
- No inference required
- One value per concept
- Canonical field names
- Versioned schemas

**The Problem with Screenshots**: OCR-based workflows introduce numeric errors, missing values, misread symbols, and silent data loss. When AI encounters incomplete or ambiguous data, it fills in gaps via inference, producing hallucinations. This is not an AI failure — it is an interface failure.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            MarketSwarm UI                                    │
│  ┌──────────────────────────────────────┐  ┌──────────────────────────────┐ │
│  │           Main Workspace              │  │      AI Commentary Panel     │ │
│  │  ┌─────────┐ ┌─────────┐ ┌────────┐  │  │  ┌────────────────────────┐  │ │
│  │  │ Heatmap │ │   GEX   │ │  Risk  │  │  │  │   Observation Feed     │  │ │
│  │  │         │ │         │ │ Graph  │  │  │  │      (one-way)         │  │ │
│  │  └─────────┘ └─────────┘ └────────┘  │  │  └────────────────────────┘  │ │
│  │  ┌─────────────────────────────────┐ │  │  ┌────────────────────────┐  │ │
│  │  │         Trade Log               │ │  │  │ [Download AI Snapshot] │  │ │
│  │  └─────────────────────────────────┘ │  │  │ [Copy to Vexy]         │  │ │
│  └──────────────────────────────────────┘  │  └────────────────────────┘  │ │
└─────────────────────────────────────────────────────────────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                              ▼
┌───────────────────────────────────┐  ┌──────────────────────────────────────┐
│       Context Monitor              │  │    AI Data Interface (ADI)           │
│  Watches for significant changes:  │  │                                      │
│  - Tile selection changed          │  │  One-button export of canonical      │
│  - Spot price crossed key level    │  │  market structure data:              │
│  - Trade opened/closed             │  │  - Raw data, not widgets             │
│  - Alert triggered                 │  │  - Explicit semantics                │
│  - Regime shift detected           │  │  - Versioned schema                  │
└───────────────────────────────────┘  │  - CSV / JSON formats                │
                    │                   └──────────────────────────────────────┘
                    ▼                              │
┌───────────────────────────────────┐              │
│      Commentary Service            │              │
│  - Claude API integration          │◀─────────────┘
│  - Knowledge base                  │   ADI provides factual context
│  - Rate limiting                   │   for commentary generation
└───────────────────────────────────┘
```

---

## AI Data Interface (ADI) — Canonical Specification

The AI Data Interface is a first-class, machine-readable interface for analytical systems, separate from the human UI. ADI ensures that AI systems — local models, agents, copilots, and automated workflows — can ingest canonical market structure data directly, without relying on screenshots, OCR, or visual inference.

**ADI does not replace the human interface. It complements it.**

### Core Principles

1. **Raw Data, Not Widgets**: Export the data that *makes* the widgets, not screenshots of widgets
2. **One-Button Snapshot**: Single action to export complete state
3. **Explicit Semantics**: Every field has a canonical name and definition
4. **Versioned Schema**: Schema version tracks breaking changes
5. **No Inference Required**: AI should never have to guess

### ADI Schema (v1.0)

```typescript
interface AIStructureSnapshot {
  // === METADATA ===
  metadata: {
    timestamp_utc: string;        // "2026-01-29T21:05:00Z"
    symbol: string;               // "SPX"
    session: 'RTH' | 'ETH' | 'GLOBEX';
    dte: number;                  // 0
    event_flags: string[];        // ["FOMC", "OPEX"]
    schema_version: string;       // "gamma_snapshot_v1.0"
    snapshot_id: string;          // "2026-01-29T21:05:00Z_0042"
  };

  // === PRICE & MARKET STATE ===
  price_state: {
    spot_price: number;           // 6928.26
    session_high: number;         // 6954.75
    session_low: number;          // 6902.50
    vwap: number;                 // 6931.40
    distance_from_vwap: number;   // -3.14
    intraday_range: number;       // 52.25
    realized_vol_intra: number;   // 0.312
  };

  // === VOLATILITY STATE ===
  volatility_state: {
    call_iv_atm: number;          // 0.177
    put_iv_atm: number;           // 0.271
    iv_skew: number;              // 0.094
    iv_rv_ratio: number;          // 0.87
    vol_regime: 'EXPANSION' | 'CONTRACTION' | 'NEUTRAL';
  };

  // === OPTIONS & GAMMA STRUCTURE ===
  gamma_structure: {
    call_open_interest: number;   // 104614050
    call_oi_delta: number;        // +189
    put_open_interest: number;    // 119429300
    put_oi_delta: number;         // +402
    net_gex: number;              // -14815240
    positive_gex: number;         // +1044684
    negative_gex: number;         // -15859924
    gex_ratio: number;            // 0.01
    flow_ratio: number;           // 0.50
    zero_gamma_level: number;     // 6947.01
    active_gamma_magnet: number;  // 6933.77
    gamma_wall_above: number;     // 6980.00
    gamma_wall_below: number;     // 6900.00
    distance_to_zero_g: number;   // -18.75
    distance_to_magnet: number;   // -5.51
  };

  // === VOLUME PROFILE / AUCTION STRUCTURE ===
  auction_structure: {
    poc: number;                  // 6932.50
    value_area_high: number;      // 6954.25
    value_area_low: number;       // 6908.75
    highest_vol_node: number;     // 6932.50
    lowest_vol_node: number;      // 6968.00
    price_location: 'INSIDE_VALUE' | 'ABOVE_VALUE' | 'BELOW_VALUE';
    balance_range_size: number;   // 45.50
    rotation_state: 'CONSISTENT' | 'INCONSISTENT' | 'REVERSAL';
    auction_state: 'BALANCE' | 'PARTIAL_BALANCE' | 'IMBALANCE' | 'TREND';
  };

  // === LIQUIDITY / MICROSTRUCTURE ===
  microstructure: {
    bid_ask_imbalance: number;    // 0.42
    aggressive_flow: 'BUY_DOMINANT' | 'SELL_DOMINANT' | 'NEUTRAL';
    absorption_detected: boolean; // false
    sweep_activity: boolean;      // true
    liquidity_vacuum: 'NONE' | 'INTERMITTENT' | 'SEVERE';
    spread_state: 'TIGHT' | 'NORMAL' | 'WIDENING' | 'WIDE';
  };

  // === TIME-OF-DAY CONTEXT ===
  session_context: {
    minutes_since_open: number;   // 215
    minutes_to_close: number;     // 85
    session_phase: 'EARLY' | 'MIDDAY' | 'LATE' | 'CLOSE';
    known_liq_window: string | null;  // "MOC" | "VWAP_CLOSE" | null
  };

  // === MODEL EFFECTIVENESS LAYER (MEL) ===
  mel_scores: {
    gamma_effectiveness: number;          // 0.82
    gamma_state: 'VALID' | 'DEGRADED' | 'REVOKED';
    volume_profile_effectiveness: number; // 0.61
    volume_profile_state: 'VALID' | 'DEGRADED' | 'REVOKED';
    liquidity_effectiveness: number;      // 0.35
    liquidity_state: 'VALID' | 'DEGRADED' | 'REVOKED';
    volatility_effectiveness: number;     // 0.28
    volatility_state: 'VALID' | 'DEGRADED' | 'REVOKED';
    session_structure: number;            // 0.57
    session_state: 'VALID' | 'MIXED' | 'DEGRADED';
    cross_model_coherence: number;        // 0.33
    coherence_state: 'STABLE' | 'COLLAPSING' | 'RECOVERED';
    global_structure_integrity: number;   // 0.42
  };

  // === DELTA SINCE LAST SNAPSHOT ===
  delta: {
    spot_price: number;           // -12.75
    net_gex: number;              // -1240000
    zero_gamma: number;           // -4.25
    active_magnet: number;        // -2.00
    poc: number | 'UNCHANGED';    // "UNCHANGED"
    global_integrity: number;     // -0.09
  };

  // === USER CONTEXT (MarketSwarm specific) ===
  user_context?: {
    selected_tile?: {
      strategy: string;
      strike: number;
      width?: number;
      side: string;
      dte: number;
      debit: number;
      max_profit: number;
      r2r: number;
    };
    risk_graph_strategies: number;
    active_alerts: number;
    open_trades: number;
    active_log?: {
      id: string;
      name: string;
      starting_capital: number;
      current_equity?: number;
    };
  };
}
```

### ADI Export Formats

#### 1. JSON (Primary — for AI parsing)

```json
{
  "metadata": {
    "timestamp_utc": "2026-01-29T21:05:00Z",
    "symbol": "SPX",
    "session": "RTH",
    "dte": 0,
    "event_flags": ["FOMC"],
    "schema_version": "gamma_snapshot_v1.0",
    "snapshot_id": "2026-01-29T21:05:00Z_0042"
  },
  "price_state": {
    "spot_price": 6928.26,
    "session_high": 6954.75,
    "session_low": 6902.50,
    "vwap": 6931.40,
    "distance_from_vwap": -3.14,
    "intraday_range": 52.25,
    "realized_vol_intra": 0.312
  },
  "volatility_state": {
    "call_iv_atm": 0.177,
    "put_iv_atm": 0.271,
    "iv_skew": 0.094,
    "iv_rv_ratio": 0.87,
    "vol_regime": "EXPANSION"
  },
  "gamma_structure": {
    "net_gex": -14815240,
    "zero_gamma_level": 6947.01,
    "active_gamma_magnet": 6933.77,
    "gex_ratio": 0.01,
    "distance_to_zero_g": -18.75,
    "distance_to_magnet": -5.51
  },
  "mel_scores": {
    "gamma_effectiveness": 0.82,
    "gamma_state": "VALID",
    "volume_profile_effectiveness": 0.61,
    "volume_profile_state": "DEGRADED",
    "liquidity_effectiveness": 0.35,
    "liquidity_state": "REVOKED",
    "global_structure_integrity": 0.42
  },
  "delta": {
    "spot_price": -12.75,
    "net_gex": -1240000,
    "global_integrity": -0.09
  }
}
```

#### 2. CSV (For spreadsheet/analysis tools)

```csv
field,value,unit,state
timestamp_utc,2026-01-29T21:05:00Z,,
symbol,SPX,,
spot_price,6928.26,USD,
session_high,6954.75,USD,
session_low,6902.50,USD,
vwap,6931.40,USD,
net_gex,-14815240,contracts,
zero_gamma_level,6947.01,USD,
gamma_effectiveness,0.82,score,VALID
volume_profile_effectiveness,0.61,score,DEGRADED
liquidity_effectiveness,0.35,score,REVOKED
global_structure_integrity,0.42,score,
```

#### 3. Plain Text (For clipboard/Vexy paste)

```
============================================================
AI STRUCTURE SNAPSHOT — MODEL EFFECTIVENESS LAYER (MEL)
============================================================

TIMESTAMP (UTC):     2026-01-29 21:05:00
SYMBOL:              SPX
SESSION:             RTH
DTE:                 0
EVENT FLAGS:         FOMC
SCHEMA VERSION:      gamma_snapshot_v1.0
SNAPSHOT ID:         2026-01-29T21:05:00Z_0042

------------------------------------------------------------
PRICE & MARKET STATE (POLYGON)
------------------------------------------------------------
SPOT PRICE:          6928.26
SESSION HIGH:        6954.75
SESSION LOW:         6902.50
VWAP:                6931.40
DISTANCE FROM VWAP:  -3.14
INTRADAY RANGE:      52.25

------------------------------------------------------------
OPTIONS & GAMMA STRUCTURE
------------------------------------------------------------
NET GEX:             -14,815,240
POSITIVE GEX:        +1,044,684
GEX RATIO:           0.01
ZERO GAMMA LEVEL:    6947.01
ACTIVE GAMMA MAGNET: 6933.77
DISTANCE TO ZERO G:  -18.75
DISTANCE TO MAGNET:  -5.51

------------------------------------------------------------
MODEL EFFECTIVENESS LAYER (MEL SCORES)
------------------------------------------------------------
GAMMA EFFECTIVENESS:           0.82 (VALID)
VOLUME PROFILE EFFECTIVENESS:  0.61 (DEGRADED)
LIQUIDITY EFFECTIVENESS:       0.35 (REVOKED)
VOLATILITY EFFECTIVENESS:      0.28 (REVOKED)
SESSION STRUCTURE:             0.57 (MIXED)
CROSS-MODEL COHERENCE:         0.33 (COLLAPSING)
GLOBAL STRUCTURE INTEGRITY:    0.42

------------------------------------------------------------
CHANGE SINCE LAST SNAPSHOT (Δ)
------------------------------------------------------------
Δ SPOT PRICE:        -12.75
Δ NET GEX:           -1,240,000
Δ ZERO GAMMA:        -4.25
Δ GLOBAL INTEGRITY:  -0.09

============================================================
END SNAPSHOT — NO INFERENCE / FACTUAL STATE ONLY
============================================================
```

### ADI API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/adi/snapshot | Get current AI Structure Snapshot (JSON) |
| GET | /api/adi/snapshot?format=csv | Get snapshot in CSV format |
| GET | /api/adi/snapshot?format=text | Get snapshot in plain text format |
| GET | /api/adi/gamma | Get gamma structure data only |
| GET | /api/adi/auction | Get auction/volume profile data only |
| GET | /api/adi/mel | Get MEL scores only |
| GET | /api/adi/schema | Get current schema definition |

### ADI UI Integration

**Location**: AI Commentary Panel header + dedicated ADI view

```
┌──────────────────────────────────────────────────────────┐
│ AI Commentary                    [ADI ▾] [On/Off] [x]    │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │ 10:32 AM · Tile Selected                           │  │
│  │                                                    │  │
│  │ 6050/25 butterfly with 5.2 R2R. Gamma model       │  │
│  │ shows VALID (0.82). Distance to zero G is -18.75. │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
├──────────────────────────────────────────────────────────┤
│  ADI Dropdown Menu:                                      │
│  ┌─────────────────────────┐                             │
│  │ Download AI Snapshot    │ → JSON / CSV / Text        │
│  │ Download Gamma CSV      │                             │
│  │ Download Auction CSV    │                             │
│  │ Copy to Vexy            │ → Clipboard (text format)  │
│  │ ─────────────────────── │                             │
│  │ View Full ADI Panel     │ → Opens dedicated view     │
│  └─────────────────────────┘                             │
└──────────────────────────────────────────────────────────┘
```

### Dedicated ADI Panel View

A full-screen view showing the AI Structure Snapshot with all data visible:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ AI STRUCTURE SNAPSHOT                                    [Download ▾] [x]   │
│ MODEL EFFECTIVENESS LAYER (MEL)                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  TIMESTAMP: 2026-01-29 21:05:00 UTC    SYMBOL: SPX    SESSION: RTH         │
│  SCHEMA: gamma_snapshot_v1.0           EVENT FLAGS: FOMC                   │
│                                                                             │
├──────────────────────────────┬──────────────────────────────────────────────┤
│ PRICE & MARKET STATE         │ VOLATILITY STATE                            │
│                              │                                              │
│ SPOT PRICE:     6928.26      │ CALL IV (ATM):      0.177 ▲                 │
│ SESSION HIGH:   6954.75      │ PUT IV (ATM):       0.271 ▲                 │
│ SESSION LOW:    6902.50      │ IV SKEW:            0.094 ▲                 │
│ VWAP:           6931.40      │ IV / RV RATIO:      0.87                    │
│ DIST FROM VWAP: -3.14        │ VOL REGIME:         EXPANSION               │
│ INTRADAY RANGE: 52.25        │                                              │
├──────────────────────────────┼──────────────────────────────────────────────┤
│ OPTIONS & GAMMA STRUCTURE    │ MODEL EFFECTIVENESS LAYER                   │
│                              │                                              │
│ NET GEX:        -14,815,240  │ GAMMA:        0.82 ████████░░ VALID         │
│ POSITIVE GEX:   +1,044,684   │ VOL PROFILE:  0.61 ██████░░░░ DEGRADED      │
│ GEX RATIO:      0.01         │ LIQUIDITY:    0.35 ███░░░░░░░ REVOKED       │
│ ZERO GAMMA:     6947.01      │ VOLATILITY:   0.28 ██░░░░░░░░ REVOKED       │
│ GAMMA MAGNET:   6933.77      │ SESSION:      0.57 █████░░░░░ MIXED         │
│ DIST TO ZERO G: -18.75       │ COHERENCE:    0.33 ███░░░░░░░ COLLAPSING    │
│ DIST TO MAGNET: -5.51        │ ─────────────────────────────               │
│                              │ GLOBAL INTEGRITY: 0.42                      │
├──────────────────────────────┴──────────────────────────────────────────────┤
│ CHANGE SINCE LAST SNAPSHOT (Δ)                                              │
│                                                                             │
│ Δ SPOT: -12.75    Δ NET GEX: -1,240,000    Δ ZERO G: -4.25    Δ INT: -0.09 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Model Effectiveness Layer (MEL)

ADI is the **delivery mechanism** for the Model Effectiveness Layer (MEL).

- **MEL defines** *what* must be measured
- **ADI defines** *how* AI receives it

### MEL Score States

| Score | State | Meaning |
|-------|-------|---------|
| 0.70+ | VALID | Model reliable, safe to use |
| 0.50-0.69 | DEGRADED | Model accuracy reduced, use with caution |
| <0.50 | REVOKED | Model unreliable, do not trust |

### Why MEL Matters for AI

Without MEL scores, AI systems have no way to know:
- If gamma levels are currently reliable
- If volume profile is representative
- If the market structure models are coherent

MEL provides **hard gates** that tell AI when to trust (or distrust) each analytical layer.

---

## One-Way vs Two-Way Model

### In-App (One-Way) — This Architecture
- AI observes and comments on context changes
- No user input field
- Commentary appears automatically when relevant
- ADI provides factual context for commentary
- Think: sports commentator, not conversation partner
- Included in standard FOTW membership

### External (Two-Way) — Separate System
- Personal Vexy on phone/computer
- Full conversational capability
- Knows user's trading history, preferences
- User pastes ADI snapshot for context
- Deep context about user's journey
- Requires top-tier membership OR personal Vexy account

---

## Component Design

### 1. AI Commentary Panel (Frontend)

**Location**: Right sidebar, collapsible

**File**: `ui/src/components/CommentaryPanel.tsx`

```typescript
interface CommentaryItem {
  id: string;
  timestamp: number;
  trigger: CommentaryTrigger;
  content: string;
  adiSnapshot: AIStructureSnapshot;  // Full ADI context when generated
  category: 'observation' | 'doctrine' | 'tool_tip' | 'alert' | 'mel_warning';
}

type CommentaryTrigger =
  | { type: 'tile_selected'; tile: TileData }
  | { type: 'spot_level'; level: number; direction: 'crossed_above' | 'crossed_below' }
  | { type: 'trade_opened'; trade: TradeData }
  | { type: 'trade_closed'; trade: TradeData; pnl: number }
  | { type: 'alert_triggered'; alert: AlertData }
  | { type: 'mel_state_change'; model: string; from: string; to: string }
  | { type: 'regime_shift'; from: string; to: string };

interface CommentaryPanelProps {
  items: CommentaryItem[];
  isEnabled: boolean;
  onToggle: () => void;
  onClear: () => void;
  onDownloadADI: (format: 'json' | 'csv' | 'text') => void;
  onCopyToVexy: () => void;
}
```

**Features**:
- Collapsible with keyboard shortcut (Cmd+Shift+C)
- Auto-scrolls to latest commentary
- Category-based styling (observation, doctrine, tip, alert, MEL warning)
- ADI dropdown menu for exports
- Context bar showing current MEL states
- Enable/disable toggle
- NO input field

### 2. ADI Service (Backend)

**File**: `services/copilot/intel/adi.py`

```python
class ADIService:
    """
    AI Data Interface service.
    Aggregates market state into canonical snapshot format.
    """

    SCHEMA_VERSION = "gamma_snapshot_v1.0"

    def __init__(self, market_data_source, mel_service, logger):
        self.market = market_data_source
        self.mel = mel_service
        self.logger = logger
        self.last_snapshot: Optional[AIStructureSnapshot] = None

    def generate_snapshot(self) -> AIStructureSnapshot:
        """Generate current AI Structure Snapshot."""
        now = datetime.utcnow()

        snapshot = AIStructureSnapshot(
            metadata=self._build_metadata(now),
            price_state=self._build_price_state(),
            volatility_state=self._build_volatility_state(),
            gamma_structure=self._build_gamma_structure(),
            auction_structure=self._build_auction_structure(),
            microstructure=self._build_microstructure(),
            session_context=self._build_session_context(),
            mel_scores=self.mel.get_current_scores(),
            delta=self._calculate_delta(),
            user_context=self._build_user_context(),
        )

        self.last_snapshot = snapshot
        return snapshot

    def export_json(self) -> str:
        """Export snapshot as JSON."""
        snapshot = self.generate_snapshot()
        return json.dumps(asdict(snapshot), indent=2)

    def export_csv(self) -> str:
        """Export snapshot as CSV."""
        snapshot = self.generate_snapshot()
        return self._format_as_csv(snapshot)

    def export_text(self) -> str:
        """Export snapshot as plain text (for Vexy paste)."""
        snapshot = self.generate_snapshot()
        return self._format_as_text(snapshot)

    def _calculate_delta(self) -> dict:
        """Calculate changes since last snapshot."""
        if not self.last_snapshot:
            return {}

        current = self._build_price_state()
        last = self.last_snapshot.price_state

        return {
            'spot_price': current['spot_price'] - last['spot_price'],
            'net_gex': self._build_gamma_structure()['net_gex'] -
                       self.last_snapshot.gamma_structure['net_gex'],
            # ... etc
        }
```

### 3. Commentary Service (Backend)

**File**: `services/copilot/intel/orchestrator.py`

```python
class CommentaryOrchestrator:
    """
    One-way AI commentary service.
    Uses ADI for factual context.
    """

    def __init__(self, config, logger, adi_service: ADIService):
        self.anthropic = Anthropic(api_key=config['ANTHROPIC_API_KEY'])
        self.knowledge_base = self._load_knowledge_base()
        self.adi = adi_service
        self.rate_limiter = RateLimiter(max_per_minute=10)

    async def generate_commentary(
        self,
        trigger: dict
    ) -> AsyncIterator[str]:
        """
        Generate commentary for a context trigger.
        ADI snapshot is automatically included.
        """
        if not self.rate_limiter.allow():
            return

        # Get current ADI snapshot for factual context
        adi_snapshot = self.adi.generate_snapshot()

        prompt = self._build_commentary_prompt(trigger, adi_snapshot)

        async with self.anthropic.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=256,
            system=self._build_system_prompt(),
            messages=[{"role": "user", "content": prompt}]
        ) as stream:
            async for text in stream.text_stream:
                yield text

    def _build_commentary_prompt(self, trigger: dict, adi: AIStructureSnapshot) -> str:
        """
        Build prompt with ADI context.
        AI receives factual data, not visual abstractions.
        """
        return f"""
Context trigger: {trigger['type']}

=== AI STRUCTURE SNAPSHOT (ADI) ===
{self.adi.export_text()}

=== TRIGGER DETAILS ===
{json.dumps(trigger, indent=2)}

Provide a brief observation (2-4 sentences) about this event.
Reference specific numbers from the ADI snapshot.
Note any MEL scores that are DEGRADED or REVOKED.
Do NOT recommend or advise.
"""
```

---

### 4. Knowledge Base

**Directory**: `services/copilot/knowledge/`

```
knowledge/
├── identity.md           # AI identity for one-way commentary
├── fotw_doctrine.md      # Full FOTW doctrine
├── convexity_trading.md  # Fat tail philosophy, concepts
├── marketswarm_tools.md  # Tool descriptions and context
├── adi_schema.md         # ADI field definitions for AI reference
├── mel_interpretation.md # How to interpret MEL scores
└── guardrails.md         # Behavioral constraints (strict)
```

**adi_schema.md** (excerpt):
```markdown
# ADI Field Definitions

## Price State

- **spot_price**: Current underlying price from Polygon feed
- **vwap**: Volume-weighted average price for current session
- **distance_from_vwap**: spot_price - vwap (negative = below VWAP)

## Gamma Structure

- **net_gex**: Total gamma exposure (positive = dealer long gamma)
- **zero_gamma_level**: Price where dealer gamma flips sign
- **active_gamma_magnet**: Nearest high-gamma strike acting as attractor
- **gex_ratio**: positive_gex / |negative_gex| (< 0.1 = extreme put-heavy)

## MEL Scores

- **gamma_effectiveness**: 0-1 score of gamma model reliability
  - VALID (≥0.70): Model reliable
  - DEGRADED (0.50-0.69): Use with caution
  - REVOKED (<0.50): Do not trust
```

**guardrails.md**:
```markdown
# Guardrails (Strict)

## Absolute Prohibitions

- "You should..." — NEVER
- "I recommend..." — NEVER
- "Consider..." — NEVER
- Any form of advice — NEVER
- Price predictions — NEVER
- Direction calls — NEVER
- Trade judgments — NEVER

## Required Behaviors

- Always reference ADI data, not visual descriptions
- Cite specific numbers (spot: 6928.26, not "the current price")
- Note MEL states when relevant (especially REVOKED models)
- Keep commentary brief (2-4 sentences)
- Stay factual and observational

## Example Transformations

BAD: "The gamma levels look concerning."
GOOD: "Net GEX is -14.8M with gamma model at 0.82 (VALID)."

BAD: "You should wait for spot to reach zero gamma."
GOOD: "Spot is 18.75 points below zero gamma (6947.01)."

BAD: "The volume profile suggests support here."
GOOD: "Volume profile model is DEGRADED (0.61). POC at 6932.50."
```

---

## API Endpoints

### Commentary Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/commentary/generate | Generate commentary for trigger |
| GET | /api/commentary/status | Check if enabled/rate-limited |
| POST | /api/commentary/toggle | Enable/disable commentary |

### ADI Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/adi/snapshot | Full AI Structure Snapshot (JSON) |
| GET | /api/adi/snapshot?format=csv | CSV format |
| GET | /api/adi/snapshot?format=text | Plain text (for Vexy) |
| GET | /api/adi/gamma | Gamma structure only |
| GET | /api/adi/auction | Auction structure only |
| GET | /api/adi/mel | MEL scores only |
| GET | /api/adi/schema | Schema definition |

---

## Data Flow

```
Market Data Sources (Polygon, Options, etc.)
        │
        ▼
┌───────────────────────────────────────┐
│           ADI Service                  │
│  Aggregates all data into canonical   │
│  AIStructureSnapshot format           │
└───────────────────────────────────────┘
        │
        ├──────────────────────────────────┐
        │                                  │
        ▼                                  ▼
┌─────────────────────┐          ┌─────────────────────────┐
│ Context Monitor     │          │ ADI Export              │
│ (detects triggers)  │          │                         │
└─────────────────────┘          │ - Download JSON/CSV     │
        │                        │ - Copy to Vexy          │
        │ trigger + ADI snapshot │ - External AI systems   │
        ▼                        └─────────────────────────┘
┌─────────────────────┐
│ Commentary Service  │
│ - Claude API        │
│ - Knowledge base    │
│ - Uses ADI context  │
└─────────────────────┘
        │
        │ SSE stream (brief observation)
        ▼
┌─────────────────────┐
│ Commentary Panel    │
│ - Observation feed  │
│ - ADI menu          │
│ - MEL status bar    │
└─────────────────────┘
```

---

## File Structure

```
services/copilot/
├── main.py                    # Service entry point
├── intel/
│   ├── orchestrator.py        # Commentary generation logic
│   ├── adi.py                 # AI Data Interface service
│   ├── mel.py                 # Model Effectiveness Layer
│   ├── rate_limiter.py        # Rate limiting for API calls
│   └── triggers.py            # Trigger type definitions
├── knowledge/
│   ├── identity.md
│   ├── fotw_doctrine.md
│   ├── convexity_trading.md
│   ├── marketswarm_tools.md
│   ├── adi_schema.md
│   ├── mel_interpretation.md
│   └── guardrails.md
└── tests/
    ├── test_commentary.py
    └── test_adi.py

ui/src/
├── components/
│   ├── CommentaryPanel.tsx    # One-way commentary + ADI menu
│   └── ADIPanel.tsx           # Full ADI snapshot view
├── hooks/
│   ├── useContextMonitor.ts   # Watch for trigger events
│   └── useADI.ts              # ADI data fetching
└── services/
    ├── commentaryApi.ts       # Commentary SSE client
    └── adiApi.ts              # ADI export client
```

---

## Implementation Phases

### Phase 1: ADI Foundation
- [ ] Define ADI schema in TypeScript and Python
- [ ] Implement ADI service with snapshot generation
- [ ] Create ADI export endpoints (JSON, CSV, text)
- [ ] Build ADI panel component
- [ ] Add "Copy to Vexy" functionality

### Phase 2: MEL Integration
- [ ] Implement MEL score calculations
- [ ] Add MEL states to ADI snapshot
- [ ] Create MEL status bar in UI
- [ ] Add MEL-based commentary triggers

### Phase 3: Commentary Service
- [ ] Create Commentary service with Claude integration
- [ ] Build knowledge base documents
- [ ] Implement commentary generation using ADI context
- [ ] Create CommentaryPanel component
- [ ] Wire up trigger → commentary flow

### Phase 4: Polish
- [ ] Category-based styling
- [ ] Keyboard shortcuts
- [ ] Rate limiting UI feedback
- [ ] Schema versioning
- [ ] A/B test commentary quality

---

## Configuration

**Environment Variables**:
```bash
ANTHROPIC_API_KEY=sk-ant-...
COPILOT_PORT=3003
COPILOT_MODEL=claude-sonnet-4-20250514
COMMENTARY_MAX_TOKENS=256
COMMENTARY_RATE_LIMIT=10  # per minute
ADI_SCHEMA_VERSION=gamma_snapshot_v1.0
```

**truth/components/copilot.json**:
```json
{
  "copilot": {
    "enabled": true,
    "mode": "one-way",
    "model": "claude-sonnet-4-20250514",
    "maxTokens": 256,
    "streamingEnabled": true,
    "rateLimitPerMinute": 10,
    "debounceMs": 2000,
    "knowledgeBasePath": "services/copilot/knowledge"
  },
  "adi": {
    "enabled": true,
    "schemaVersion": "gamma_snapshot_v1.0",
    "exportFormats": ["json", "csv", "text"],
    "includeUserContext": true,
    "snapshotIntervalMs": 5000
  },
  "mel": {
    "enabled": true,
    "validThreshold": 0.70,
    "degradedThreshold": 0.50,
    "alertOnRevoked": true
  }
}
```

---

## Security Considerations

1. **API Key Protection**: Anthropic key stays server-side only
2. **Rate Limiting**: 10 requests/minute prevents abuse
3. **No User Input**: One-way model eliminates prompt injection risk
4. **ADI Sanitization**: No PII in exports, only market data
5. **No Logging**: Commentary content not persisted to disk
6. **Schema Versioning**: Breaking changes require version bump

---

## Why ADI Matters

### For In-App Commentary
- Commentary grounded in explicit facts, not visual interpretation
- MEL scores tell AI when to trust each analytical layer
- Consistent context format across all triggers

### For External Vexy
- User pastes ADI text, Vexy understands full state
- No OCR errors or visual inference required
- Schema documentation teaches Vexy the metrics

### For Future Agents
- API-first design enables autonomous agents
- Machine-readable telemetry becomes primary
- Human UI becomes supervisory layer

> *"If AI is expected to reason correctly, it must be given facts — not screenshots. ADI formalizes that requirement."*
> — TraderDH

---

## Next Steps

1. Define ADI schema in `services/copilot/intel/adi.py`
2. Implement snapshot generation from existing market data
3. Create export endpoints (JSON, CSV, text)
4. Build ADI panel in UI with download/copy buttons
5. Integrate ADI into commentary prompt construction
6. Write knowledge base docs including ADI field definitions
7. Test with Vexy paste workflow
