# Risk Graph Service Layer Implementation Plan

## Overview

Transform the Risk Graph from a localStorage-based component into a full service layer with:
- Backend persistence with user isolation
- Strategy versioning and audit trail
- Real-time multi-device sync via SSE
- Strategy templates for sharing and reuse
- Clean frontend hook-based architecture

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (React)                          │
├─────────────────────────────────────────────────────────────────┤
│  RiskGraphProvider (Context)                                     │
│  ├── useRiskGraph() hook - strategies, templates, operations    │
│  ├── SSE subscription for real-time sync                        │
│  └── localStorage fallback for offline                          │
├─────────────────────────────────────────────────────────────────┤
│  riskGraphService.ts - HTTP client for API calls                │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│                    SSE Gateway (Node.js)                         │
│  ├── /sse/risk-graph - User-scoped real-time channel           │
│  └── Redis pub/sub subscription for broadcasts                  │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│                  Journal Service (Python/FastAPI)                │
│  ├── /api/risk-graph/strategies/* - Strategy CRUD              │
│  ├── /api/risk-graph/templates/* - Template management         │
│  └── Redis pub/sub publish on changes                           │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│                      MySQL Database                              │
│  ├── risk_graph_strategies - Active strategies                  │
│  ├── risk_graph_strategy_versions - Audit trail                 │
│  └── risk_graph_templates - Saved/shareable templates           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. Database Schema

**File:** `services/journal/intel/db_v2.py` (add migration v16)

```sql
-- Active risk graph strategies per user
CREATE TABLE risk_graph_strategies (
    id VARCHAR(36) PRIMARY KEY,
    user_id INT NOT NULL,

    -- Strategy geometry
    symbol VARCHAR(20) NOT NULL DEFAULT 'SPX',
    underlying VARCHAR(20) NOT NULL DEFAULT 'I:SPX',
    strategy ENUM('single', 'vertical', 'butterfly') NOT NULL,
    side ENUM('call', 'put') NOT NULL,
    strike DECIMAL(10,2) NOT NULL,
    width INT DEFAULT NULL,
    dte INT NOT NULL,
    expiration DATE NOT NULL,
    debit DECIMAL(10,4) DEFAULT NULL,

    -- Display state
    visible BOOLEAN DEFAULT TRUE,
    sort_order INT DEFAULT 0,
    color VARCHAR(20) DEFAULT NULL,
    label VARCHAR(100) DEFAULT NULL,

    -- State
    added_at BIGINT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_user_active (user_id, is_active)
);

-- Version history for audit trail
CREATE TABLE risk_graph_strategy_versions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    strategy_id VARCHAR(36) NOT NULL,
    version INT NOT NULL,
    debit DECIMAL(10,4) DEFAULT NULL,
    visible BOOLEAN DEFAULT TRUE,
    label VARCHAR(100) DEFAULT NULL,
    change_type ENUM('created', 'debit_updated', 'visibility_toggled', 'edited', 'deleted') NOT NULL,
    change_reason VARCHAR(255) DEFAULT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (strategy_id) REFERENCES risk_graph_strategies(id) ON DELETE CASCADE,
    INDEX idx_strategy_version (strategy_id, version)
);

-- Saved strategy templates (shareable)
CREATE TABLE risk_graph_templates (
    id VARCHAR(36) PRIMARY KEY,
    user_id INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT DEFAULT NULL,

    -- Template geometry (strike is relative to ATM)
    symbol VARCHAR(20) NOT NULL DEFAULT 'SPX',
    strategy ENUM('single', 'vertical', 'butterfly') NOT NULL,
    side ENUM('call', 'put') NOT NULL,
    strike_offset INT DEFAULT 0,
    width INT DEFAULT NULL,
    dte_target INT NOT NULL,
    debit_estimate DECIMAL(10,4) DEFAULT NULL,

    -- Sharing
    is_public BOOLEAN DEFAULT FALSE,
    share_code VARCHAR(20) DEFAULT NULL UNIQUE,
    use_count INT DEFAULT 0,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_templates (user_id),
    INDEX idx_share_code (share_code)
);
```

---

## 2. Backend API Endpoints

**File:** `services/journal/intel/orchestrator.py`

### Strategy Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/risk-graph/strategies` | List active strategies for user |
| POST | `/api/risk-graph/strategies` | Add new strategy |
| PATCH | `/api/risk-graph/strategies/:id` | Update strategy (debit, visible, label) |
| DELETE | `/api/risk-graph/strategies/:id` | Remove strategy (soft delete) |
| GET | `/api/risk-graph/strategies/:id/versions` | Get audit trail |

### Template Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/risk-graph/templates` | List user's templates |
| POST | `/api/risk-graph/templates` | Create template |
| POST | `/api/risk-graph/templates/:id/use` | Instantiate template as strategy |
| POST | `/api/risk-graph/templates/:id/share` | Generate share code |
| GET | `/api/risk-graph/templates/shared/:code` | Get shared template |

### Bulk Operations

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/risk-graph/strategies/import` | Import strategies (JSON) |
| GET | `/api/risk-graph/strategies/export` | Export strategies |
| POST | `/api/risk-graph/strategies/reorder` | Update sort_order batch |

---

## 3. Real-time Sync (SSE)

**File:** `services/sse/src/routes/sse.js`

New channel: `GET /sse/risk-graph`

Events:
- `strategy_added` - New strategy created
- `strategy_updated` - Strategy modified
- `strategy_removed` - Strategy deleted

Flow:
1. Journal service publishes to Redis `risk_graph_updates` channel
2. SSE Gateway subscribes and broadcasts to user's connected clients
3. Frontend context receives events and updates state

---

## 4. Frontend Service

**New File:** `ui/src/services/riskGraphService.ts`

HTTP client with:
- `fetchStrategies()`, `createStrategy()`, `updateStrategy()`, `deleteStrategy()`
- `fetchStrategyVersions()`
- `fetchTemplates()`, `useTemplate()`, `getSharedTemplate()`
- `subscribeToRiskGraphStream()` - SSE subscription helper

---

## 5. Frontend Context

**New File:** `ui/src/contexts/RiskGraphContext.tsx`

```typescript
interface RiskGraphContextValue {
  // State
  strategies: RiskGraphStrategy[];
  templates: RiskGraphTemplate[];
  connected: boolean;
  loading: boolean;

  // Operations
  addStrategy: (strategy) => Promise<RiskGraphStrategy>;
  removeStrategy: (id: string) => void;
  toggleVisibility: (id: string) => void;
  updateDebit: (id: string, debit: number | null, reason?: string) => void;

  // Queries
  getStrategy: (id: string) => RiskGraphStrategy | undefined;
  getVisibleStrategies: () => RiskGraphStrategy[];
  getStrategyVersions: (id: string) => Promise<StrategyVersion[]>;

  // Templates
  loadTemplates: () => Promise<void>;
  useTemplate: (templateId, params) => Promise<RiskGraphStrategy>;

  // Bulk
  importStrategies: (strategies) => Promise<void>;
  exportStrategies: () => RiskGraphStrategy[];
}
```

Features:
- Optimistic updates with rollback on failure
- SSE subscription for real-time sync
- localStorage fallback for offline mode
- Auto-reconnect on disconnect

---

## 6. App.tsx Migration

### Remove
- `riskGraphStrategies` useState with localStorage
- `addToRiskGraph`, `removeFromRiskGraph`, `toggleStrategyVisibility`, `updateStrategyDebit` functions
- localStorage persistence useEffect

### Add
- Wrap app with `<RiskGraphProvider>`
- Use `useRiskGraph()` hook

### Simplify RiskGraphPanel Props
Before: 20+ props for strategies, callbacks, etc.
After: ~10 props (market data, simulation controls, external modal triggers)

---

## 7. Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `services/journal/intel/db_v2.py` | Modify | Add migration v16 with new tables |
| `services/journal/intel/models_v2.py` | Modify | Add RiskGraphStrategy, Template models |
| `services/journal/intel/orchestrator.py` | Modify | Add API endpoints |
| `services/sse/src/routes/sse.js` | Modify | Add /sse/risk-graph channel |
| `ui/src/types/riskGraph.ts` | Create | TypeScript types |
| `ui/src/services/riskGraphService.ts` | Create | HTTP client |
| `ui/src/contexts/RiskGraphContext.tsx` | Create | React context |
| `ui/src/App.tsx` | Modify | Remove old state, add provider |
| `ui/src/components/RiskGraphPanel.tsx` | Modify | Use context, simplify props |

---

## 8. Migration Strategy

1. **Phase 1**: Backend (can deploy independently)
   - Database migration
   - API endpoints
   - SSE channel

2. **Phase 2**: Frontend service layer (no breaking changes)
   - New service file
   - New context file
   - New types file

3. **Phase 3**: Migration with feature flag
   ```typescript
   const USE_SERVER_RISK_GRAPH = true;
   const { strategies } = USE_SERVER_RISK_GRAPH
     ? useRiskGraph()
     : useLocalStorage();
   ```

4. **Phase 4**: Remove old code
   - Delete localStorage logic
   - Remove feature flag

---

## 9. Verification

1. **Database**: Run migration, verify tables created
2. **API**: Test CRUD operations via curl/Postman
3. **SSE**: Open two browser tabs, add strategy in one, verify it appears in other
4. **Offline**: Disconnect network, add strategy, reconnect, verify sync
5. **Templates**: Create template, share it, import in different user
6. **Versions**: Update debit, check version history shows change
7. **Migration**: Enable feature flag, verify existing localStorage strategies load

---
---

# TradeLog–Journal Service Layer Implementation Plan

## Core Principle

> **UI is never the integration bus.**
> Services communicate via **versioned contracts**, not React hooks calling each other.

- **TradeLog–Journal** owns *what happened / what was intended / what was felt*
- **RiskGraph** owns *risk, payoff, scenario artifacts*
- Communication happens via **snapshots, events, and artifact references**

---

## Bounded Context Ownership

### TradeLog–Journal Service Owns
- Positions / Trades (open, adjust, close)
- Orders & fills
- Journaling (notes, bias flags, reflection objects)
- Audit trail & versions
- Position snapshots (authoritative)

### RiskGraph Service Owns
- Risk strategies & scenarios
- Payoff curves, Greeks, tail metrics
- Strategy versioning (risk-side)
- Risk artifacts linked to positions

> **Rule:** TradeLog never mutates RiskGraph state. RiskGraph never mutates TradeLog state.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (React)                          │
├─────────────────────────────────────────────────────────────────┤
│  TradeLogProvider (Context) - CLIENT, not system of record      │
│  ├── Cache server state                                         │
│  ├── Apply optimistic updates                                   │
│  ├── Reconcile via version                                      │
│  └── Subscribe to SSE                                           │
├─────────────────────────────────────────────────────────────────┤
│  tradeLogService.ts - HTTP client for API calls                 │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│                    SSE Gateway (Node.js)                         │
│  ├── /sse/trade-log - User-scoped real-time channel            │
│  ├── Event envelope with id, seq, version                       │
│  └── Redis pub/sub subscription                                 │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│               Journal Service (Python/FastAPI)                   │
│  ├── /api/positions/* - Position CRUD with versioning          │
│  ├── /api/positions/{id}/snapshot - For RiskGraph integration  │
│  ├── /api/journal_entries/* - Journaling                        │
│  ├── Idempotency-Key support on mutations                       │
│  └── Redis pub/sub publish on changes                           │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│                      MySQL Database                              │
│  ├── positions - Core position aggregate                        │
│  ├── legs - Individual option/stock legs                        │
│  ├── fills - Price/quantity records                             │
│  └── journal_entries - Reflection objects                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. Domain Model (Normalized)

### Position (replaces flattened TradeLog)
```sql
CREATE TABLE positions (
    id VARCHAR(36) PRIMARY KEY,
    user_id INT NOT NULL,
    status ENUM('planned', 'open', 'closed') NOT NULL DEFAULT 'planned',
    symbol VARCHAR(20) NOT NULL,
    underlying VARCHAR(20) NOT NULL,
    version INT NOT NULL DEFAULT 1,
    opened_at DATETIME DEFAULT NULL,
    closed_at DATETIME DEFAULT NULL,
    tags JSON DEFAULT NULL,
    campaign_id VARCHAR(36) DEFAULT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_user_status (user_id, status),
    INDEX idx_campaign (campaign_id)
);
```

### Leg
```sql
CREATE TABLE legs (
    id VARCHAR(36) PRIMARY KEY,
    position_id VARCHAR(36) NOT NULL,
    instrument_type ENUM('option', 'stock', 'future') NOT NULL,
    expiry DATE DEFAULT NULL,
    strike DECIMAL(10,2) DEFAULT NULL,
    right ENUM('call', 'put') DEFAULT NULL,
    quantity INT NOT NULL,  -- positive = long, negative = short
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (position_id) REFERENCES positions(id) ON DELETE CASCADE,
    INDEX idx_position (position_id)
);
```

### Fill
```sql
CREATE TABLE fills (
    id VARCHAR(36) PRIMARY KEY,
    leg_id VARCHAR(36) NOT NULL,
    price DECIMAL(10,4) NOT NULL,
    quantity INT NOT NULL,
    occurred_at DATETIME NOT NULL,      -- market reality
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP,  -- system reality

    FOREIGN KEY (leg_id) REFERENCES legs(id) ON DELETE CASCADE,
    INDEX idx_leg (leg_id)
);
```

### JournalEntry
```sql
CREATE TABLE journal_entries (
    id VARCHAR(36) PRIMARY KEY,
    position_id VARCHAR(36) NOT NULL,
    object_of_reflection TEXT NOT NULL,  -- required
    bias_flags JSON DEFAULT NULL,
    notes TEXT DEFAULT NULL,
    phase ENUM('setup', 'entry', 'management', 'exit', 'review') NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (position_id) REFERENCES positions(id) ON DELETE CASCADE,
    INDEX idx_position (position_id)
);
```

> Strategy type (vertical, butterfly, etc.) becomes **derived metadata**, not storage primitive.

---

## 2. Deterministic API Requirements

### Idempotency
- Every create/mutate endpoint accepts `Idempotency-Key` header
- Retries never duplicate state
- Store idempotency keys with TTL in Redis

### Versioning
- Each aggregate has a `version` field
- Mutations require `If-Match: <version>` header
- Returns `409 Conflict` with current version on mismatch

### Time Semantics
- `occurred_at` - when it happened in market reality
- `recorded_at` - when system recorded it

---

## 3. API Surface (Service-Level)

### Position Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/positions` | List positions for user (filterable by status) |
| POST | `/api/positions` | Create new position |
| GET | `/api/positions/{id}` | Get position with legs |
| PATCH | `/api/positions/{id}` | Update position (requires If-Match) |
| POST | `/api/positions/{id}/fills` | Record a fill |
| POST | `/api/positions/{id}/close` | Close position |
| GET | `/api/positions/{id}/snapshot` | **For RiskGraph** - full position snapshot |

### Snapshot Response (for RiskGraph Integration)
```json
{
  "position_id": "uuid",
  "version": 7,
  "status": "open",
  "symbol": "SPX",
  "underlying": "I:SPX",
  "legs": [
    {
      "id": "uuid",
      "instrument_type": "option",
      "expiry": "2025-02-21",
      "strike": 6100,
      "right": "call",
      "quantity": -1
    }
  ],
  "fills": [
    {
      "leg_id": "uuid",
      "price": 12.50,
      "quantity": -1,
      "occurred_at": "2025-02-05T10:30:00Z"
    }
  ],
  "metadata": {
    "derived_strategy": "single",
    "net_debit": 12.50,
    "dte": 16
  }
}
```

### Journal Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/journal_entries` | Create journal entry |
| GET | `/api/journal_entries?position_id=...` | Get entries for position |

### Order Endpoints (existing, enhanced)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/orders/active` | Get pending orders |
| POST | `/api/orders` | Create order (with Idempotency-Key) |
| DELETE | `/api/orders/{id}` | Cancel order |
| POST | `/api/orders/{id}/execute` | Execute order → creates position |

---

## 4. SSE Event Envelope (Deterministic)

Events must support deduplication, ordering, and replay.

```json
{
  "event_id": "uuid",
  "event_seq": 1842,
  "type": "PositionAdjusted",
  "aggregate_type": "position",
  "aggregate_id": "uuid",
  "aggregate_version": 7,
  "occurred_at": "2025-02-05T10:30:00Z",
  "payload": { ... }
}
```

### Event Types

| Event | Trigger |
|-------|---------|
| `PositionCreated` | New position opened |
| `FillRecorded` | Fill added to leg |
| `PositionAdjusted` | Leg added/modified |
| `PositionClosed` | Position closed |
| `OrderCreated` | New pending order |
| `OrderCancelled` | Order cancelled |
| `OrderFilled` | Order executed → position created |

### Frontend SSE Handling
- Track `last_event_seq` for reconnection
- Deduplicate by `event_id`
- Reconcile by `aggregate_version`

---

## 5. RiskGraph ↔ TradeLog Integration

### Pattern A: Pull-Based (Recommended for Phase 1)

1. RiskGraph requests snapshot:
   ```
   GET /api/positions/{id}/snapshot
   ```
2. RiskGraph computes risk artifacts
3. RiskGraph stores its own artifact with `position_id` reference
4. Optional callback to TradeLog:
   ```
   POST /api/positions/{id}/risk-artifact
   { "artifact_id": "uuid", "computed_at": "..." }
   ```

### Pattern B: Event-Based (Phase 2)

- TradeLog emits domain events via SSE
- RiskGraph subscribes and recomputes on relevant events
- RiskGraph emits `RiskArtifactComputed`
- TradeLog stores only artifact reference, never risk math

> **Key Rule:** All cross-app communication must survive the UI being deleted.

---

## 6. Frontend Types

**New File:** `ui/src/types/tradeLog.ts`

```typescript
// Normalized domain types
export interface Position {
  id: string;
  user_id: number;
  status: 'planned' | 'open' | 'closed';
  symbol: string;
  underlying: string;
  version: number;
  opened_at: string | null;
  closed_at: string | null;
  tags: string[] | null;
  campaign_id: string | null;
  legs: Leg[];
}

export interface Leg {
  id: string;
  position_id: string;
  instrument_type: 'option' | 'stock' | 'future';
  expiry: string | null;
  strike: number | null;
  right: 'call' | 'put' | null;
  quantity: number;
}

export interface Fill {
  id: string;
  leg_id: string;
  price: number;
  quantity: number;
  occurred_at: string;
  recorded_at: string;
}

export interface JournalEntry {
  id: string;
  position_id: string;
  object_of_reflection: string;
  bias_flags: string[] | null;
  notes: string | null;
  phase: 'setup' | 'entry' | 'management' | 'exit' | 'review';
  created_at: string;
}

export interface PendingOrder {
  id: string;
  position_template: Omit<Position, 'id' | 'user_id' | 'version' | 'status'>;
  limit_price: number;
  order_type: 'limit' | 'market';
  status: 'pending' | 'filled' | 'cancelled';
  created_at: string;
}

// Derived metadata (computed, not stored)
export interface PositionMetadata {
  derived_strategy: 'single' | 'vertical' | 'butterfly' | 'custom';
  net_debit: number;
  dte: number;
  max_profit: number | null;
  max_loss: number | null;
}

// SSE Event envelope
export interface TradeLogEvent {
  event_id: string;
  event_seq: number;
  type: string;
  aggregate_type: 'position' | 'order';
  aggregate_id: string;
  aggregate_version: number;
  occurred_at: string;
  payload: unknown;
}
```

---

## 7. Frontend Service

**New File:** `ui/src/services/tradeLogService.ts`

```typescript
const JOURNAL_API = import.meta.env.VITE_JOURNAL_API || '';

const createFetchOptions = (
  method: string = 'GET',
  body?: unknown,
  version?: number,
  idempotencyKey?: string
): RequestInit => ({
  method,
  credentials: 'include',
  headers: {
    'Content-Type': 'application/json',
    ...(version && { 'If-Match': String(version) }),
    ...(idempotencyKey && { 'Idempotency-Key': idempotencyKey }),
  },
  ...(body && { body: JSON.stringify(body) }),
});

export const tradeLogService = {
  // Positions
  fetchPositions: (status?: string) =>
    fetch(`${JOURNAL_API}/api/positions${status ? `?status=${status}` : ''}`,
      createFetchOptions()),

  getPosition: (id: string) =>
    fetch(`${JOURNAL_API}/api/positions/${id}`, createFetchOptions()),

  getPositionSnapshot: (id: string) =>
    fetch(`${JOURNAL_API}/api/positions/${id}/snapshot`, createFetchOptions()),

  createPosition: (position: PositionInput, idempotencyKey: string) =>
    fetch(`${JOURNAL_API}/api/positions`,
      createFetchOptions('POST', position, undefined, idempotencyKey)),

  updatePosition: (id: string, updates: Partial<Position>, version: number) =>
    fetch(`${JOURNAL_API}/api/positions/${id}`,
      createFetchOptions('PATCH', updates, version)),

  recordFill: (positionId: string, fill: FillInput, idempotencyKey: string) =>
    fetch(`${JOURNAL_API}/api/positions/${positionId}/fills`,
      createFetchOptions('POST', fill, undefined, idempotencyKey)),

  closePosition: (id: string, version: number) =>
    fetch(`${JOURNAL_API}/api/positions/${id}/close`,
      createFetchOptions('POST', undefined, version)),

  // Orders
  fetchPendingOrders: () =>
    fetch(`${JOURNAL_API}/api/orders/active`, createFetchOptions()),

  createOrder: (order: OrderInput, idempotencyKey: string) =>
    fetch(`${JOURNAL_API}/api/orders`,
      createFetchOptions('POST', order, undefined, idempotencyKey)),

  cancelOrder: (id: string) =>
    fetch(`${JOURNAL_API}/api/orders/${id}`, createFetchOptions('DELETE')),

  executeOrder: (id: string) =>
    fetch(`${JOURNAL_API}/api/orders/${id}/execute`, createFetchOptions('POST')),

  // Journal
  createJournalEntry: (entry: JournalEntryInput) =>
    fetch(`${JOURNAL_API}/api/journal_entries`, createFetchOptions('POST', entry)),

  getJournalEntries: (positionId: string) =>
    fetch(`${JOURNAL_API}/api/journal_entries?position_id=${positionId}`,
      createFetchOptions()),

  // SSE
  subscribeToStream: (
    onEvent: (event: TradeLogEvent) => void,
    lastSeq?: number
  ) => {
    const url = new URL(`${JOURNAL_API}/sse/trade-log`);
    if (lastSeq) url.searchParams.set('last_seq', String(lastSeq));

    const eventSource = new EventSource(url.toString(), { withCredentials: true });

    eventSource.onmessage = (e) => {
      const event = JSON.parse(e.data) as TradeLogEvent;
      onEvent(event);
    };

    return () => eventSource.close();
  },
};
```

---

## 8. Frontend Context

**New File:** `ui/src/contexts/TradeLogContext.tsx`

```typescript
interface TradeLogContextValue {
  // State (cached from server)
  positions: Position[];
  pendingOrders: PendingOrder[];
  loading: boolean;
  connected: boolean;
  lastEventSeq: number;

  // Position Operations
  refreshPositions: () => Promise<void>;
  createPosition: (position: PositionInput) => Promise<Position>;
  updatePosition: (id: string, updates: Partial<Position>) => Promise<void>;
  recordFill: (positionId: string, fill: FillInput) => Promise<void>;
  closePosition: (id: string) => Promise<void>;
  getPositionSnapshot: (id: string) => Promise<PositionSnapshot>;

  // Order Operations
  createOrder: (order: OrderInput) => Promise<PendingOrder>;
  cancelOrder: (id: string) => Promise<void>;
  executeOrder: (id: string) => Promise<Position>;

  // Journal Operations
  addJournalEntry: (entry: JournalEntryInput) => Promise<JournalEntry>;
  getJournalEntries: (positionId: string) => Promise<JournalEntry[]>;

  // Queries (derived from cached state)
  getOpenPositions: () => Position[];
  getClosedPositions: () => Position[];
  getPositionById: (id: string) => Position | undefined;
  getPendingOrderCount: () => number;
}
```

### Context Responsibilities (Client, Not Authority)
1. **Cache server state** - Mirror of backend truth
2. **Apply optimistic updates** - Immediate UI feedback
3. **Reconcile via version** - Handle conflicts from SSE events
4. **Subscribe to SSE** - Stay in sync
5. **Never assume authority** - Server is always right

---

## 9. Offline Mode Strategy

Phase 1: **Read-only offline**
- Cache last known state
- Show "offline" indicator
- Block mutations

Phase 2 (future): **Queued writes**
- Outbox pattern with idempotency keys
- Reconciliation on reconnect
- Conflict resolution UI

---

## 10. Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `services/journal/intel/db_v2.py` | Modify | Add migration with new schema |
| `services/journal/intel/orchestrator.py` | Modify | New endpoints, idempotency, versioning |
| `services/sse/src/routes/sse.js` | Modify | Add /sse/trade-log with event envelope |
| `ui/src/types/tradeLog.ts` | Create | Normalized TypeScript types |
| `ui/src/services/tradeLogService.ts` | Create | HTTP client with headers |
| `ui/src/contexts/TradeLogContext.tsx` | Create | React context (client) |
| `ui/src/components/MonitorPanel.tsx` | Modify | Use context |
| `ui/src/components/TradeLogPanel.tsx` | Modify | Use context |
| `ui/src/components/TradeEntryModal.tsx` | Modify | Use context |
| `ui/src/App.tsx` | Modify | Add TradeLogProvider |

---

## 11. Implementation Order

### Phase 1: Backend Foundation
1. Database migration (positions, legs, fills, journal_entries)
2. Position API endpoints with versioning
3. Idempotency key infrastructure
4. Snapshot endpoint for RiskGraph

### Phase 2: Real-time Infrastructure
5. SSE channel with event envelope
6. Redis publish on mutations
7. Event sequence tracking

### Phase 3: Frontend Service Layer
8. Types file
9. Service file with headers
10. Context with SSE integration

### Phase 4: Component Migration
11. Add TradeLogProvider to App.tsx
12. Migrate MonitorPanel
13. Migrate TradeLogPanel
14. Migrate TradeEntryModal

### Phase 5: Integration
15. Wire RiskGraph to use `/api/positions/{id}/snapshot`
16. Remove UI-level cross-context calls
17. Test headless communication (API-only)

---

## 12. Verification

### Service-Level Tests
1. **Idempotency**: Send same request twice with same key, verify no duplicate
2. **Versioning**: Send update with stale version, verify 409 Conflict
3. **Snapshot**: Fetch snapshot, verify complete position data
4. **Events**: Verify event envelope has all required fields

### Integration Tests
5. **SSE Sync**: Create position in one tab, verify it appears in other
6. **RiskGraph Integration**: Load position to RiskGraph via snapshot API
7. **Reconnection**: Disconnect SSE, reconnect with last_seq, verify no gaps
8. **Headless Test**: Call APIs without UI, verify full functionality

### The Ultimate Test
> **Can TradeLog and RiskGraph coordinate with the UI deleted?**
> If yes: you built services.
> If no: you built contexts pretending to be services

---
---

# ML Feedback Loop for Trade Selector

## Overview

Build a high-throughput, deterministic learning system capable of handling **~20k trades/day**, recording **context + outcomes + path-dependent P&L**, and feeding data into an ML loop that continuously improves strategy selection.

**Current State:**
- Trade Selector scores ideas with: Convexity (40%), R2R (25%), Width Fit (20%), Gamma Alignment (15%)
- Already has `tracked_ideas` table with entry context, max P&L, settlement data
- Already has `selector_params` table for versioned scoring weights
- Market context available: VIX regime, GEX structure, bias/LFI signals

**Goal:** Close the loop with ML while guaranteeing:
- **Reproducibility** - Which model/weights scored this idea? Which exact features?
- **Determinism** - What trades occurred and what was the path-dependent P&L?
- **Auditability** - What market regime/context existed at decision time?

**Throughput Context:**
- ~20k/day = **evaluated candidates** (ideas generated and scored by Trade Selector)
- Actual traded positions = much smaller subset (dozens to hundreds/day)
- Event spine handles high-throughput scoring
- P&L ledger tracks the smaller set of actual positions

---

## 0. First Principles

### Object of the System
The object is not "prediction." The object is **position selection + execution outcomes + regime context**.

### Deterministic Requirements
Every scoring decision must be fully reproducible later:
- **Immutable feature snapshots** for every scoring decision
- **Immutable decision records** linking: idea → model version → features → score → action → outcome
- **Idempotency + ordering** for high-throughput ingestion

---

## Architecture

With ~20k trades/day + time-series snapshots, pure "write to MySQL per tick" will saturate. Use **event-driven ingestion + materialized views**.

```
┌─────────────────────────────────────────────────────────────────┐
│                    Trade Selector                                │
│  ├── Scoring Engine (current rules)                             │
│  ├── Fast ML Path (lightweight GBDT, <5ms)                      │
│  └── Decision Logger → Redis Stream                             │
└────────────────────────┬────────────────────────────────────────┘
                         │ append-only events
┌────────────────────────▼────────────────────────────────────────┐
│                    Event Spine (Redis Streams)                   │
│  ├── ml_decisions stream (immutable decision records)           │
│  ├── pnl_events stream (P&L deltas)                             │
│  └── feature_snapshots stream                                   │
└───────────┬──────────────────────────────────┬──────────────────┘
            │                                  │
┌───────────▼───────────┐        ┌─────────────▼──────────────────┐
│   MySQL (Canonical)    │        │   ClickHouse (Analytics)       │
│  ├── ml_decisions      │        │  ├── Dense time-series         │
│  ├── pnl_events        │        │  ├── Equity curves             │
│  └── daily_performance │        │  └── Feature aggregations      │
└───────────┬────────────┘        └──────────────────────────────┘
            │
┌───────────▼────────────────────────────────────────────────────┐
│                 Training Pipeline (Offline)                      │
│  ├── Feature extraction with point-in-time correctness         │
│  ├── Walk-forward validation                                    │
│  ├── Regime-specific model training                             │
│  └── Calibration-focused evaluation                             │
└────────────────────────┬───────────────────────────────────────┘
                         │
┌────────────────────────▼───────────────────────────────────────┐
│                    Model Registry                                │
│  ├── Versioned models with feature_set_version                  │
│  ├── Per-regime champions                                       │
│  ├── Drift detection gates                                      │
│  └── Shadow mode → conservative blend → full deployment         │
└────────────────────────────────────────────────────────────────┘
```

---

## 1. Core Schema: Deterministic Data Foundation

**File:** `services/journal/intel/db_v2.py` (add migration)

### Immutable Decision Records (Critical for Reproducibility)

```sql
-- Every scoring decision is logged immutably
CREATE TABLE ml_decisions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idea_id VARCHAR(36) NOT NULL,
    decision_time DATETIME(3) NOT NULL,  -- millisecond precision

    -- Model identification (for exact reproducibility)
    model_id INT DEFAULT NULL,
    model_version INT DEFAULT NULL,
    selector_params_version INT NOT NULL,
    feature_snapshot_id BIGINT NOT NULL,

    -- Scores
    original_score DECIMAL(6,2) NOT NULL,  -- rule-based
    ml_score DECIMAL(6,2) DEFAULT NULL,     -- ML contribution
    final_score DECIMAL(6,2) NOT NULL,      -- blended

    -- Experiment tracking
    experiment_id INT DEFAULT NULL,
    experiment_arm ENUM('champion', 'challenger') DEFAULT NULL,

    -- Action taken
    action_taken ENUM('ranked', 'presented', 'traded', 'dismissed') DEFAULT 'ranked',

    INDEX idx_idea (idea_id),
    INDEX idx_decision_time (decision_time),
    INDEX idx_model (model_id, model_version),
    INDEX idx_experiment (experiment_id, experiment_arm)
);
```

### P&L Ledger (Append-Only, Path-Dependent Tracking)

```sql
-- Append-only P&L events for accurate path reconstruction
CREATE TABLE pnl_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_time DATETIME(3) NOT NULL,
    idea_id VARCHAR(36) NOT NULL,
    trade_id VARCHAR(36) DEFAULT NULL,
    strategy_id VARCHAR(36) DEFAULT NULL,

    -- P&L delta (not cumulative)
    pnl_delta DECIMAL(12,2) NOT NULL,
    fees DECIMAL(8,2) DEFAULT 0,
    slippage DECIMAL(8,2) DEFAULT 0,

    -- Context
    underlying_price DECIMAL(10,2) NOT NULL,
    event_type ENUM('mark', 'fill', 'settlement', 'adjustment') NOT NULL,

    INDEX idx_idea_time (idea_id, event_time),
    INDEX idx_trade (trade_id),
    INDEX idx_event_time (event_time)
);

-- Daily aggregated performance (materialized from pnl_events)
CREATE TABLE daily_performance (
    id INT AUTO_INCREMENT PRIMARY KEY,
    date DATE NOT NULL UNIQUE,

    -- P&L metrics
    net_pnl DECIMAL(12,2) NOT NULL,
    gross_pnl DECIMAL(12,2) NOT NULL,
    total_fees DECIMAL(10,2) NOT NULL,

    -- High water / drawdown
    high_water_pnl DECIMAL(12,2) NOT NULL,  -- max cumulative at any point
    max_drawdown DECIMAL(12,2) NOT NULL,
    drawdown_pct DECIMAL(6,4) DEFAULT NULL,

    -- Volume metrics
    trade_count INT NOT NULL,
    win_count INT NOT NULL,
    loss_count INT NOT NULL,

    -- Model attribution
    primary_model_id INT DEFAULT NULL,
    ml_contribution_pct DECIMAL(6,4) DEFAULT NULL,  -- % of decisions using ML

    INDEX idx_date (date)
);
```

### Feature Snapshots (with Versioning for Point-in-Time Correctness)

```sql
-- Feature snapshots at idea generation time
CREATE TABLE ml_feature_snapshots (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    tracked_idea_id INT NOT NULL,
    snapshot_time DATETIME(3) NOT NULL,

    -- VERSIONING (critical for reproducibility)
    feature_set_version VARCHAR(20) NOT NULL,  -- e.g., "v2.3"
    feature_extractor_version VARCHAR(20) NOT NULL,
    gex_calc_version VARCHAR(20) DEFAULT NULL,
    vix_regime_classifier_version VARCHAR(20) DEFAULT NULL,

    -- Price Action Features
    spot_price DECIMAL(10,2) NOT NULL,
    spot_5m_return DECIMAL(8,6) DEFAULT NULL,
    spot_15m_return DECIMAL(8,6) DEFAULT NULL,
    spot_1h_return DECIMAL(8,6) DEFAULT NULL,
    spot_1d_return DECIMAL(8,6) DEFAULT NULL,
    intraday_high DECIMAL(10,2) DEFAULT NULL,
    intraday_low DECIMAL(10,2) DEFAULT NULL,
    range_position DECIMAL(6,4) DEFAULT NULL,

    -- Volatility Features
    vix_level DECIMAL(6,2) DEFAULT NULL,
    vix_regime ENUM('chaos', 'goldilocks_1', 'goldilocks_2', 'zombieland') DEFAULT NULL,
    vix_term_slope DECIMAL(8,4) DEFAULT NULL,
    iv_rank_30d DECIMAL(6,4) DEFAULT NULL,
    iv_percentile_30d DECIMAL(6,4) DEFAULT NULL,

    -- GEX Structure Features
    gex_total DECIMAL(15,2) DEFAULT NULL,
    gex_call_wall DECIMAL(10,2) DEFAULT NULL,
    gex_put_wall DECIMAL(10,2) DEFAULT NULL,
    gex_gamma_flip DECIMAL(10,2) DEFAULT NULL,
    spot_vs_call_wall DECIMAL(8,4) DEFAULT NULL,
    spot_vs_put_wall DECIMAL(8,4) DEFAULT NULL,
    spot_vs_gamma_flip DECIMAL(8,4) DEFAULT NULL,

    -- Market Mode Features
    market_mode VARCHAR(20) DEFAULT NULL,
    bias_lfi DECIMAL(6,4) DEFAULT NULL,
    bias_direction ENUM('bullish', 'bearish', 'neutral') DEFAULT NULL,

    -- Time Features
    minutes_since_open INT DEFAULT NULL,
    day_of_week TINYINT DEFAULT NULL,
    is_opex_week BOOLEAN DEFAULT FALSE,
    days_to_monthly_opex INT DEFAULT NULL,

    -- Cross-Asset Signals
    es_futures_premium DECIMAL(6,4) DEFAULT NULL,
    tnx_level DECIMAL(6,3) DEFAULT NULL,
    dxy_level DECIMAL(6,2) DEFAULT NULL,

    FOREIGN KEY (tracked_idea_id) REFERENCES tracked_ideas(id) ON DELETE CASCADE,
    INDEX idx_idea_time (tracked_idea_id, snapshot_time),
    INDEX idx_feature_version (feature_set_version)
);

-- Event-based snapshots (not time-based - controls volume)
-- Triggered on: fills, profit tier boundaries, stop/target touches, significant moves
CREATE TABLE tracked_idea_snapshots (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    tracked_idea_id INT NOT NULL,
    snapshot_time DATETIME(3) NOT NULL,

    -- Trigger reason (controls when we snapshot)
    trigger_type ENUM(
        'fill',              -- on trade execution
        'tier_boundary',     -- crossed profit tier (e.g., -50%, 0%, +100%)
        'stop_touch',        -- hit stop level
        'target_touch',      -- hit target level
        'significant_move',  -- underlying moved >1%
        'periodic'           -- 5-minute periodic (sparse)
    ) NOT NULL,

    -- Position state
    mark_price DECIMAL(10,4) NOT NULL,
    underlying_price DECIMAL(10,2) NOT NULL,
    unrealized_pnl DECIMAL(10,2) NOT NULL,
    pnl_percent DECIMAL(8,4) NOT NULL,

    -- Greeks snapshot
    delta DECIMAL(8,4) DEFAULT NULL,
    gamma DECIMAL(10,6) DEFAULT NULL,
    theta DECIMAL(8,4) DEFAULT NULL,
    vega DECIMAL(8,4) DEFAULT NULL,

    -- Market context at snapshot
    vix_level DECIMAL(6,2) DEFAULT NULL,

    FOREIGN KEY (tracked_idea_id) REFERENCES tracked_ideas(id) ON DELETE CASCADE,
    INDEX idx_idea_time (tracked_idea_id, snapshot_time),
    INDEX idx_trigger (trigger_type)
);

-- User behavior tracking
CREATE TABLE user_trade_actions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tracked_idea_id INT NOT NULL,
    user_id INT NOT NULL,
    action ENUM('viewed', 'dismissed', 'starred', 'traded', 'trade_closed') NOT NULL,
    action_time DATETIME NOT NULL,

    -- Trade details if action = 'traded'
    fill_price DECIMAL(10,4) DEFAULT NULL,
    fill_quantity INT DEFAULT NULL,
    trade_id VARCHAR(36) DEFAULT NULL,

    -- Exit details if action = 'trade_closed'
    exit_price DECIMAL(10,4) DEFAULT NULL,
    realized_pnl DECIMAL(10,2) DEFAULT NULL,

    FOREIGN KEY (tracked_idea_id) REFERENCES tracked_ideas(id) ON DELETE CASCADE,
    INDEX idx_idea_user (tracked_idea_id, user_id),
    INDEX idx_user_time (user_id, action_time)
);

-- Model registry
CREATE TABLE ml_models (
    id INT AUTO_INCREMENT PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    model_version INT NOT NULL,
    model_type VARCHAR(50) NOT NULL,  -- 'gradient_boost', 'ensemble', etc.

    -- Model artifacts
    model_blob LONGBLOB NOT NULL,  -- serialized model
    feature_list JSON NOT NULL,
    hyperparameters JSON NOT NULL,

    -- Performance metrics
    train_auc DECIMAL(6,4) DEFAULT NULL,
    val_auc DECIMAL(6,4) DEFAULT NULL,
    train_samples INT DEFAULT NULL,
    val_samples INT DEFAULT NULL,

    -- Deployment state
    status ENUM('training', 'validating', 'champion', 'challenger', 'retired') NOT NULL,
    deployed_at DATETIME DEFAULT NULL,
    retired_at DATETIME DEFAULT NULL,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uk_name_version (model_name, model_version),
    INDEX idx_status (status)
);

-- A/B Experiment tracking
CREATE TABLE ml_experiments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    experiment_name VARCHAR(100) NOT NULL,
    description TEXT DEFAULT NULL,

    champion_model_id INT NOT NULL,
    challenger_model_id INT NOT NULL,
    traffic_split DECIMAL(4,2) NOT NULL DEFAULT 0.10,  -- % to challenger

    -- Experiment state
    status ENUM('running', 'concluded', 'aborted') NOT NULL,
    started_at DATETIME NOT NULL,
    ended_at DATETIME DEFAULT NULL,

    -- Results
    champion_samples INT DEFAULT 0,
    challenger_samples INT DEFAULT 0,
    champion_win_rate DECIMAL(6,4) DEFAULT NULL,
    challenger_win_rate DECIMAL(6,4) DEFAULT NULL,
    p_value DECIMAL(8,6) DEFAULT NULL,
    winner ENUM('champion', 'challenger', 'no_difference') DEFAULT NULL,

    FOREIGN KEY (champion_model_id) REFERENCES ml_models(id),
    FOREIGN KEY (challenger_model_id) REFERENCES ml_models(id),
    INDEX idx_status (status)
);
```

---

## 2. Outcome Labeling Strategy

### Risk Unit Definition (Critical for Consistency)

Define `risk_unit` at entry time and store it:
- Debit paid (for debit spreads)
- Max loss estimate (for defined-risk strategies)
- Width-based max loss (for verticals/butterflies)

```python
def compute_risk_unit(idea: TrackedIdea) -> float:
    """Compute consistent risk unit for normalization."""
    if idea.strategy == 'single':
        return abs(idea.entry_context.get('debit', 0))
    elif idea.strategy == 'vertical':
        width = idea.width or 5
        return width * 100  # max loss = width
    elif idea.strategy == 'butterfly':
        return abs(idea.entry_context.get('debit', 0))
    return abs(idea.entry_context.get('debit', 0))
```

### Multi-Target Labeling

```python
def label_outcome(idea: TrackedIdea, cohort_outcomes: List[float]) -> dict:
    """Label idea outcome for ML training with path-dependent metrics."""

    if idea.settlement_status != 'settled':
        return None

    risk_unit = compute_risk_unit(idea)
    final_pnl = idea.settlement_pnl
    max_profit = idea.max_pnl or 0
    max_loss = idea.min_pnl or 0

    # Basic labels
    labels = {
        # Binary: Was it profitable?
        'profitable': 1 if final_pnl > 0 else 0,

        # Ordinal: Profit tier
        'profit_tier': classify_profit_tier(final_pnl, risk_unit),

        # Continuous: Risk-adjusted
        'r2r_achieved': final_pnl / risk_unit if risk_unit else 0,
        'risk_unit': risk_unit,
    }

    # Path-dependent labels (from snapshots)
    labels.update({
        # Excursion metrics (often more predictive than final P&L)
        'max_favorable_excursion': max_profit / risk_unit if risk_unit else 0,
        'max_adverse_excursion': abs(max_loss) / risk_unit if risk_unit else 0,
        'time_to_max_pnl_pct': idea.time_to_max_pnl / idea.dte if idea.dte else 0,
        'time_in_drawdown_pct': idea.time_in_drawdown / idea.dte if idea.dte else 0,

        # Stop/target hits
        'hit_stop': 1 if max_loss < -risk_unit * 0.5 else 0,
        'hit_target': 1 if max_profit > risk_unit * 2 else 0,
    })

    # Regret labels (relative to cohort generated at same time)
    if cohort_outcomes:
        median_outcome = sorted(cohort_outcomes)[len(cohort_outcomes) // 2]
        labels['outperformed_median'] = 1 if final_pnl > median_outcome else 0
        labels['cohort_percentile'] = sum(1 for o in cohort_outcomes if o < final_pnl) / len(cohort_outcomes)

    return labels
```

---

## 3. ML Pipeline Architecture

**New Directory:** `services/ml_feedback/`

```
services/ml_feedback/
├── __init__.py
├── config.py              # Feature definitions, model configs
├── feature_extractor.py   # Extract features from market data
├── training_pipeline.py   # Model training orchestration
├── model_registry.py      # Model versioning, deployment
├── inference_engine.py    # Real-time scoring
├── experiment_manager.py  # A/B testing
└── jobs/
    ├── daily_feature_extraction.py
    ├── weekly_model_training.py
    └── experiment_evaluation.py
```

### Feature Extractor

```python
# services/ml_feedback/feature_extractor.py

class FeatureExtractor:
    """Extract ML features from market data at idea generation time."""

    FEATURE_GROUPS = {
        'price_action': [
            'spot_5m_return', 'spot_15m_return', 'spot_1h_return',
            'spot_1d_return', 'range_position'
        ],
        'volatility': [
            'vix_level', 'vix_regime', 'vix_term_slope',
            'iv_rank_30d', 'iv_percentile_30d'
        ],
        'gex_structure': [
            'gex_total', 'spot_vs_call_wall', 'spot_vs_put_wall',
            'spot_vs_gamma_flip'
        ],
        'market_mode': [
            'market_mode', 'bias_lfi', 'bias_direction'
        ],
        'time': [
            'minutes_since_open', 'day_of_week',
            'is_opex_week', 'days_to_monthly_opex'
        ],
        'strategy': [
            'strategy_type', 'side', 'dte', 'width',
            'strike_vs_spot', 'original_score'
        ]
    }

    async def extract_features(
        self,
        idea: TrackedIdea,
        market_data: MarketSnapshot
    ) -> dict:
        """Extract all features for an idea."""
        features = {}

        # Price action
        features['spot_price'] = market_data.spot
        features['spot_5m_return'] = self._calc_return(market_data.spot_history, 5)
        features['spot_15m_return'] = self._calc_return(market_data.spot_history, 15)
        features['range_position'] = self._range_position(
            market_data.spot, market_data.day_high, market_data.day_low
        )

        # VIX regime
        features['vix_level'] = market_data.vix
        features['vix_regime'] = self._classify_vix_regime(market_data.vix)
        features['vix_term_slope'] = (market_data.vix3m - market_data.vix) / market_data.vix

        # GEX structure
        features['gex_total'] = market_data.gex_total
        features['spot_vs_call_wall'] = (market_data.gex_call_wall - market_data.spot) / market_data.spot
        features['spot_vs_put_wall'] = (market_data.spot - market_data.gex_put_wall) / market_data.spot

        # Strategy specifics
        features['strategy_type'] = idea.strategy
        features['side'] = idea.side
        features['dte'] = idea.dte
        features['strike_vs_spot'] = (idea.strike - market_data.spot) / market_data.spot
        features['original_score'] = idea.score

        return features
```

### Training Pipeline (Walk-Forward Validation)

```python
# services/ml_feedback/training_pipeline.py

class TrainingPipeline:
    """Orchestrate model training with walk-forward validation."""

    def __init__(self, db: Database, model_registry: ModelRegistry):
        self.db = db
        self.registry = model_registry

    async def train_model_with_wfv(
        self,
        model_name: str,
        regime: str = None,  # Optional regime-specific training
        min_samples: int = 500,
        train_weeks: int = 4,
        val_weeks: int = 1
    ) -> MLModel:
        """Train with walk-forward validation (WFV)."""

        # 1. Load training data
        ideas = await self._load_settled_ideas(min_samples, regime=regime)
        features, labels = await self._prepare_dataset(ideas)

        # 2. Walk-forward validation
        # Train: weeks 1-4 → Val: week 5
        # Train: weeks 2-5 → Val: week 6
        # etc.
        wfv_results = []
        for train_start, train_end, val_start, val_end in self._wfv_windows(
            features, train_weeks, val_weeks
        ):
            train_X = features[train_start:train_end]
            train_y = labels[train_start:train_end]
            val_X = features[val_start:val_end]
            val_y = labels[val_start:val_end]

            model = self._train_gradient_boost(train_X, train_y)
            metrics = self._evaluate_with_calibration(model, val_X, val_y)
            wfv_results.append(metrics)

        # 3. Train final model on all data
        final_model = self._train_gradient_boost(features, labels)

        # 4. Aggregate WFV metrics
        avg_metrics = self._aggregate_wfv_metrics(wfv_results)

        # 5. Register with regime tag if applicable
        return await self.registry.register_model(
            name=model_name,
            model=final_model,
            features=list(features.columns),
            metrics=avg_metrics,
            regime=regime,
            feature_set_version=self.feature_extractor.version
        )

    def _evaluate_with_calibration(self, model, X, y) -> dict:
        """Evaluate with calibration metrics (more important than AUC for trading)."""
        from sklearn.calibration import calibration_curve
        from sklearn.metrics import brier_score_loss, precision_score

        probs = model.predict_proba(X)
        preds = model.predict(X)

        # Standard metrics
        metrics = {
            'auc': roc_auc_score(y['profit_tier'], probs, multi_class='ovr'),
            'accuracy': accuracy_score(y['profit_tier'], preds),
        }

        # Calibration (critical for trading decisions)
        for tier in range(4):
            tier_probs = probs[:, tier]
            tier_actual = (y['profit_tier'] == tier).astype(int)
            metrics[f'brier_tier_{tier}'] = brier_score_loss(tier_actual, tier_probs)

        # Precision on worst-loss tier (tier 0)
        metrics['precision_big_loss'] = precision_score(
            y['profit_tier'], preds, labels=[0], average='micro', zero_division=0
        )

        # Expected utility of top-k picks
        metrics['top_10_avg_pnl'] = self._top_k_utility(probs, y, k=10)
        metrics['top_20_avg_pnl'] = self._top_k_utility(probs, y, k=20)

        return metrics

    def _train_gradient_boost(self, X, y):
        """Train gradient boosting classifier."""
        from sklearn.ensemble import GradientBoostingClassifier

        model = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            subsample=0.8,
            min_samples_leaf=20,
            random_state=42
        )
        model.fit(X, y['profit_tier'])
        return model
```

### Inference Engine (Two-Tier Scoring)

At ~20k trades/day, synchronous heavy scoring will saturate. Use two-tier approach:

```python
# services/ml_feedback/inference_engine.py

class InferenceEngine:
    """Two-tier ML scoring: fast path (sync) + deep path (async)."""

    def __init__(self, model_registry: ModelRegistry):
        self.registry = model_registry
        self._fast_model = None      # Lightweight GBDT (<5ms)
        self._deep_model = None      # Full ensemble (async)
        self._feature_extractor = FeatureExtractor()
        self._context_cache = {}     # Cache market context per second

    async def score_idea_fast(
        self,
        idea: TradeIdea,
        market_context_id: str,  # Reuse cached context
        experiment_id: str = None
    ) -> FastScoringResult:
        """Fast path scoring (<5ms). Always runs synchronously."""

        # Get cached market context (computed once per second, not per idea)
        context = self._context_cache.get(market_context_id)
        if not context:
            return self._fallback_to_rules(idea)

        # Extract strategy-specific features (fast)
        strategy_features = self._extract_strategy_features(idea, context)

        # Get fast model (lightweight GBDT or logistic)
        model = await self._get_fast_model(experiment_id)
        if not model:
            return self._fallback_to_rules(idea)

        # Score
        feature_vector = self._to_vector(strategy_features, model.feature_list)
        ml_score = model.predict_score(feature_vector)

        return FastScoringResult(
            idea_id=idea.id,
            original_score=idea.score,
            ml_score=ml_score,
            final_score=self._blend_scores(idea.score, ml_score, weight=0.3),
            model_version=model.version,
            context_id=market_context_id
        )

    async def score_idea_deep(
        self,
        idea: TradeIdea,
        market_data: MarketSnapshot
    ) -> DeepScoringResult:
        """Deep path scoring (async). Updates ranking in background."""

        # Full feature extraction
        features = await self._feature_extractor.extract_all_features(idea, market_data)

        # Deep ensemble model
        model = await self._get_deep_model()
        probabilities = model.predict_proba(features)

        # More sophisticated score with confidence bounds
        ml_score = self._probability_to_score(probabilities)
        confidence = self._compute_confidence(probabilities)

        return DeepScoringResult(
            idea_id=idea.id,
            ml_score=ml_score,
            confidence=confidence,
            tier_probabilities=probabilities.tolist(),
            model_version=model.version,
            feature_snapshot_id=await self._store_features(features)
        )

    def cache_market_context(self, context_id: str, market_data: MarketSnapshot):
        """Cache market context (call once per second, not per idea)."""
        self._context_cache[context_id] = self._extract_market_features(market_data)
        # Expire old contexts
        self._cleanup_old_contexts()

    def _fallback_to_rules(self, idea: TradeIdea) -> FastScoringResult:
        """Graceful degradation when ML unavailable."""
        return FastScoringResult(
            idea_id=idea.id,
            original_score=idea.score,
            ml_score=None,
            final_score=idea.score,  # Use rule-based only
            model_version=None,
            context_id=None
        )

    def _probability_to_score(self, probs: np.ndarray) -> float:
        """Convert profit tier probabilities to 0-100 score."""
        weights = [-1.0, 0.0, 0.5, 1.0]  # big_loss, small_loss, small_win, big_win
        expected_value = sum(p * w for p, w in zip(probs, weights))
        return max(0, min(100, 50 + expected_value * 50))
```

---

## 4. Experiment Framework (with Decision Logging + Stopping Rules)

```python
# services/ml_feedback/experiment_manager.py

class ExperimentManager:
    """Manage A/B experiments with decision logging and auto-stopping."""

    async def create_experiment(
        self,
        name: str,
        challenger_model_id: int,
        traffic_split: float = 0.10,
        max_duration_days: int = 14,
        min_samples_per_arm: int = 100,
        early_stop_threshold: float = 0.01  # p-value for early stop
    ) -> Experiment:
        """Create new A/B experiment with stopping rules."""
        champion = await self.registry.get_champion_model()

        return await self.db.execute(
            """INSERT INTO ml_experiments
               (experiment_name, champion_model_id, challenger_model_id,
                traffic_split, status, started_at,
                max_duration_days, min_samples_per_arm, early_stop_threshold)
               VALUES (?, ?, ?, ?, 'running', NOW(), ?, ?, ?)""",
            [name, champion.id, challenger_model_id, traffic_split,
             max_duration_days, min_samples_per_arm, early_stop_threshold]
        )

    async def log_decision(
        self,
        idea_id: str,
        experiment_id: int,
        arm: str,
        model_version: int,
        feature_snapshot_id: int,
        scores: dict
    ) -> int:
        """Log immutable decision record for every scored idea."""
        return await self.db.execute(
            """INSERT INTO ml_decisions
               (idea_id, decision_time, model_id, model_version,
                feature_snapshot_id, original_score, ml_score, final_score,
                experiment_id, experiment_arm, selector_params_version)
               VALUES (?, NOW(3), ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [idea_id, scores['model_id'], model_version, feature_snapshot_id,
             scores['original'], scores['ml'], scores['final'],
             experiment_id, arm, scores['params_version']]
        )

    async def route_request(
        self,
        experiment_id: int,
        idea_id: str  # Use idea_id for deterministic routing
    ) -> str:
        """Deterministically route idea to champion or challenger."""
        hash_val = hash(f"{experiment_id}:{idea_id}") % 100
        experiment = await self.get_experiment(experiment_id)

        if hash_val < experiment.traffic_split * 100:
            return 'challenger'
        return 'champion'

    async def check_stopping_rules(self, experiment_id: int) -> StoppingDecision:
        """Check if experiment should stop early."""
        experiment = await self.get_experiment(experiment_id)

        # Rule 1: Max duration
        days_running = (datetime.now() - experiment.started_at).days
        if days_running >= experiment.max_duration_days:
            return StoppingDecision(stop=True, reason='max_duration')

        # Rule 2: Minimum samples
        samples = await self._get_sample_counts(experiment_id)
        if min(samples['champion'], samples['challenger']) < experiment.min_samples_per_arm:
            return StoppingDecision(stop=False, reason='insufficient_samples')

        # Rule 3: Early stopping on clear winner
        result = await self.evaluate_experiment(experiment_id)
        if result.p_value < experiment.early_stop_threshold:
            return StoppingDecision(stop=True, reason='statistical_significance', result=result)

        return StoppingDecision(stop=False, reason='continue')

    async def evaluate_experiment(self, experiment_id: int) -> ExperimentResult:
        """Evaluate with business metrics (not just win rate)."""
        from scipy import stats

        champion = await self._get_outcomes(experiment_id, 'champion')
        challenger = await self._get_outcomes(experiment_id, 'challenger')

        # Win rate comparison
        ch_win_rate = sum(1 for o in champion if o['profitable']) / len(champion)
        cl_win_rate = sum(1 for o in challenger if o['profitable']) / len(challenger)

        # Risk-adjusted return comparison
        ch_avg_rar = np.mean([o['r2r_achieved'] for o in champion])
        cl_avg_rar = np.mean([o['r2r_achieved'] for o in challenger])

        # Drawdown comparison (lower is better)
        ch_max_dd = max(o['max_adverse_excursion'] for o in champion)
        cl_max_dd = max(o['max_adverse_excursion'] for o in challenger)

        # Statistical test (Welch's t-test for RAR)
        t_stat, p_value = stats.ttest_ind(
            [o['r2r_achieved'] for o in champion],
            [o['r2r_achieved'] for o in challenger],
            equal_var=False
        )

        return ExperimentResult(
            champion_metrics={'win_rate': ch_win_rate, 'avg_rar': ch_avg_rar, 'max_dd': ch_max_dd},
            challenger_metrics={'win_rate': cl_win_rate, 'avg_rar': cl_avg_rar, 'max_dd': cl_max_dd},
            p_value=p_value,
            significant=p_value < 0.05,
            winner='challenger' if (p_value < 0.05 and cl_avg_rar > ch_avg_rar) else 'champion'
        )
```

---

## 5. Feedback Loop Mechanism

### Continuous Learning Cycle

```
1. IDEAS GENERATED
   └── Trade Selector generates ideas with original scoring
   └── ML Inference adds ml_score, final_score
   └── Features extracted and stored in ml_feature_snapshots

2. TRACKING PHASE
   └── Ideas tracked in tracked_ideas table
   └── Periodic snapshots in tracked_idea_snapshots
   └── User actions logged in user_trade_actions

3. SETTLEMENT
   └── Expiration settles ideas
   └── Outcomes labeled (profit tier, R2R achieved)
   └── Full lifecycle data available

4. TRAINING (Weekly)
   └── Load settled ideas with features
   └── Train new model version
   └── Evaluate against validation set
   └── If improved: deploy as challenger

5. EXPERIMENTATION
   └── New model gets 10% traffic
   └── Track outcomes by model
   └── Statistical evaluation
   └── Promote if significant improvement

6. MODEL UPDATE
   └── Challenger becomes champion
   └── Old champion retired
   └── Loop continues
```

### Exploration vs Exploitation

```python
class ExplorationManager:
    """Balance learning new strategies vs exploiting known good ones."""

    def __init__(self, exploration_rate: float = 0.1):
        self.exploration_rate = exploration_rate

    def should_explore(self, idea: TradeIdea) -> bool:
        """Decide if we should track less-scored ideas for learning."""
        import random

        # Always explore low-data regimes
        if self._is_low_data_regime(idea):
            return True

        # Random exploration
        if random.random() < self.exploration_rate:
            return True

        return False

    def _is_low_data_regime(self, idea: TradeIdea) -> bool:
        """Check if we have limited data for this type of trade."""
        # Query training data for similar ideas
        similar_count = self._count_similar_ideas(
            strategy=idea.strategy,
            vix_regime=idea.vix_regime,
            dte_bucket=idea.dte // 5 * 5
        )
        return similar_count < 50
```

---

## 6. Integration with Trade Selector

### Modified Scoring Flow

```python
# services/massive/intel/model_builders/trade_selector.py

class TradeSelector:
    def __init__(self, ...):
        # Existing init
        self.ml_engine = InferenceEngine(model_registry)
        self.feature_extractor = FeatureExtractor()

    async def score_and_rank_ideas(
        self,
        ideas: List[TradeIdea],
        market_data: MarketSnapshot
    ) -> List[ScoredIdea]:
        """Score ideas with both rule-based and ML scoring."""

        scored = []
        for idea in ideas:
            # 1. Original rule-based score
            original_score = self._calculate_original_score(idea)

            # 2. ML score (if model available)
            ml_result = await self.ml_engine.score_idea(idea, market_data)

            # 3. Blend scores
            final_score = self._blend_scores(
                original_score,
                ml_result.ml_score if ml_result else None
            )

            # 4. Extract and store features for future training
            features = await self.feature_extractor.extract_features(
                idea, market_data
            )

            scored.append(ScoredIdea(
                idea=idea,
                original_score=original_score,
                ml_score=ml_result.ml_score if ml_result else None,
                final_score=final_score,
                features=features
            ))

        # Sort by final score
        return sorted(scored, key=lambda x: x.final_score, reverse=True)
```

---

## 7. Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `services/journal/intel/db_v2.py` | Modify | Add ML tables: ml_decisions, pnl_events, daily_performance, ml_feature_snapshots |
| `services/ml_feedback/__init__.py` | Create | Module init |
| `services/ml_feedback/config.py` | Create | Feature definitions, versioning, circuit breaker configs |
| `services/ml_feedback/feature_extractor.py` | Create | Feature extraction with versioning, point-in-time correctness |
| `services/ml_feedback/training_pipeline.py` | Create | WFV training, regime-specific models |
| `services/ml_feedback/model_registry.py` | Create | Model versioning with feature_set_version |
| `services/ml_feedback/inference_engine.py` | Create | Two-tier scoring (fast + deep) |
| `services/ml_feedback/experiment_manager.py` | Create | A/B testing with stopping rules, decision logging |
| `services/ml_feedback/circuit_breakers.py` | Create | Safety rails, kill switches |
| `services/ml_feedback/decision_logger.py` | Create | Immutable decision record writer |
| `services/ml_feedback/pnl_ledger.py` | Create | P&L event logger, equity curve computation |
| `services/ml_feedback/jobs/materialize_daily_performance.py` | Create | Daily aggregation job |
| `services/ml_feedback/jobs/weekly_model_training.py` | Create | Weekly WFV training |
| `services/ml_feedback/jobs/drift_detection.py` | Create | Feature/model drift monitoring |
| `services/massive/intel/model_builders/trade_selector.py` | Modify | Integrate ML scoring, decision logging |

---

## 8. Implementation Order (Robust Phasing)

### Phase A: Deterministic Data Foundation
**Goal:** Ensure every decision is reproducible before any ML inference.

1. Database migration: `ml_decisions`, `pnl_events`, `daily_performance`
2. Add feature versioning fields to `ml_feature_snapshots`
3. Implement decision logger (writes to `ml_decisions` on every score)
4. Implement P&L event logger (append-only `pnl_events`)
5. Daily job to materialize `daily_performance` from events

### Phase B: Shadow Inference + Monitoring
**Goal:** ML scores but does NOT affect ranking. Build trust.

6. Feature extractor with point-in-time correctness
7. Training pipeline with walk-forward validation
8. Model registry with feature_set_version tracking
9. Fast-path inference engine (logging only, no blend)
10. Monitoring dashboards: calibration, top-k utility, drawdown

### Phase C: Conservative Blending + Experiments
**Goal:** Small ML weight with A/B testing framework.

11. Enable score blending at 10% weight
12. Experiment manager with stopping rules
13. Decision logging with experiment_arm
14. Statistical evaluation on business metrics
15. Circuit breakers implementation

### Phase D: Regime-Aware Champions + Drift Gates
**Goal:** Specialized models with automatic safeguards.

16. Regime-specific training (VIX regime, market mode)
17. Per-regime champion deployment
18. Drift detection gates (block deployment on drift)
19. Auto-promotion logic with human approval gate
20. Increase blend weight: 30% → 50%

### Phase E: Full Production + Monitoring (Ongoing)
21. Two-tier scoring (fast + deep async)
22. Feature drift alerting
23. Model performance reports
24. Continuous retraining pipeline

---

## 9. Verification

### Determinism Tests (Critical)
1. **Decision Reproducibility**: Given `ml_decisions.id`, can reconstruct exact feature values and model used
2. **Point-in-Time Correctness**: Features at `snapshot_time` use only data known at or before that time
3. **Idempotency**: Same idea scored twice → same `ml_decisions` record (deduped by idempotency key)
4. **P&L Reconstruction**: Sum of `pnl_events` for idea matches `tracked_ideas.settlement_pnl`

### Data Pipeline Tests
5. **Feature Extraction**: Generate idea, verify all features populated with correct versions
6. **Event-Based Snapshots**: Verify snapshots only on trigger events (not time-based flooding)
7. **Settlement**: Settle idea, verify all outcome labels computed correctly
8. **Daily Aggregation**: `daily_performance` matches hand-calculated from `pnl_events`

### Model Tests
9. **WFV Training**: Train with walk-forward, verify no future leakage
10. **Calibration**: Brier score < 0.25 for all profit tiers
11. **Top-k Utility**: Top 10 picks have positive avg P&L
12. **Inference Speed**: Fast path < 5ms, deep path < 50ms

### Experiment Tests
13. **Deterministic Routing**: Same idea_id always routes to same arm
14. **Decision Logging**: Every scored idea has `ml_decisions` record
15. **Stopping Rules**: Experiment auto-stops on duration/significance
16. **Business Metrics**: Evaluate on RAR, not just win rate

### Circuit Breaker Tests
17. **Daily Loss**: Trading stops when limit hit
18. **Drawdown**: Trading stops when drawdown exceeded
19. **Fallback**: ML unavailable → graceful degradation to rules-only
20. **Instant Disable**: One-click disable works, no ML influence

### Operational Checklist (What Will Bite First)
- **Leakage**: Features use future data? (verify point-in-time)
- **Non-reproducibility**: Missing decision records or versions?
- **DB Write Amplification**: Snapshot tables exploding? (verify event-based)
- **Latency**: Feature extraction repeated per idea? (verify caching)
- **Regime Shift**: Model trained on old regime dying live?

---

## 10. Key Metrics to Track

### Model Performance
- **AUC-ROC** for profit tier prediction
- **Precision/Recall** by tier
- **Feature importance** rankings
- **Prediction calibration**

### Business Metrics
- **Win rate** (overall and by tier)
- **Average R2R** achieved
- **Score correlation** with outcomes
- **User adoption** (trades taken from recommendations)

### System Health
- **Inference latency** (p50, p95, p99)
- **Feature coverage** (% ideas with all features)
- **Model freshness** (days since training)
- **Experiment velocity** (experiments concluded per month)

---

## 11. Safety Rails & Circuit Breakers

### Circuit Breakers (Hard Kill Switches)

```python
# services/ml_feedback/circuit_breakers.py

class CircuitBreaker:
    """Hard limits that override ML recommendations."""

    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self._daily_pnl = 0
        self._daily_trades = 0
        self._recent_slippage = deque(maxlen=20)

    async def check_all_breakers(self) -> BreakerStatus:
        """Check all breakers before allowing trade."""
        breakers = [
            self._check_daily_loss_limit(),
            self._check_max_drawdown(),
            self._check_order_rate(),
            self._check_slippage_anomaly(),
            self._check_model_confidence(),
        ]

        triggered = [b for b in breakers if b.triggered]
        if triggered:
            return BreakerStatus(
                allow_trade=False,
                triggered_breakers=triggered,
                action='block_all' if any(b.severity == 'critical' for b in triggered) else 'rules_only'
            )
        return BreakerStatus(allow_trade=True)

    def _check_daily_loss_limit(self) -> Breaker:
        """Max daily loss limit."""
        if self._daily_pnl < -self.config.max_daily_loss:
            return Breaker(
                name='daily_loss_limit',
                triggered=True,
                severity='critical',
                message=f'Daily P&L {self._daily_pnl} exceeds limit {-self.config.max_daily_loss}'
            )
        return Breaker(name='daily_loss_limit', triggered=False)

    def _check_max_drawdown(self) -> Breaker:
        """Max drawdown from high water."""
        drawdown = self._compute_drawdown()
        if drawdown > self.config.max_drawdown_pct:
            return Breaker(
                name='max_drawdown',
                triggered=True,
                severity='critical',
                message=f'Drawdown {drawdown:.1%} exceeds limit {self.config.max_drawdown_pct:.1%}'
            )
        return Breaker(name='max_drawdown', triggered=False)

    def _check_order_rate(self) -> Breaker:
        """Max orders per second."""
        recent_rate = self._compute_recent_order_rate()
        if recent_rate > self.config.max_orders_per_second:
            return Breaker(
                name='order_rate',
                triggered=True,
                severity='warning',
                message=f'Order rate {recent_rate}/s exceeds limit {self.config.max_orders_per_second}/s'
            )
        return Breaker(name='order_rate', triggered=False)

    def _check_slippage_anomaly(self) -> Breaker:
        """Detect abnormal slippage."""
        if len(self._recent_slippage) < 10:
            return Breaker(name='slippage_anomaly', triggered=False)

        avg_slippage = np.mean(self._recent_slippage)
        if avg_slippage > self.config.slippage_anomaly_threshold:
            return Breaker(
                name='slippage_anomaly',
                triggered=True,
                severity='warning',
                message=f'Avg slippage {avg_slippage:.2f} exceeds threshold'
            )
        return Breaker(name='slippage_anomaly', triggered=False)

    def _check_model_confidence(self) -> Breaker:
        """Don't trade in low-confidence regimes."""
        if self._current_regime_confidence < self.config.min_regime_confidence:
            return Breaker(
                name='model_confidence',
                triggered=True,
                severity='warning',
                message=f'Regime confidence {self._current_regime_confidence:.2f} below threshold'
            )
        return Breaker(name='model_confidence', triggered=False)
```

### Deployment Discipline

```
Shadow Mode (Week 1-2)
├── ML scores all ideas
├── Scores logged but DO NOT affect ranking
├── Monitor: calibration, top-k utility, drawdown metrics
└── Gate: Must pass all monitoring checks

Conservative Blend (Week 3-4)
├── ML weight: 0% → 10%
├── A/B experiment running
├── Monitor: champion vs challenger metrics
└── Gate: No degradation in business metrics

Increased Blend (Week 5+)
├── ML weight: 10% → 30% → 50%
├── Only if monitoring green
├── Regime-specific champions deployed
└── Instant rollback capability preserved
```

### Regime Protection
- Train separate champions per VIX regime
- Don't deploy regime model if < min_samples for that regime
- Drift detection gates deployment
- Alert on regime shift (model may not generalize)

### Human Oversight
- Manual review of model updates before promotion
- Weekly report: model decisions vs outcomes, feature importance shifts
- One-click disable of ML scoring (fallback to rules-only)

---

# ML Feedback Loop: Mid-Week Evaluation Plan

## Timeline

- **Thu-Fri (Feb 6-7)**: Continue data collection (~1% sampling of ML decisions)
- **Mon-Wed (Feb 10-12)**: Evaluate data, plan experiments, build performance visibility

---

## 1. Data Evaluation (Monday)

### Sample Size Analysis
```sql
-- Total decisions logged
SELECT COUNT(*) as total,
       COUNT(DISTINCT DATE(decision_time)) as days,
       COUNT(*) / COUNT(DISTINCT DATE(decision_time)) as avg_per_day
FROM ml_decisions;

-- Distribution by VIX regime (from tracked_ideas)
SELECT ti.vix_regime, COUNT(*) as count
FROM ml_decisions md
JOIN tracked_ideas ti ON md.idea_id = ti.idea_id
GROUP BY ti.vix_regime;

-- Distribution by strategy type
SELECT 
    SUBSTRING_INDEX(SUBSTRING_INDEX(idea_id, ':', 3), ':', -1) as strategy,
    COUNT(*) as count
FROM ml_decisions
GROUP BY strategy;
```

### Outcome Labeling Check
```sql
-- How many decisions have settled outcomes?
SELECT 
    COUNT(*) as total_decisions,
    SUM(CASE WHEN ti.settlement_status = 'settled' THEN 1 ELSE 0 END) as settled,
    SUM(CASE WHEN ti.settlement_status = 'settled' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as pct_settled
FROM ml_decisions md
LEFT JOIN tracked_ideas ti ON md.idea_id = ti.idea_id;

-- Settlement P&L distribution
SELECT 
    CASE 
        WHEN ti.settlement_pnl < -100 THEN 'big_loss'
        WHEN ti.settlement_pnl < 0 THEN 'small_loss'
        WHEN ti.settlement_pnl < 100 THEN 'small_win'
        ELSE 'big_win'
    END as outcome_tier,
    COUNT(*) as count,
    AVG(md.ml_score) as avg_ml_score,
    AVG(md.original_score) as avg_original_score
FROM ml_decisions md
JOIN tracked_ideas ti ON md.idea_id = ti.idea_id
WHERE ti.settlement_status = 'settled'
GROUP BY outcome_tier;
```

### Score Correlation Analysis
```sql
-- Correlation: ML score vs actual P&L
SELECT 
    CASE 
        WHEN md.ml_score < 20 THEN '0-20'
        WHEN md.ml_score < 40 THEN '20-40'
        WHEN md.ml_score < 60 THEN '40-60'
        WHEN md.ml_score < 80 THEN '60-80'
        ELSE '80-100'
    END as ml_score_bucket,
    COUNT(*) as count,
    AVG(ti.settlement_pnl) as avg_pnl,
    SUM(CASE WHEN ti.settlement_pnl > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate
FROM ml_decisions md
JOIN tracked_ideas ti ON md.idea_id = ti.idea_id
WHERE ti.settlement_status = 'settled'
GROUP BY ml_score_bucket
ORDER BY ml_score_bucket;
```

---

## 2. Experimentation Framework (Tuesday)

### Walk-Forward Validation Setup
- **Training window**: 5 trading days
- **Validation window**: 1 trading day
- **Slide**: 1 day at a time
- **Minimum samples**: 500 per training window

### A/B Experiment Structure
```python
# Experiment configuration
experiment_config = {
    "name": "ml_blend_10pct",
    "description": "Test 10% ML blend vs rules-only",
    "champion": {"type": "rules_only", "ml_weight": 0.0},
    "challenger": {"type": "blended", "ml_weight": 0.10},
    "traffic_split": 0.20,  # 20% to challenger
    "min_samples_per_arm": 200,
    "max_duration_days": 7,
    "early_stop_threshold": 0.01,  # p-value for early stop
    "primary_metric": "risk_adjusted_return",
    "guardrail_metrics": ["win_rate", "max_drawdown"]
}
```

### Key Metrics to Track

| Metric | Description | Target |
|--------|-------------|--------|
| **Calibration** | Predicted probability matches actual win rate | Brier < 0.25 |
| **Top-K Utility** | Avg P&L of top 10 ML-scored ideas | > 0 |
| **Risk-Adjusted Return** | P&L / max adverse excursion | > 1.0 |
| **Win Rate** | % of profitable trades | No degradation |
| **Max Drawdown** | Worst peak-to-trough | < 20% |

---

## 3. Performance Visibility (Wednesday)

### Dashboard Additions to Node Admin ML Lab

#### Score Distribution vs Outcomes Chart
```javascript
// X-axis: ML score buckets (0-20, 20-40, etc.)
// Y-axis: Avg P&L and Win Rate
// Visual: Bar chart with overlaid line for win rate
```

#### Win Rate by Score Bucket Table
| ML Score | Count | Avg P&L | Win Rate | vs Baseline |
|----------|-------|---------|----------|-------------|
| 0-20     | N     | $X      | X%       | -X%         |
| 20-40    | N     | $X      | X%       | -X%         |
| 40-60    | N     | $X      | X%       | +X%         |
| 60-80    | N     | $X      | X%       | +X%         |
| 80-100   | N     | $X      | X%       | +X%         |

#### ML vs Rules Comparison
- Side-by-side: ideas where ML agreed vs disagreed with rules
- Highlight cases where ML diverged significantly (>20 pts) and was right/wrong

### API Endpoints Needed
```
GET /api/admin/ml/evaluation/score-outcomes
GET /api/admin/ml/evaluation/ml-vs-rules  
GET /api/admin/ml/evaluation/regime-breakdown
```

---

## 4. Success Criteria for Going Live

Before enabling ML blend in production:

- [ ] **Sufficient data**: 1000+ settled decisions with outcomes
- [ ] **Positive correlation**: Higher ML scores → better outcomes (monotonic trend)
- [ ] **Calibration**: Brier score < 0.25 for profit tier prediction
- [ ] **Top-K value**: Top 10 ML picks outperform random selection
- [ ] **No regime blindness**: Model works across VIX regimes (not just one)
- [ ] **Experiment ready**: A/B infrastructure tested and working

---

## 5. Implementation Order

### Monday
1. Run evaluation queries above
2. Document findings in `/docs/ml-evaluation-feb10.md`
3. Identify any data quality issues

### Tuesday  
4. Implement walk-forward validation script
5. Set up experiment configuration
6. Test A/B routing logic

### Wednesday
7. Add evaluation API endpoints
8. Build dashboard visualizations
9. First experiment kickoff decision

---
