# Implementation Plan: ADI + MEL Infrastructure

## Overview

This plan establishes the **AI Data Interface (ADI)** and **Model Effectiveness Layer (MEL)** as foundational infrastructure before building Journal and Playbook features. These systems provide the data layer that all downstream features depend on.

---

## Dependency Graph

```
                    ┌─────────────────────────────────────────┐
                    │         Market Data Sources             │
                    │    (Polygon, Options, Order Flow)       │
                    └─────────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                        PHASE 1: MEL INFRASTRUCTURE                            │
│                                                                               │
│   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐         │
│   │ Gamma MEL Calc  │    │   VP MEL Calc   │    │ Global Integrity│         │
│   └─────────────────┘    └─────────────────┘    └─────────────────┘         │
└──────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                        PHASE 2: ADI INFRASTRUCTURE                            │
│                                                                               │
│   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐         │
│   │  ADI Snapshot   │    │  Export Formats │    │   ADI API       │         │
│   │   Generator     │    │ JSON/CSV/Text   │    │   Endpoints     │         │
│   └─────────────────┘    └─────────────────┘    └─────────────────┘         │
└──────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                        PHASE 3: UI INTEGRATION                                │
│                                                                               │
│   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐         │
│   │ MEL Status Bar  │    │  ADI Panel      │    │ Copy to Vexy    │         │
│   └─────────────────┘    └─────────────────┘    └─────────────────┘         │
└──────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    PHASE 4: AI COMMENTARY SERVICE                             │
│                                                                               │
│   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐         │
│   │Commentary Engine│    │ Knowledge Base  │    │Commentary Panel │         │
│   └─────────────────┘    └─────────────────┘    └─────────────────┘         │
└──────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    FUTURE: JOURNAL & PLAYBOOK                                 │
│                    (Depends on ADI + MEL)                                     │
│                                                                               │
│   • Trade entries capture MEL state at entry                                 │
│   • Journal reflects on trades with MEL context                              │
│   • Playbooks gated by MEL model validity                                    │
│   • Retrospectives use ADI historical data                                   │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: MEL Infrastructure

**Goal**: Build the MEL calculation engine that scores model effectiveness in real-time.

### 1.1 MEL Service Foundation

**Files to create**:
```
services/copilot/
├── main.py                    # Service entry point
├── intel/
│   ├── __init__.py
│   ├── mel.py                 # MEL orchestrator
│   ├── mel_models.py          # Data models
│   └── mel_calculator.py      # Base calculator class
```

**Deliverables**:
- [ ] MEL service skeleton with FastAPI/aiohttp
- [ ] MEL data models (MELSnapshot, MELModelScore)
- [ ] Base MELCalculator abstract class
- [ ] MEL orchestrator that coordinates calculators

### 1.2 Gamma Effectiveness Calculator

**File**: `services/copilot/intel/mel_gamma.py`

**Inputs needed**:
- Gamma levels from existing MarketSwarm data
- Intraday price history
- Zero gamma level, gamma magnet

**Metrics to calculate**:
- Level respect rate
- Mean reversion success
- Pin duration
- Violation frequency/magnitude
- Gamma level stability

**Deliverables**:
- [ ] GammaEffectivenessCalculator class
- [ ] Level respect rate calculation
- [ ] Mean reversion success calculation
- [ ] Composite gamma effectiveness score
- [ ] Unit tests

### 1.3 Volume Profile Effectiveness Calculator

**File**: `services/copilot/intel/mel_volume_profile.py`

**Inputs needed**:
- Volume profile data (POC, VAH, VAL, HVNs, LVNs)
- Intraday price history

**Metrics to calculate**:
- HVN acceptance rate
- LVN rejection rate
- Rotation completion
- Balance duration

**Deliverables**:
- [ ] VolumeProfileEffectivenessCalculator class
- [ ] HVN/LVN testing logic
- [ ] Rotation analysis
- [ ] Composite VP effectiveness score
- [ ] Unit tests

### 1.4 Global Structure Integrity

**File**: `services/copilot/intel/mel_global.py`

**Calculation**:
```python
global_integrity = (
    0.30 × gamma_effectiveness +
    0.25 × volume_profile_effectiveness +
    0.20 × liquidity_effectiveness +
    0.15 × volatility_effectiveness +
    0.10 × session_effectiveness
) × coherence_multiplier
```

**Deliverables**:
- [ ] Global integrity calculator
- [ ] Cross-model coherence detection
- [ ] State determination (VALID/DEGRADED/REVOKED)
- [ ] Delta tracking from previous snapshot

### 1.5 MEL API Endpoints

**File**: `services/copilot/intel/mel_api.py`

**Endpoints**:
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/mel/snapshot | Current MEL snapshot |
| GET | /api/mel/gamma | Gamma detail |
| GET | /api/mel/volume-profile | VP detail |
| GET | /api/mel/history | Historical snapshots |

**Deliverables**:
- [ ] MEL API routes
- [ ] Snapshot endpoint
- [ ] Detail endpoints
- [ ] WebSocket for real-time MEL updates

---

## Phase 2: ADI Infrastructure

**Goal**: Build the AI Data Interface that aggregates all market state into canonical format.

### 2.1 ADI Service Foundation

**Files to create**:
```
services/copilot/intel/
├── adi.py                     # ADI orchestrator
├── adi_models.py              # ADI data models
├── adi_exporters.py           # JSON/CSV/Text exporters
└── adi_api.py                 # ADI API endpoints
```

**Deliverables**:
- [ ] ADI data models (AIStructureSnapshot)
- [ ] ADI orchestrator class
- [ ] Integration with MEL service

### 2.2 ADI Snapshot Generator

**File**: `services/copilot/intel/adi.py`

**Data aggregation from**:
- Price state (Polygon)
- Volatility state
- Gamma structure (existing)
- Auction structure (volume profile)
- Microstructure (if available)
- Session context
- MEL scores (from Phase 1)
- User context (selected tile, alerts, trades)

**Deliverables**:
- [ ] ADIService class
- [ ] generate_snapshot() method
- [ ] Delta calculation from previous snapshot
- [ ] Event flag detection

### 2.3 ADI Export Formats

**File**: `services/copilot/intel/adi_exporters.py`

**Formats**:
1. **JSON** — Primary for AI parsing
2. **CSV** — For spreadsheet analysis
3. **Text** — For clipboard/Vexy paste

**Deliverables**:
- [ ] JSONExporter class
- [ ] CSVExporter class
- [ ] TextExporter class (formatted plain text)
- [ ] Schema version in all exports

### 2.4 ADI API Endpoints

**File**: `services/copilot/intel/adi_api.py`

**Endpoints**:
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/adi/snapshot | Full snapshot (JSON default) |
| GET | /api/adi/snapshot?format=csv | CSV format |
| GET | /api/adi/snapshot?format=text | Plain text |
| GET | /api/adi/gamma | Gamma structure only |
| GET | /api/adi/mel | MEL scores only |
| GET | /api/adi/schema | Schema definition |

**Deliverables**:
- [ ] ADI API routes
- [ ] Format parameter handling
- [ ] Partial snapshot endpoints
- [ ] Schema endpoint

---

## Phase 3: UI Integration

**Goal**: Surface MEL and ADI in the MarketSwarm UI.

### 3.1 MEL Status Bar

**File**: `ui/src/components/MELStatusBar.tsx`

**Design**:
```
┌─────────────────────────────────────────────────────────────────────────────┐
│ MEL: 42% │ Γ:84✓ │ VP:62⚠ │ LIQ:35✗ │ VOL:28✗ │ SES:57⚠ │ COH:33↓ │ [FOMC] │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Features**:
- Compact display in main workspace header
- Color-coded states (green/yellow/red)
- Click to expand MEL dashboard
- Event flags shown

**Deliverables**:
- [ ] MELStatusBar component
- [ ] useMEL hook for data fetching
- [ ] Real-time updates via WebSocket
- [ ] Integration into App.tsx header

### 3.2 MEL Dashboard

**File**: `ui/src/components/MELDashboard.tsx`

**Features**:
- Full effectiveness percentages with progress bars
- State indicators (VALID/DEGRADED/REVOKED)
- Trend arrows
- Global Structure Integrity gauge
- Click-through to detail screens

**Deliverables**:
- [ ] MELDashboard component
- [ ] Progress bar visualizations
- [ ] State styling
- [ ] Modal or dedicated view

### 3.3 ADI Panel

**File**: `ui/src/components/ADIPanel.tsx`

**Features**:
- Download dropdown (JSON/CSV/Text)
- Copy to Vexy button
- Preview of current snapshot
- Schema version display

**Deliverables**:
- [ ] ADIPanel component
- [ ] Download functionality
- [ ] Copy to clipboard
- [ ] useADI hook

### 3.4 Visual De-Emphasis

**File**: `ui/src/styles/mel.css`

**Rules**:
- DEGRADED widgets: 85% opacity, yellow border
- REVOKED widgets: 50% opacity, red border, grayscale filter

**Deliverables**:
- [ ] MEL state CSS classes
- [ ] Apply to heatmap when gamma REVOKED
- [ ] Apply to volume profile widgets when VP REVOKED

---

## Phase 4: AI Commentary Service

**Goal**: Build the one-way AI commentary system that uses ADI + MEL.

### 4.1 Commentary Service Foundation

**Files to create**:
```
services/copilot/intel/
├── commentary.py              # Commentary orchestrator
├── commentary_triggers.py     # Trigger detection
└── commentary_prompts.py      # Prompt templates
```

**Deliverables**:
- [ ] CommentaryOrchestrator class
- [ ] Claude API integration
- [ ] Rate limiting
- [ ] SSE streaming

### 4.2 Knowledge Base

**Files to create**:
```
services/copilot/knowledge/
├── identity.md
├── fotw_doctrine.md
├── convexity_trading.md
├── marketswarm_tools.md
├── adi_schema.md
├── mel_interpretation.md
└── guardrails.md
```

**Deliverables**:
- [ ] Identity document (one-way commentator role)
- [ ] FOTW doctrine reference
- [ ] ADI field definitions
- [ ] MEL interpretation guide
- [ ] Guardrails (strict prohibitions)

### 4.3 Trigger System

**File**: `services/copilot/intel/commentary_triggers.py`

**Triggers**:
- Tile selected
- Spot crossed level
- Trade opened/closed
- Alert triggered
- MEL state change
- Global integrity warning

**Deliverables**:
- [ ] Trigger detection logic
- [ ] Debouncing
- [ ] Priority handling
- [ ] MEL-specific triggers

### 4.4 Commentary Panel

**File**: `ui/src/components/CommentaryPanel.tsx`

**Features**:
- One-way observation feed (no input)
- Category styling (observation, doctrine, alert, MEL warning)
- Auto-scroll
- ADI dropdown in header
- Enable/disable toggle

**Deliverables**:
- [ ] CommentaryPanel component
- [ ] SSE client for streaming
- [ ] Category-based styling
- [ ] Context bar showing what AI sees

### 4.5 Context Monitor Hook

**File**: `ui/src/hooks/useContextMonitor.ts`

**Features**:
- Watch for significant context changes
- Debounce triggers
- Send to commentary service

**Deliverables**:
- [ ] useContextMonitor hook
- [ ] Trigger detection
- [ ] Integration with CommentaryPanel

---

## Implementation Timeline

### Week 1: MEL Foundation
| Day | Focus | Deliverables |
|-----|-------|--------------|
| 1-2 | MEL Service Setup | Service skeleton, data models, base calculator |
| 3-4 | Gamma Calculator | Level respect, mean reversion, composite score |
| 5 | VP Calculator | HVN/LVN testing, rotation analysis |

### Week 2: MEL + ADI
| Day | Focus | Deliverables |
|-----|-------|--------------|
| 1 | Global Integrity | Weighted composite, coherence detection |
| 2 | MEL API | Snapshot endpoint, detail endpoints |
| 3-4 | ADI Service | Snapshot generator, exporters |
| 5 | ADI API | Endpoints, format handling |

### Week 3: UI Integration
| Day | Focus | Deliverables |
|-----|-------|--------------|
| 1-2 | MEL UI | Status bar, dashboard |
| 3 | ADI UI | ADI panel, download/copy |
| 4 | Visual De-Emphasis | CSS classes, widget integration |
| 5 | Testing & Polish | End-to-end testing |

### Week 4: AI Commentary
| Day | Focus | Deliverables |
|-----|-------|--------------|
| 1-2 | Commentary Service | Orchestrator, Claude integration |
| 3 | Knowledge Base | All knowledge documents |
| 4 | Triggers + Panel | Trigger system, CommentaryPanel |
| 5 | Integration | Full flow testing |

---

## Technical Notes

### Service Configuration

**truth/components/copilot.json**:
```json
{
  "copilot": {
    "enabled": true,
    "mode": "one-way",
    "model": "claude-sonnet-4-20250514",
    "maxTokens": 256,
    "rateLimitPerMinute": 10
  },
  "adi": {
    "enabled": true,
    "schemaVersion": "gamma_snapshot_v1.0",
    "exportFormats": ["json", "csv", "text"],
    "snapshotIntervalMs": 5000
  },
  "mel": {
    "enabled": true,
    "thresholds": {
      "valid": 70,
      "degraded": 50
    },
    "weights": {
      "gamma": 0.30,
      "volume_profile": 0.25,
      "liquidity": 0.20,
      "volatility": 0.15,
      "session": 0.10
    }
  }
}
```

### Data Flow

```
Market Data → MEL Calculators → MEL Snapshot
                                    ↓
                              ADI Service → ADI Snapshot
                                    ↓
                    ┌───────────────┴───────────────┐
                    ↓                               ↓
            UI (MEL Status, ADI Panel)    Commentary Service
                                                    ↓
                                          CommentaryPanel (SSE)
```

### Existing Integration Points

**MarketSwarm data already available**:
- Gamma levels (from massive pipeline)
- Volume profile (POC, VAH, VAL)
- Spot price (from Polygon via SSE)
- Options chain data

**UI state already available**:
- Selected tile
- Risk graph strategies
- Alerts
- Open trades
- Selected log

---

## Success Criteria

### Phase 1 Complete When:
- [ ] MEL service running
- [ ] Gamma effectiveness calculating in real-time
- [ ] VP effectiveness calculating
- [ ] Global integrity score available
- [ ] MEL API returning snapshots

### Phase 2 Complete When:
- [ ] ADI service running
- [ ] Full ADI snapshots generating
- [ ] JSON/CSV/Text exports working
- [ ] ADI API returning data

### Phase 3 Complete When:
- [ ] MEL status bar in UI
- [ ] MEL dashboard accessible
- [ ] ADI panel with download/copy
- [ ] Visual de-emphasis applied

### Phase 4 Complete When:
- [ ] Commentary service generating observations
- [ ] Triggers firing on context changes
- [ ] Commentary panel displaying stream
- [ ] MEL state changes triggering commentary

---

## Why This Order Matters

1. **MEL First**: Without MEL, we can't know if models are valid. All downstream features need this.

2. **ADI Second**: ADI aggregates MEL + market state into canonical format. Commentary needs this.

3. **UI Third**: Users need to see MEL states before we can expect them to understand AI commentary that references MEL.

4. **Commentary Fourth**: The AI needs MEL + ADI infrastructure to generate grounded observations.

5. **Journal/Playbook Later**: These features will capture MEL state at trade entry, gate playbooks by model validity, and use ADI for retrospectives. They depend on all prior phases.

---

## Next Action

Start with **Phase 1.1: MEL Service Foundation**:

1. Create `services/copilot/` directory structure
2. Define MEL data models
3. Create base MELCalculator class
4. Build MEL orchestrator skeleton

Ready to begin?
