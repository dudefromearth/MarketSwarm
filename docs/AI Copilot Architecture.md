# MarketSwarm AI Copilot — Technical Architecture

## Overview

A **one-way contextual commentary system** deeply integrated with MarketSwarm. The Copilot provides real-time observations, FOTW doctrine context, and market insights without interactive prompting — similar to Vexy Play-by-Play.

**Key Design Principle**: The in-app AI is one-way. Two-way interactive AI is available through:
- Personal Vexy (more capable, knows the user personally)
- Top-tier FOTW membership (covers API costs)

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         MarketSwarm UI                               │
│  ┌──────────────────────────────────────┐  ┌─────────────────────┐  │
│  │           Main Workspace              │  │   AI Commentary     │  │
│  │  ┌─────────┐ ┌─────────┐ ┌────────┐  │  │      Panel          │  │
│  │  │ Heatmap │ │   GEX   │ │  Risk  │  │  │  ┌──────────────┐   │  │
│  │  │         │ │         │ │ Graph  │  │  │  │  Observation │   │  │
│  │  └─────────┘ └─────────┘ └────────┘  │  │  │    Feed      │   │  │
│  │  ┌─────────────────────────────────┐ │  │  │              │   │  │
│  │  │         Trade Log               │ │  │  │  (one-way)   │   │  │
│  │  └─────────────────────────────────┘ │  │  └──────────────┘   │  │
│  └──────────────────────────────────────┘  │  ┌──────────────┐   │  │
│                                             │  │ Context Bar  │   │  │
│                                             │  │ [Spot][Tile] │   │  │
│                                             │  └──────────────┘   │  │
│                                             │                     │  │
│                                             │  No input field     │  │
│                                             └─────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Context Monitor                                 │
│  Watches for significant changes:                                    │
│  - Tile selection changed                                            │
│  - Spot price crossed key level                                      │
│  - Trade opened/closed                                               │
│  - Alert triggered                                                   │
│  - View changed                                                      │
│  - Regime shift detected                                             │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Commentary Service                               │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │
│  │  Event Router   │  │    Knowledge    │  │    Claude API       │  │
│  │                 │  │      Base       │  │    Integration      │  │
│  │ - Debounce      │  │                 │  │                     │  │
│  │ - Priority      │  │ - FOTW Doctrine │  │ - Streaming         │  │
│  │ - Rate limit    │  │ - Tool Guides   │  │ - Short responses   │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## One-Way vs Two-Way Model

### In-App (One-Way) — This Architecture
- AI observes and comments on context changes
- No user input field
- Commentary appears automatically when relevant
- Think: sports commentator, not conversation partner
- Included in standard FOTW membership

### External (Two-Way) — Separate System
- Personal Vexy on phone/computer
- Full conversational capability
- Knows user's trading history, preferences
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
  trigger: CommentaryTrigger;  // What caused this commentary
  content: string;
  context: ContextSnapshot;    // State when generated
  category: 'observation' | 'doctrine' | 'tool_tip' | 'alert';
}

type CommentaryTrigger =
  | { type: 'tile_selected'; tile: TileData }
  | { type: 'spot_level'; level: number; direction: 'crossed_above' | 'crossed_below' }
  | { type: 'trade_opened'; trade: TradeData }
  | { type: 'trade_closed'; trade: TradeData; pnl: number }
  | { type: 'alert_triggered'; alert: AlertData }
  | { type: 'view_changed'; from: string; to: string }
  | { type: 'risk_graph_updated'; strategies: number }
  | { type: 'regime_shift'; from: string; to: string };

interface ContextSnapshot {
  spot: number | null;
  underlying: string;
  vix?: number;
  gexRegime?: 'positive' | 'negative' | 'neutral';
  selectedTile?: TileData;
  openTrades: number;
  riskGraphStrategies: number;
  activeAlerts: number;
}

interface CommentaryPanelProps {
  items: CommentaryItem[];
  isEnabled: boolean;
  onToggle: () => void;
  onClear: () => void;
}
```

**Features**:
- Collapsible with keyboard shortcut (Cmd+Shift+C or similar)
- Auto-scrolls to latest commentary
- Category-based styling (observation, doctrine, tip, alert)
- Context bar showing what AI can "see"
- Clear history button
- Enable/disable toggle
- NO input field

**UI Layout**:
```
┌──────────────────────────────────────┐
│ AI Commentary              [On] [x]  │
├──────────────────────────────────────┤
│ ┌────────────────────────────────┐   │
│ │ 10:32 AM · Tile Selected       │   │
│ │                                │   │
│ │ 6050/25 butterfly with 5.2    │   │
│ │ R2R. Spot at 6045 puts you    │   │
│ │ 5 points from center strike.  │   │
│ │ In positive GEX regime, spot  │   │
│ │ tends to mean-revert...       │   │
│ └────────────────────────────────┘   │
│                                      │
│ ┌────────────────────────────────┐   │
│ │ 10:28 AM · FOTW Doctrine       │   │
│ │                                │   │
│ │ Fat tail strategies require   │   │
│ │ patience. The 5.2 R2R means   │   │
│ │ you can be wrong 4 times and  │   │
│ │ still profit on the 5th...    │   │
│ └────────────────────────────────┘   │
├──────────────────────────────────────┤
│ Watching: SPX 6045.32 | Tile 6050   │
│           3 strategies | 2 alerts    │
└──────────────────────────────────────┘
```

---

### 2. Context Monitor (Frontend)

**File**: `ui/src/hooks/useContextMonitor.ts`

A React hook that watches for significant context changes and triggers commentary.

```typescript
interface ContextMonitorConfig {
  enabled: boolean;
  debounceMs: number;           // Minimum time between triggers
  spotThreshold: number;        // Points of movement to trigger
  priorities: Record<string, number>;  // Event type priorities
}

function useContextMonitor(
  context: AppContext,
  config: ContextMonitorConfig,
  onTrigger: (trigger: CommentaryTrigger) => void
) {
  const prevContextRef = useRef<AppContext>();
  const lastTriggerRef = useRef<number>(0);

  useEffect(() => {
    const prevContext = prevContextRef.current;
    const now = Date.now();

    // Debounce
    if (now - lastTriggerRef.current < config.debounceMs) {
      prevContextRef.current = context;
      return;
    }

    // Check for trigger conditions
    const trigger = detectTrigger(prevContext, context);
    if (trigger) {
      lastTriggerRef.current = now;
      onTrigger(trigger);
    }

    prevContextRef.current = context;
  }, [context, config, onTrigger]);
}

function detectTrigger(prev: AppContext | undefined, curr: AppContext): CommentaryTrigger | null {
  // Tile selection changed
  if (curr.selectedTile?.id !== prev?.selectedTile?.id && curr.selectedTile) {
    return { type: 'tile_selected', tile: curr.selectedTile };
  }

  // Spot crossed significant level
  if (prev?.spot && curr.spot) {
    const gexFlip = curr.gexLevels?.flipLevel;
    if (gexFlip && prev.spot < gexFlip && curr.spot >= gexFlip) {
      return { type: 'spot_level', level: gexFlip, direction: 'crossed_above' };
    }
    if (gexFlip && prev.spot > gexFlip && curr.spot <= gexFlip) {
      return { type: 'spot_level', level: gexFlip, direction: 'crossed_below' };
    }
  }

  // Trade state changes
  if (curr.openTradesCount > (prev?.openTradesCount || 0)) {
    return { type: 'trade_opened', trade: curr.lastOpenedTrade };
  }

  // Alert triggered
  const newTriggered = curr.alerts?.find(a =>
    a.triggered && !prev?.alerts?.find(p => p.id === a.id)?.triggered
  );
  if (newTriggered) {
    return { type: 'alert_triggered', alert: newTriggered };
  }

  return null;
}
```

---

### 3. Commentary Service (Backend)

**File**: `services/copilot/intel/orchestrator.py`

```python
class CommentaryOrchestrator:
    """
    One-way AI commentary service.
    Generates contextual observations without user prompting.
    """

    def __init__(self, config, logger):
        self.anthropic = Anthropic(api_key=config['ANTHROPIC_API_KEY'])
        self.knowledge_base = self._load_knowledge_base()
        self.rate_limiter = RateLimiter(max_per_minute=10)

    async def generate_commentary(
        self,
        trigger: dict,
        context: dict
    ) -> AsyncIterator[str]:
        """
        Generate commentary for a context trigger.
        Returns streaming response.
        """
        if not self.rate_limiter.allow():
            return

        prompt = self._build_commentary_prompt(trigger, context)

        async with self.anthropic.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=256,  # Keep commentary concise
            system=self._build_system_prompt(),
            messages=[{"role": "user", "content": prompt}]
        ) as stream:
            async for text in stream.text_stream:
                yield text

    def _build_system_prompt(self) -> str:
        """
        System prompt for one-way commentary.
        Emphasizes observation over interaction.
        """
        return f"""
{self.knowledge_base['identity']}

## Your Role

You are a contextual commentator for MarketSwarm — like a knowledgeable observer
providing real-time insights. You DO NOT engage in conversation. You observe and
comment.

## Commentary Style

- Brief observations (2-4 sentences typical)
- Reference specific numbers from context
- Connect to FOTW doctrine when relevant
- Surface patterns the trader might not see
- NEVER recommend, suggest, or advise
- NEVER use "you should" or "consider"
- State observations, not instructions

## Knowledge Base
{self.knowledge_base['fotw_doctrine']}
{self.knowledge_base['convexity_trading']}
{self.knowledge_base['marketswarm_tools']}

## Guardrails
{self.knowledge_base['guardrails']}
"""

    def _build_commentary_prompt(self, trigger: dict, context: dict) -> str:
        """
        Build prompt for specific trigger type.
        """
        trigger_type = trigger['type']

        if trigger_type == 'tile_selected':
            tile = trigger['tile']
            return f"""
A tile was selected on the heatmap. Provide a brief observation.

Selected Tile:
- Strategy: {tile['strategy']}
- Strike: {tile['strike']}
- Width: {tile.get('width', 'N/A')}
- Side: {tile['side']}
- DTE: {tile['dte']}
- Debit: ${tile['debit']}
- Max Profit: ${tile['maxProfit']}
- R2R: {tile['r2r']}

Market Context:
- Spot: {context['spot']}
- Underlying: {context['underlying']}
- GEX Regime: {context.get('gexRegime', 'unknown')}
- VIX: {context.get('vix', 'N/A')}

Provide a brief observation about this setup. Reference specific numbers.
Do NOT recommend or advise.
"""

        if trigger_type == 'spot_level':
            return f"""
Spot price just crossed a significant level.

Event:
- Level: {trigger['level']}
- Direction: {trigger['direction']}
- Current Spot: {context['spot']}

GEX Context:
- Flip Level: {context.get('gexLevels', {}).get('flipLevel', 'N/A')}
- Regime: {context.get('gexRegime', 'unknown')}

Provide a brief observation about this price action. What does crossing
this level typically mean in FOTW doctrine? Reference specific numbers.
"""

        if trigger_type == 'trade_opened':
            trade = trigger['trade']
            return f"""
A trade was logged.

Trade:
- Strategy: {trade['strategy']}
- Strike: {trade['strike']}
- Entry: ${trade['entry_price']}
- Planned Risk: ${trade.get('planned_risk', 'N/A')}

Market Context:
- Spot: {context['spot']}
- GEX Regime: {context.get('gexRegime', 'unknown')}

Provide a brief observation about this entry. What does FOTW doctrine say
about trade logging and accountability? Keep it brief.
"""

        if trigger_type == 'alert_triggered':
            alert = trigger['alert']
            return f"""
An alert was triggered.

Alert:
- Type: {alert['type']}
- Target: {alert.get('targetValue', 'N/A')}
- Strategy: {alert.get('strategyLabel', 'N/A')}

Market Context:
- Spot: {context['spot']}

Provide a brief observation. What might the trader be watching for?
Keep it factual.
"""

        # Default fallback
        return f"""
Context changed. Provide a brief relevant observation.

Context:
- Spot: {context['spot']}
- Underlying: {context['underlying']}
- Open Trades: {context.get('openTradesCount', 0)}
- Active Strategies: {context.get('riskGraphStrategiesCount', 0)}
- Active Alerts: {context.get('alertsCount', 0)}
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
└── guardrails.md         # Behavioral constraints (strict)
```

**identity.md**:
```markdown
# AI Commentary Identity

You are the MarketSwarm Commentary AI — a contextual observer providing
real-time insights grounded in convexity trading and FOTW doctrine.

## Core Role

You OBSERVE and COMMENT. You do not CONVERSE or ADVISE.

Think of yourself as:
- A knowledgeable commentator at a trading desk
- Someone who notices patterns and connections
- A voice that surfaces relevant doctrine without lecturing

## Voice

- Terse, not chatty
- Specific numbers, not vague observations
- Pattern recognition, not prediction
- Doctrine connection, not instruction
- Question-raising, not answer-giving

## What You Do

- Note interesting R2R ratios
- Connect setups to FOTW principles
- Observe spot behavior relative to GEX levels
- Acknowledge trade entries without judgment
- Surface patterns across strategies
- Reference historical doctrine concepts

## What You Never Do

- Recommend trades
- Predict direction
- Suggest actions
- Judge decisions
- Say "you should" or "consider"
- Engage in back-and-forth dialogue
```

**guardrails.md**:
```markdown
# Guardrails (Strict)

## Absolute Prohibitions

- "You should..." — NEVER
- "I recommend..." — NEVER
- "Consider..." — NEVER
- "A good idea would be..." — NEVER
- "You might want to..." — NEVER
- Any form of advice — NEVER
- Price predictions — NEVER
- Direction calls — NEVER
- Trade judgments — NEVER

## Required Behaviors

- Ground every observation in specific context data
- Reference actual numbers (spot, strike, R2R)
- Connect to doctrine through observation, not instruction
- Keep commentary brief (2-4 sentences)
- Acknowledge uncertainty when present
- Stay factual and observational

## Example Transformations

BAD: "You should wait for spot to reach the strike before entering."
GOOD: "Spot is 15 points below the strike center."

BAD: "Consider setting a profit target here."
GOOD: "The 5.2 R2R implies breakeven if right 1-in-6."

BAD: "This looks like a good setup."
GOOD: "The R2R is above the FOTW threshold for asymmetric plays."
```

---

### 5. API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/commentary/generate | Generate commentary for trigger |
| GET | /api/commentary/status | Check if commentary is enabled/rate-limited |
| POST | /api/commentary/toggle | Enable/disable commentary |

**Generate Request**:
```json
{
  "trigger": {
    "type": "tile_selected",
    "tile": {
      "strategy": "butterfly",
      "strike": 6050,
      "width": 25,
      "debit": 4.20,
      "maxProfit": 21.80,
      "r2r": 5.2
    }
  },
  "context": {
    "spot": 6045.32,
    "underlying": "I:SPX",
    "gexRegime": "positive",
    "vix": 14.2,
    "openTradesCount": 2,
    "riskGraphStrategiesCount": 4
  }
}
```

**Generate Response** (SSE stream):
```
data: {"type": "text", "content": "6050/25 butterfly "}
data: {"type": "text", "content": "with 5.2 R2R. "}
data: {"type": "text", "content": "Spot at 6045 puts..."}
data: {"type": "done"}
```

---

## Data Flow

```
Context changes (tile, spot, trade, alert)
        │
        ▼
┌───────────────────┐
│ Context Monitor   │ ──── detectTrigger() ────▶ Significant change?
│ (Frontend)        │                                    │
└───────────────────┘                                    │ Yes
        │                                                ▼
        │                                    ┌───────────────────┐
        │                                    │ Debounce / Rate   │
        │                                    │ Limit Check       │
        │                                    └───────────────────┘
        │                                                │
        │ POST /api/commentary/generate                  │
        │ { trigger, context }                           │
        ▼                                                ▼
┌───────────────────┐                        ┌───────────────────┐
│ Commentary Service│ ◀──────────────────────│ Call Claude       │
│ (Backend)         │                        │ (256 token limit) │
│                   │                        └───────────────────┘
└───────────────────┘
        │
        │ SSE stream (brief observation)
        ▼
┌───────────────────┐
│ Commentary Panel  │
│ - Append to feed  │
│ - Auto-scroll     │
│ - Category style  │
└───────────────────┘
```

---

## File Structure

```
services/copilot/
├── main.py                    # Service entry point
├── intel/
│   ├── orchestrator.py        # Commentary generation logic
│   ├── rate_limiter.py        # Rate limiting for API calls
│   └── triggers.py            # Trigger type definitions
├── knowledge/
│   ├── identity.md
│   ├── fotw_doctrine.md
│   ├── convexity_trading.md
│   ├── marketswarm_tools.md
│   └── guardrails.md
└── tests/
    └── test_commentary.py

ui/src/
├── components/
│   └── CommentaryPanel.tsx    # One-way commentary display
├── hooks/
│   ├── useContextMonitor.ts   # Watch for trigger events
│   └── useCommentaryContext.ts # Context aggregation
└── services/
    └── commentaryApi.ts       # API client with SSE support
```

---

## Implementation Phases

### Phase 1: Foundation
- [ ] Create Commentary service with Claude integration
- [ ] Build knowledge base documents (pull from FOTW docs)
- [ ] Implement commentary generation endpoint
- [ ] Create CommentaryPanel component (display only)
- [ ] Implement context monitoring hook
- [ ] Basic trigger → commentary flow working

### Phase 2: Trigger Coverage
- [ ] Tile selection triggers
- [ ] Spot level crossing triggers
- [ ] Trade open/close triggers
- [ ] Alert triggered events
- [ ] View change triggers
- [ ] Risk graph update triggers

### Phase 3: Polish
- [ ] Category-based styling
- [ ] Context bar in panel
- [ ] Enable/disable toggle
- [ ] Clear history
- [ ] Rate limiting UI feedback
- [ ] Keyboard shortcut to toggle panel

### Phase 4: Knowledge Enhancement
- [ ] Refine prompts based on output quality
- [ ] Add more doctrine context
- [ ] Add tool-specific commentary templates
- [ ] A/B test commentary length/style

---

## Configuration

**Environment Variables**:
```bash
ANTHROPIC_API_KEY=sk-ant-...
COPILOT_PORT=3003
COPILOT_MODEL=claude-sonnet-4-20250514
COMMENTARY_MAX_TOKENS=256
COMMENTARY_RATE_LIMIT=10  # per minute
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
    "knowledgeBasePath": "services/copilot/knowledge",
    "triggers": {
      "tileSelected": true,
      "spotLevel": true,
      "tradeOpened": true,
      "tradeClosed": true,
      "alertTriggered": true,
      "viewChanged": false
    }
  }
}
```

---

## Security Considerations

1. **API Key Protection**: Anthropic key stays server-side only
2. **Rate Limiting**: 10 requests/minute prevents abuse
3. **No User Input**: One-way model eliminates prompt injection risk
4. **Context Sanitization**: Only send relevant context, no PII
5. **No Logging**: Commentary content not persisted to disk

---

## Two-Way Interaction (External)

For users who want conversational AI interaction:

1. **Personal Vexy**: Available on phone/computer via separate app
   - Full conversation capability
   - Knows user's trading history and style
   - Deep personal context
   - Requires Vexy account

2. **Top-Tier FOTW Membership**: Enables in-app chat
   - Adds chat input to Commentary Panel
   - Full conversational mode
   - Covers API costs
   - Same knowledge base, adds interaction

---

## Vexy Bridge — Context Export

An "umbilical cord" between MarketSwarm and personal Vexy. Users can export their current context as a structured data model that Vexy can understand — no screenshots needed.

### Export Button

**Location**: Settings or Commentary Panel header

**UI**:
```
┌──────────────────────────────────────┐
│ AI Commentary              [📋] [x]  │
│                            ↑         │
│                   Copy to Vexy       │
└──────────────────────────────────────┘
```

One-click copies context to clipboard in Vexy-readable format.

### Export Data Model

```typescript
interface VexyContextExport {
  // Metadata
  exportedAt: string;           // ISO timestamp
  source: 'MarketSwarm';
  version: '1.0';

  // Market State
  market: {
    underlying: string;         // "I:SPX"
    spot: number;               // 6045.32
    vix?: number;               // 14.2
    gexRegime?: string;         // "positive"
    gexFlipLevel?: number;      // 6040
  };

  // Current Focus
  focus?: {
    type: 'tile' | 'trade' | 'strategy';
    tile?: {
      strategy: string;
      strike: number;
      width?: number;
      side: string;
      dte: number;
      debit: number;
      maxProfit: number;
      r2r: number;
    };
    trade?: {
      id: string;
      strategy: string;
      strike: number;
      entryPrice: number;
      currentPnl?: number;
      status: string;
    };
  };

  // Position Summary
  positions: {
    openTrades: number;
    riskGraphStrategies: number;
    activeAlerts: number;
    totalExposure?: number;
  };

  // Log Context
  activeLog?: {
    id: string;
    name: string;
    startingCapital: number;
    currentEquity?: number;
    winRate?: number;
  };

  // Recent Activity
  recentCommentary?: Array<{
    timestamp: string;
    trigger: string;
    content: string;
  }>;
}
```

### Export Formats

**1. JSON (for Vexy parsing)**:
```json
{
  "exportedAt": "2025-01-30T10:32:00Z",
  "source": "MarketSwarm",
  "version": "1.0",
  "market": {
    "underlying": "I:SPX",
    "spot": 6045.32,
    "vix": 14.2,
    "gexRegime": "positive"
  },
  "focus": {
    "type": "tile",
    "tile": {
      "strategy": "butterfly",
      "strike": 6050,
      "width": 25,
      "debit": 4.20,
      "r2r": 5.2
    }
  },
  "positions": {
    "openTrades": 2,
    "riskGraphStrategies": 4,
    "activeAlerts": 3
  }
}
```

**2. Markdown (for conversation context)**:
```markdown
## MarketSwarm Context Export
*Exported: Jan 30, 2025 10:32 AM*

### Market
- **SPX** @ 6045.32
- VIX: 14.2
- GEX Regime: Positive (flip at 6040)

### Current Focus
Looking at **6050/25 butterfly** (call side)
- DTE: 0
- Debit: $4.20
- Max Profit: $21.80
- R2R: 5.2

### Positions
- 2 open trades
- 4 strategies on risk graph
- 3 active alerts

### Active Log
"0DTE Income" - Started with $25,000, currently at $27,450
```

### API Endpoint

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/context/export | Get current context for Vexy |
| GET | /api/context/export?format=markdown | Get markdown format |

### Frontend Implementation

**File**: `ui/src/utils/vexyExport.ts`

```typescript
function exportContextForVexy(context: AppContext, format: 'json' | 'markdown' = 'json'): string {
  const exportData: VexyContextExport = {
    exportedAt: new Date().toISOString(),
    source: 'MarketSwarm',
    version: '1.0',
    market: {
      underlying: context.underlying,
      spot: context.spot,
      vix: context.vix,
      gexRegime: context.gexLevels?.regime,
      gexFlipLevel: context.gexLevels?.flipLevel,
    },
    focus: context.selectedTile ? {
      type: 'tile',
      tile: context.selectedTile,
    } : undefined,
    positions: {
      openTrades: context.openTrades?.length || 0,
      riskGraphStrategies: context.riskGraphStrategies?.length || 0,
      activeAlerts: context.alerts?.filter(a => a.enabled).length || 0,
    },
    activeLog: context.selectedLog ? {
      id: context.selectedLog.id,
      name: context.selectedLog.name,
      startingCapital: context.selectedLog.starting_capital,
    } : undefined,
  };

  if (format === 'markdown') {
    return formatAsMarkdown(exportData);
  }

  return JSON.stringify(exportData, null, 2);
}

function copyToClipboard(context: AppContext, format: 'json' | 'markdown' = 'json'): void {
  const exported = exportContextForVexy(context, format);
  navigator.clipboard.writeText(exported);
}
```

### User Workflow

1. User is working in MarketSwarm, looking at a tile
2. User wants to discuss with their personal Vexy
3. User clicks "Copy to Vexy" button
4. Context is copied to clipboard
5. User opens Vexy on phone/computer
6. User pastes context, asks their question
7. Vexy understands the full MarketSwarm state

### Why This Matters

- **No screenshots**: Structured data Vexy can parse and reference
- **Consistent format**: Always the same schema
- **Complete context**: Everything relevant in one export
- **Privacy preserved**: User controls what gets shared
- **Vexy personalization**: Vexy can combine with user's history/style
- **Offline capable**: Works without real-time integration

---

## Next Steps

1. Create the `services/copilot/` directory structure
2. Write knowledge base documents (pull from existing FOTW docs)
3. Implement the commentary orchestrator
4. Build the CommentaryPanel component (one-way display)
5. Implement context monitoring hook
6. Wire up trigger → commentary flow
7. Test with tile selection and spot movements
