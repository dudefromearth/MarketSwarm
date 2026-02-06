# MarketSwarm System Architecture

Complete internal reference for all services, components, data flows, and configuration. Use this document alongside "Infrastructure & Network Architecture.md" for full system understanding.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [SSE Gateway Service](#2-sse-gateway-service)
3. [Journal API Service](#3-journal-api-service)
4. [Copilot Service](#4-copilot-service)
5. [Massive Service](#5-massive-service)
6. [UI Architecture](#6-ui-architecture)
7. [Truth System & Configuration](#7-truth-system--configuration)
8. [Redis Architecture](#8-redis-architecture)
9. [Data Flow Diagrams](#9-data-flow-diagrams)

---

## 1. System Overview

MarketSwarm is a real-time options trading platform consisting of:

| Service | Port | Technology | Purpose |
|---------|------|------------|---------|
| **SSE Gateway** | 3001 | Node.js/Express | Authentication, SSE streams, REST proxy |
| **Journal API** | 3002 | Python/aiohttp | Trade logs, positions, alerts, analytics |
| **Copilot** | 8095 | Python/aiohttp | MEL, ADI, AI commentary, alert evaluation |
| **Massive** | N/A | Python/async | Market data pipeline, GEX, heatmaps |
| **UI** | 5173 | React/TypeScript | Trading dashboard |

### Redis Buses

| Bus | Port | Purpose |
|-----|------|---------|
| **system-redis** | 6379 | Truth config, heartbeats, service registry |
| **market-redis** | 6380 | Market data, models, pub/sub streams |
| **intel-redis** | 6381 | RSS, alerts, analytics |

---

## 2. SSE Gateway Service

**Location:** `/services/sse/`

### 2.1 Route Handlers

#### Authentication (`/api/auth/*`)
- `GET /api/auth/me` - Check authentication status
- `GET /api/auth/sso?sso=<jwt>` - WordPress SSO callback
- `GET /api/auth/logout` - Clear session

#### Profile (`/api/profile/*`)
- `GET /api/profile/me` - User profile from database
- `PUT /api/profile/timezone` - Update timezone preference
- `GET/PATCH /api/profile/leaderboard-settings` - Leaderboard display settings

#### Model Data (`/api/models/*`)
- `GET /api/models/spot` - All symbols with current prices
- `GET /api/models/gex/:symbol` - Gamma exposure (calls + puts)
- `GET /api/models/heatmap/:symbol` - Heatmap tiles
- `GET /api/models/candles/:symbol` - OHLC candles (5m/15m/1h)
- `GET /api/models/vexy/latest` - Latest Vexy commentary
- `GET /api/models/market_mode` - Market regime classification
- `GET /api/models/volume_profile` - Volume by price level
- `GET /api/models/bias_lfi` - Bias/LFI sentiment
- `GET /api/models/trade_selector/:symbol` - Trade recommendations

#### SSE Streams (`/sse/*`)
- `/sse/spot` - Real-time spot prices
- `/sse/gex/:symbol` - GEX updates
- `/sse/heatmap/:symbol` - Heatmap tile diffs
- `/sse/candles/:symbol` - OHLC updates
- `/sse/vexy` - Vexy commentary
- `/sse/alerts` - Alert events
- `/sse/risk-graph` - User-scoped risk graph sync
- `/sse/trade-log` - User-scoped trade events
- `/sse/all` - Combined stream (all models)

#### Admin (`/api/admin/*`)
- `GET /api/admin/stats` - Login stats, live user count
- `GET /api/admin/users` - All users with online status
- `GET /api/admin/users/:id/performance` - Trading performance
- `GET /api/admin/users/:id/activity` - Activity heatmap (30 days)
- `GET /api/admin/activity/hourly` - Peak usage hours
- `GET /api/admin/diagnostics` - System health, Redis status

### 2.2 Database Schema

```sql
-- User persistence
CREATE TABLE users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  issuer VARCHAR(32) NOT NULL,        -- "fotw" or "0-dte"
  wp_user_id VARCHAR(64) NOT NULL,
  email VARCHAR(255) NOT NULL,
  display_name VARCHAR(255),
  roles_json TEXT DEFAULT '[]',
  is_admin BOOLEAN DEFAULT FALSE,
  subscription_tier VARCHAR(128),
  timezone VARCHAR(64),
  screen_name VARCHAR(100),
  show_screen_name TINYINT DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  last_login_at DATETIME,
  UNIQUE KEY (issuer, wp_user_id)
);

-- Activity tracking (15-min snapshots)
CREATE TABLE user_activity_snapshots (
  id INT AUTO_INCREMENT PRIMARY KEY,
  snapshot_time DATETIME NOT NULL,
  user_id INT NOT NULL,
  INDEX (user_id, snapshot_time),
  FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Hourly aggregates
CREATE TABLE hourly_activity_aggregates (
  id INT AUTO_INCREMENT PRIMARY KEY,
  hour_start DATETIME NOT NULL UNIQUE,
  user_count INT DEFAULT 0
);
```

### 2.3 Authentication Flow

1. User clicks "Login with WordPress"
2. WordPress redirects to `/api/auth/sso?sso=<jwt>&next=/dashboard`
3. SSE verifies JWT with issuer-specific secret
4. User upserted in database
5. App session JWT issued, set as `ms_session` cookie
6. Redirect to `next` parameter

### 2.4 Redis Keys Consumed

```
massive:model:spot:{SYMBOL}              # Current spot price
massive:model:spot:{SYMBOL}:trail        # Price history (zset)
massive:gex:model:{SYMBOL}:calls         # GEX calls
massive:gex:model:{SYMBOL}:puts          # GEX puts
massive:heatmap:model:{SYMBOL}:latest    # Heatmap state
massive:selector:model:{SYMBOL}:latest   # Trade recommendations
massive:market_mode:model:latest         # Market regime
massive:volume_profile:spx               # Volume profile (hash)
massive:bias_lfi:model:latest            # Bias/LFI
vexy:model:playbyplay:epoch:latest       # Vexy epoch
vexy:model:playbyplay:event:latest       # Vexy event
```

---

## 3. Journal API Service

**Location:** `/services/journal/`

### 3.1 API Routes

#### Trade Logs
```
GET    /api/logs                    # List trade logs
POST   /api/logs                    # Create log
GET    /api/logs/{id}               # Get log with summary
PUT    /api/logs/{id}               # Update log
DELETE /api/logs/{id}               # Archive log
```

#### Trades
```
GET    /api/logs/{logId}/trades     # List trades (filterable)
POST   /api/logs/{logId}/trades     # Create trade
GET    /api/trades/{id}             # Get trade with events
PUT    /api/trades/{id}             # Update trade
POST   /api/trades/{id}/close       # Close with P&L
```

#### Positions (Normalized Multi-Leg)
```
GET    /api/positions               # List positions
POST   /api/positions               # Create position
PATCH  /api/positions/{id}          # Update (version check)
POST   /api/positions/{id}/fills    # Record execution
POST   /api/positions/{id}/close    # Close position
GET    /api/positions/{id}/snapshot # Full state
```

#### Orders
```
GET    /api/orders/active           # Pending orders
POST   /api/orders                  # Create order
DELETE /api/orders/{id}             # Cancel order
```

#### Journal
```
GET    /api/journal/entries                    # List entries
GET    /api/journal/entries/date/{date}        # Entry by date
POST   /api/journal/entries                    # Create entry
GET    /api/journal/retrospectives             # Weekly/monthly reviews
GET    /api/journal/calendar/{year}/{month}    # Calendar view
```

#### Playbook
```
GET    /api/playbook/entries        # Distilled wisdom
POST   /api/playbook/entries        # Create entry
GET    /api/playbook/flagged-material # From journal
```

#### Alerts
```
GET    /api/alerts                  # User's alerts
POST   /api/alerts                  # Create alert
PATCH  /api/alerts/{id}             # Update alert
DELETE /api/alerts/{id}             # Delete alert
```

#### Risk Graph
```
GET    /api/risk-graph/strategies           # List strategies
POST   /api/risk-graph/strategies           # Create strategy
PATCH  /api/risk-graph/strategies/{id}      # Update
DELETE /api/risk-graph/strategies/{id}      # Delete
GET    /api/risk-graph/templates            # Templates
POST   /api/risk-graph/templates/{id}/use   # Create from template
```

#### Analytics
```
GET    /api/logs/{logId}/analytics  # Performance summary
GET    /api/logs/{logId}/equity     # Equity curve
GET    /api/logs/{logId}/drawdown   # Drawdown curve
```

### 3.2 Alert Types

| Type | Purpose |
|------|---------|
| `price` | Spot price crosses level |
| `debit` | Position cost threshold |
| `profit_target` | P&L reaches target |
| `trailing_stop` | Drawdown from high water |
| `ai_theta_gamma` | AI-evaluated theta/gamma balance |
| `ai_sentiment` | AI-driven sentiment |
| `butterfly_entry` | OTM butterfly detection |
| `butterfly_profit_mgmt` | Butterfly exit management |

### 3.3 Key Business Logic

**P&L Calculation:**
```python
pnl = (exit_price - entry_price) * 100 * quantity  # Dollars
r_multiple = pnl / planned_risk
```

**Prices stored in cents** (BIGINT) to avoid floating-point errors.

**Optimistic Locking:** Positions have `version` field, PATCH requires `If-Match` header.

---

## 4. Copilot Service

**Location:** `/services/copilot/`

### 4.1 Subsystems

| Subsystem | Purpose |
|-----------|---------|
| **MEL** | Model Effectiveness Layer - monitors model validity |
| **ADI** | AI Data Interface - machine-readable market snapshots |
| **Commentary** | One-way AI market observations |
| **Alerts** | Queue-based alert evaluation |

### 4.2 MEL (Model Effectiveness Layer)

**Endpoints:**
- `GET /api/mel/snapshot?dte=N` - Current MEL snapshot
- `GET /api/mel/gamma` - Gamma effectiveness
- `GET /api/mel/volume-profile` - VP effectiveness
- `WS /ws/mel?dte=N` - Real-time MEL updates

**Five Models Monitored:**
1. **Gamma/Dealer** - Level respect rate, mean reversion
2. **Volume Profile** - HVN acceptance, LVN rejection
3. **Liquidity** - Absorption accuracy, sweep predictiveness
4. **Volatility** - IV/RV alignment, consistency
5. **Session** - Open discovery, midday balance

**States:**
- **VALID** (70%+): Structure present, models trusted
- **DEGRADED** (50-69%): Partial structure, selective trust
- **REVOKED** (<50%): No-trade condition

### 4.3 Commentary System

**AI Providers Supported:**
- OpenAI (GPT-4-turbo)
- Anthropic (Claude)
- Grok (x.ai)

**Trigger Types:**
- `MEL_STATE_CHANGE` - Model changed state
- `GLOBAL_INTEGRITY_WARNING` - Below 50%
- `SPOT_CROSSED_LEVEL` - Price crossed gamma/VAH/VAL/POC
- `PERIODIC` - Scheduled (5-10 min)
- `ALERT_TRIGGERED` - User alert fired

**Constraints:**
- NEVER give trading advice
- NEVER predict price movements
- Observe and describe only

### 4.4 Alert Engine

**Evaluation Loops:**
- **Fast (1s):** Price, Debit, ProfitTarget, TrailingStop
- **Slow (5s):** AI-powered evaluators

**AI Evaluators:**
- `AIThetaGammaEvaluator` - Theta harvest timing
- `AISentimentEvaluator` - Market sentiment
- `ButterflyProfitMgmtEvaluator` - Exit strategy

### 4.5 Redis Keys

```
copilot:alerts:events     # Pub/sub channel for triggered alerts
copilot:alerts:latest     # Most recent triggered alert
copilot:alerts:analytics  # Alert statistics
```

---

## 5. Massive Service

**Location:** `/services/massive/`

### 5.1 Pipeline Architecture

```
CHAIN PATH (Snapshots):
SpotWorker → ChainWorker → SnapshotWorker → Builder → ModelPublisher
   (1s)         (10s)         (event)       (tiles)    (publish)

WS PATH (Real-Time):
WsWorker → Redis Stream → WsConsumer → Hydrator → Builder
 (ticks)     (queued)      (2-5 Hz)    (state)   (tiles)
```

### 5.2 Workers

| Worker | Interval | Purpose |
|--------|----------|---------|
| **SpotWorker** | 1s | SPX, NDX, VIX, SPY prices |
| **ChainWorker** | 10s | Option chain geometry, 0-DTE subscriptions |
| **SnapshotWorker** | Event | Buckets contracts, triggers Builder |
| **WsWorker** | Real-time | WebSocket trade stream |
| **WsConsumer** | 250ms | Batches WS messages |
| **WsHydrator** | Continuous | In-memory price state |

### 5.3 Model Builders

| Builder | Interval | Output |
|---------|----------|--------|
| **TileBuilder** | Event | Butterfly/vertical/single strategies |
| **GexBuilder** | 5s | Gamma exposure per strike |
| **BiasLfiBuilder** | 5s | Directional strength, LFI score |
| **TradeSelectorBuilder** | Event | Convexity-scored recommendations |
| **VolumeProfileWorker** | 1s | SPY → SPX volume buckets |

### 5.4 Tile Strategies

| Strategy | Description |
|----------|-------------|
| `single` | Individual call or put |
| `vertical` | Debit spread (call or put) |
| `butterfly` | 3-leg: long/short 2x/long |

**Tile Key Format:** `{strategy}:{dte}:{width}:{strike}`

### 5.5 Redis Keys Published

```
massive:model:spot:{SYMBOL}              # Latest spot
massive:model:spot:{SYMBOL}:trail        # Price trail (zset)
massive:chain:latest                     # Full chain geometry
massive:heatmap:model:{SYMBOL}:latest    # Live tiles
massive:heatmap:diff:{SYMBOL}            # Pub/sub diffs
massive:gex:model:{SYMBOL}:calls         # GEX calls
massive:gex:model:{SYMBOL}:puts          # GEX puts
massive:bias_lfi:model:latest            # Bias/LFI/Mode
massive:market_mode:model:latest         # Market regime
massive:selector:model:{SYMBOL}:latest   # Trade recommendations
massive:volume_profile:spx               # Volume profile (hash)
```

### 5.6 Key Metrics

**Bias/LFI:**
- **Directional Strength** (-100 to +100): Dealer hedging supportiveness
- **LFI Score** (0-100): Liquidity flow imbalance
- **Market Mode Score** (0-100): Compression/Transition/Expansion

**GEX Flip Level:** Where net gamma changes sign - critical for regime.

---

## 6. UI Architecture

**Location:** `/ui/src/`

### 6.1 Pages

| Page | Route | Purpose |
|------|-------|---------|
| **App** | `/` | Main trading dashboard |
| **Admin** | `/admin` | User management, analytics |
| **Profile** | `/profile` | Account settings |
| **ML Lab** | `/admin/ml-lab` | Model monitoring |

### 6.2 Key Components

**Panels:**
- `TradeLogPanel` - Open/closed trades
- `MonitorPanel` - Quick trade view
- `OrderQueuePanel` - Pending orders
- `RiskGraphPanel` - Strategy visualization (echarts)
- `GexChartPanel` - Gamma exposure chart

**Charts:**
- `ActivityHeatmap` - 30-day user activity
- `PeakUsageChart` - System usage trends
- `PnLChart` - P&L performance

**Modals:**
- `AlertCreationModal` - Create alerts
- `TradeEntryModal` - New trades
- `JournalModal` - Trade reflections

### 6.3 Context Providers

| Context | Purpose |
|---------|---------|
| **AlertContext** | Alert CRUD, SSE sync |
| **TradeLogContext** | Positions, orders, legacy trades |
| **RiskGraphContext** | Strategy visualization state |
| **TimezoneContext** | User timezone |
| **PathContext** | Breadcrumb navigation |

### 6.4 SSE Subscriptions

All contexts use SSE with automatic reconnection:

```typescript
// Alert events
/sse/alerts → alert_triggered, alert_updated, ai_evaluation

// Trade events
/sse/trade-log → PositionCreated, FillRecorded, PositionClosed

// Risk graph events
/sse/risk-graph → strategy_added, strategy_updated, strategy_removed
```

### 6.5 Key Patterns

- **Optimistic Updates:** UI updates immediately, API in background
- **Idempotency:** POST requests include `Idempotency-Key` header
- **Optimistic Locking:** PATCH requests include `If-Match: {version}`
- **Event Sourcing:** SSE events include sequence numbers

---

## 7. Truth System & Configuration

**Location:** `/truth/`

### 7.1 Structure

```
truth/
├── mm_node.json              # Active node definition
├── components/               # Service configs
│   ├── massive.json         # 64 env vars
│   ├── sse.json             # 51 env vars
│   ├── journal.json
│   ├── copilot.json
│   └── ...
└── schema/
    ├── node.json            # Node schema
    └── component.json       # Component schema
```

### 7.2 Node Definition

```json
{
  "version": "3.1",
  "node": { "name": "marketswarm-local", "env": "dev" },
  "buses": {
    "system-redis": { "url": "redis://127.0.0.1:6379", "role": "system" },
    "market-redis": { "url": "redis://127.0.0.1:6380", "role": "market" },
    "intel-redis": { "url": "redis://127.0.0.1:6381", "role": "intel" }
  },
  "components": ["massive", "sse", "journal", "copilot", ...]
}
```

### 7.3 Component Definition

```json
{
  "id": "massive",
  "meta": { "name": "Massive", "kind": "basic" },
  "access_points": {
    "publish_to": [{ "bus": "market-redis", "key": "massive:*" }],
    "subscribe_to": []
  },
  "models": {
    "produces": ["spot", "gex", "heatmap", "bias_lfi"],
    "consumes": []
  },
  "heartbeat": { "interval_sec": 5, "ttl_sec": 15 },
  "env": {
    "MASSIVE_API_KEY": "...",
    "MASSIVE_SPOT_SYMBOLS": "SPX,NDX,VIX",
    ...
  }
}
```

### 7.4 Build Process

```bash
# Build truth.json from components
python scripts/build_truth.py

# Validate node definition
python scripts/build_truth.py check-node --file truth/mm_node.json

# Validate component
python scripts/build_truth.py check-component --name massive
```

**Output:** `scripts/truth.json` (40KB compiled config)

### 7.5 Loading Truth

```bash
# Load into Redis
./scripts/ms-update-truth.sh

# Or manually:
redis-cli -p 6379 SET truth "$(cat scripts/truth.json)"
```

---

## 8. Redis Architecture

### 8.1 Bus Topology

```
system-redis (6379)
├── truth                              # Compiled config
├── {service}:heartbeat                # Service liveness
└── sse:*                              # SSE gateway state

market-redis (6380)
├── massive:model:spot:*               # Spot prices
├── massive:model:spot:*:trail         # Price history
├── massive:chain:*                    # Option chains
├── massive:heatmap:*                  # Tile models
├── massive:gex:*                      # Gamma exposure
├── massive:selector:*                 # Trade recommendations
├── massive:bias_lfi:*                 # Bias/LFI
├── massive:market_mode:*              # Market mode
├── massive:volume_profile:*           # Volume profile
└── vexy:*                             # Vexy commentary

intel-redis (6381)
├── copilot:alerts:*                   # Alert state
├── rss:*                              # RSS feeds
└── enrichment:*                       # Content enrichment
```

### 8.2 Key Patterns

| Pattern | Type | Purpose |
|---------|------|---------|
| `massive:model:spot:{SYMBOL}` | String | Latest spot JSON |
| `massive:model:spot:{SYMBOL}:trail` | Sorted Set | Price history by timestamp |
| `massive:heatmap:model:{SYMBOL}:latest` | String | Full tile state |
| `massive:heatmap:diff:{SYMBOL}` | Pub/Sub | Incremental diffs |
| `massive:volume_profile:spx` | Hash | Volume by price bucket |

### 8.3 TTLs

| Key | TTL | Purpose |
|-----|-----|---------|
| Heatmap live | 72h | Weekend persistence |
| Spot trail | 48h | Historical reference |
| Heartbeat | 15s | Liveness check |

---

## 9. Data Flow Diagrams

### 9.1 Market Data Flow

```
Polygon API
    │
    ▼
┌─────────────────────────────────────────────────────┐
│                    MASSIVE                           │
│                                                      │
│  SpotWorker ──────────────────────────────┐         │
│      │                                     │         │
│      ▼                                     ▼         │
│  ChainWorker ──► SnapshotWorker ──► Builder         │
│      │                                     │         │
│      ▼                                     ▼         │
│  WsWorker ──► WsConsumer ──► Hydrator ──► Builder   │
│                                            │         │
│                                            ▼         │
│                                    ModelPublisher    │
└────────────────────────────────────────────┬────────┘
                                             │
                                             ▼
                                     market-redis
                                             │
    ┌────────────────────────────────────────┼────────────────────┐
    │                                        │                     │
    ▼                                        ▼                     ▼
SSE Gateway                              Copilot              Volume Profile
    │                                    (MEL/ADI)                 │
    ▼                                        │                     │
 Browsers                                    ▼                     │
                                     Commentary/Alerts             │
                                             │                     │
                                             └─────────────────────┘
```

### 9.2 User Request Flow

```
Browser
    │
    ▼
nginx (MiniThree - HTTP/2)
    │
    ├──► /sse/* ──────────────────► SSE Gateway (3001)
    │                                     │
    │                                     ▼
    │                               market-redis
    │
    ├──► /api/logs, /api/trades ──► Journal API (3002)
    │    /api/alerts, /api/positions      │
    │                                     ▼
    │                                   MySQL
    │
    ├──► /api/mel, /api/adi ──────► Copilot (8095)
    │    /api/commentary                  │
    │                                     ▼
    │                          AI Providers + Redis
    │
    └──► /* ──────────────────────► Static Server (5173)
                                          │
                                          ▼
                                     ui/dist/
```

### 9.3 Alert Lifecycle

```
1. User creates alert (UI)
         │
         ▼
2. Journal API stores alert (MySQL)
         │
         ▼
3. Copilot polls alerts (internal API)
         │
         ▼
4. Alert Engine evaluates conditions
   ├── Fast loop (1s): Price checks
   └── Slow loop (5s): AI evaluation
         │
         ▼
5. Condition met → Publish to Redis
   copilot:alerts:events
         │
         ▼
6. SSE Gateway receives pub/sub
         │
         ▼
7. Broadcast to user's SSE stream
         │
         ▼
8. UI updates + sound notification
```

---

## Quick Reference

### Service Ports

| Service | Port | Protocol |
|---------|------|----------|
| Static Frontend | 5173 | HTTP |
| SSE Gateway | 3001 | HTTP |
| Journal API | 3002 | HTTP |
| Copilot | 8095 | HTTP |
| system-redis | 6379 | Redis |
| market-redis | 6380 | Redis |
| intel-redis | 6381 | Redis |
| MySQL | 3306 | MySQL |

### PM2 Process Names

| Name | Service |
|------|---------|
| `fotw-static` | Node.js static server |
| `fotw-sse` | SSE Gateway |
| `fotw-journal` | Journal API |
| `fotw-copilot` | Copilot |

### Key File Locations

| Purpose | Path |
|---------|------|
| SSE Gateway | `/services/sse/src/index.js` |
| Journal API | `/services/journal/app.py` |
| Copilot | `/services/copilot/main.py` |
| Massive | `/services/massive/main.py` |
| UI | `/ui/src/` |
| Truth configs | `/truth/components/*.json` |
| Compiled truth | `/scripts/truth.json` |

---

*Last updated: February 2026*
