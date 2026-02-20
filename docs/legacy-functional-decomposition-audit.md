# Legacy Functional Decomposition Audit

**Date:** 2026-02-18
**Authority:** Engine Admission Spec v1.0, Canonical Schema v1.0, Canonical Conformance Transformation v1.0
**Scope:** Full codebase — where logic lives, where assumptions live, where capital math lives, where regime logic hides, where convexity heuristics are embedded.

---

## 1. SERVICE INVENTORY

### Core Services (Production)

| Service | Port | Language | LOC | Role | Redis Bus |
|---------|------|----------|-----|------|-----------|
| **SSE Gateway** | 3001 | Node.js | ~8K | HTTP gateway + SSE streams + SPA host + proxy router | system + market + intel |
| **Journal** | 3002 | Python (aiohttp) | ~21K | Trade state, DB layer, analytics, settlement, distribution | system |
| **Vexy AI** | 3005 | Python (aiohttp) | ~29K (122 files) | Cognitive kernel, Path runtime, Echo memory, capabilities | market + echo (:6382) |
| **Vexy Proxy** | 3006 | Node.js | ~500 | JWT auth proxy, AOL v2.0 doctrine routing | market |
| **Copilot** | 8095 | Python (aiohttp) | ~13K (33 files) | Alerts, MEL, ADI, Commentary | market |

### Background Services

| Service | Language | Role | Status |
|---------|----------|------|--------|
| **Massive** | Python (asyncio) | Real-time market data aggregation (Polygon WS/REST) | ACTIVE |
| **RSS Agg** | Python | Economic calendar, news feeds, sentiment scoring | ACTIVE |
| **Vigil** | Python | Event detection, anomaly monitoring | ACTIVE |
| **Mesh** | Python | Node discovery, heartbeat coordination | ACTIVE (pre-federation) |
| **Healer** | Python | Service health, error recovery, circuit breakers | ACTIVE |
| **Content Analysis** | Python | Article processing, content intelligence | ACTIVE |
| **Vexy Hydrator** | Python | Echo memory hydration, WARM snapshot building | ACTIVE |
| **ML Feedback** | Python | Model training, inference, experiment lifecycle | BETA |

### Redis Bus Topology (4 Buses)

| Bus | Port | Domain | Key Patterns |
|-----|------|--------|--------------|
| **system-redis** | 6379 | Governance | `truth`, `heartbeat:*`, `mesh:*`, `alerts:sync` |
| **market-redis** | 6380 | Market data | `massive:model:*`, `copilot:alerts:*`, `vexy_interaction:*` |
| **intel-redis** | 6381 | Intelligence | RSS feeds, enrichment, sentiment |
| **echo-redis** | 6382 | Memory | `echo:hot:*`, `echo:warm_snapshot:*`, `echo:activity:*` |

### SSE Streams (16 Total)

| Stream | Scope | Source | Description |
|--------|-------|--------|-------------|
| `/sse/spot` | Global | market-redis | Spot prices + prev close diffs |
| `/sse/gex/:symbol` | Per-symbol | market-redis | GEX calls/puts updates |
| `/sse/heatmap/:symbol` | Per-symbol | market-redis | Heatmap tile diffs |
| `/sse/candles/:symbol` | Per-symbol | market-redis | OHLC candle aggregations |
| `/sse/trade-selector/:symbol` | Per-symbol | market-redis | Trade selector recommendations |
| `/sse/vexy` | Global | market-redis | Vexy epoch + event messages |
| `/sse/bias-lfi` | Global | market-redis | Bias/LFI model updates |
| `/sse/market-mode` | Global | market-redis | Market mode classification |
| `/sse/alerts` | Global | market-redis | Alert events (copilot) |
| `/sse/risk-graph` | Per-user | market-redis | Risk graph updates |
| `/sse/trade-log` | Per-user | market-redis | Trade log lifecycle |
| `/sse/positions` | Per-user | system-redis | Position updates |
| `/sse/logs` | Per-user | market-redis | Log lifecycle events |
| `/sse/dealer-gravity` | Global | market-redis | Dealer Gravity artifact |
| `/sse/vexy-interaction` | Per-user | market-redis | Vexy cognitive progress |
| `/sse/all` | Global | (combined) | All events multiplexed |

### SSE Route Classification

| Category | Count | Type |
|----------|-------|------|
| **CLEAN_PROXY** (Journal) | 21 paths | Just forward to :3002 with optional tier gating |
| **CLEAN_PROXY** (Vexy) | 1 path | Forward to :3005 with tier headers |
| **CLEAN_PROXY** (ML Lab) | 24 routes | Forward to :3002 internal ML endpoints |
| **OWNS_LOGIC** | 68 routes | Auth, admin, models, positions, AI, imports, econ, SSE streams |
| **HYBRID** | 15 routes | Logic + proxy (RSS scoring, DG artifact, market data) |

### Exposed Debug Endpoints (Security Finding)

```
GET /api/admin/_debug/test       — No auth guard
GET /api/admin/_debug/stats      — No auth guard
GET /api/admin/_debug/users      — No auth guard, returns user data
GET /api/admin/_debug/activity/hourly — No auth guard
```

**Recommendation:** Remove or add `requireAdmin` guard.

---

## 2. ENGINE INVENTORY

### Active Engines

| Engine | Location | LOC | Status | Canonical? |
|--------|----------|-----|--------|------------|
| **Distribution Core v1.0.0** | `journal/intel/distribution_core/` | ~2K | FROZEN | YES (pure computation) |
| **AFI/Scoring Engine** | `journal/intel/afi_engine/` | ~1.5K | ACTIVE | Partial (Sharpe independent) |
| **Settlement Engine** | `journal/intel/settlement.py` | 163 | ACTIVE | NO (pre-canonical) |
| **Analytics v2** | `journal/intel/analytics_v2.py` | 513 | ACTIVE | NO (multiplier divergence) |
| **Edge Lab Analytics** | `journal/intel/edge_lab_analytics.py` | 261 | ACTIVE | YES (reads dist_core) |
| **MEL System** | `copilot/intel/mel*.py` | ~3K | ACTIVE | YES (pure market computation) |
| **Alert Engine** | `copilot/intel/alert_engine.py` | 1,110 | ACTIVE | YES (event-driven) |
| **ADI (Algo Derivative Intel)** | `copilot/intel/adi*.py` | ~860 | ACTIVE | YES (regime detection) |
| **Commentary Engine** | `copilot/intel/commentary.py` | 382 | ACTIVE | VIOLATION (direct AI calls) |
| **Prompt Alert System** | `copilot/intel/prompt_*.py` | ~1.2K | ACTIVE | YES (state machine) |
| **Algo Alert Evaluator** | `copilot/intel/algo_alert_evaluator.py` | 750 | ACTIVE | YES |
| **VexyKernel** | `vexy_ai/kernel.py` | 1,140 | ACTIVE | YES (all LLM routing) |
| **Path Runtime** | `vexy_ai/intel/path_runtime.py` | 959 | ACTIVE | YES (doctrine enforcement) |
| **Echo System** | `vexy_ai/intel/echo_*.py` | ~1.3K | ACTIVE | YES (structured forgetting) |

### Distribution Core v1.0.0 (Frozen)

| Module | Responsibility |
|--------|---------------|
| `models.py` | Frozen enums, TradeRecord, DrawdownProfile, all data contracts |
| `metric_engine.py` | Skew, kurtosis, LTC, ROCPR, profit factor, tail contribution/ratio, strategy mix |
| `regime_engine.py` | Fixed VIX threshold classification (4 structural regimes) |
| `window_engine.py` | 7/30/90/180D rolling windows, MIN_SAMPLE=10 |
| `normalization_engine.py` | Frozen normalization bounds, CII computation |
| `drawdown_engine.py` | UCSP foundation: depth/duration/recovery, peak equity series |
| `versioning.py` | Semver tagging (1.0.0), compatibility checks |
| `trade_adapter.py` | Bridges pre-canonical Trade → TradeRecord (lossy) |

**CII v1.0.0 Formula (Frozen):**
```
CII = (0.35 * normalized_skew) + (0.30 * normalized_LTC) + (0.20 * normalized_ROCPR) - (0.15 * normalized_drawdown_volatility)
```

### MEL Calculators (All Implemented)

| Calculator | Status |
|-----------|--------|
| GammaEffectivenessCalculator | ACTIVE |
| VolumeProfileEffectivenessCalculator | ACTIVE |
| LiquidityEffectivenessCalculator | ACTIVE |
| VolatilityEffectivenessCalculator | ACTIVE |
| SessionEffectivenessCalculator | ACTIVE |
| DummyCalculator | **DEAD** — imported but never instantiated, safe to remove |
| CoherenceCalculator | ACTIVE (cross-calculator validation) |

### Alert Evaluators (14 Total, All Active)

| Evaluator | Loop | Type |
|-----------|------|------|
| PriceEvaluator | Fast (1s) | Deterministic |
| DebitEvaluator | Fast (1s) | Deterministic |
| ProfitTargetEvaluator | Fast (1s) | Deterministic |
| TrailingStopEvaluator | Fast (1s) | Deterministic |
| AIThetaGammaEvaluator | Slow (5s) | AI-powered |
| AISentimentEvaluator | Slow (5s) | AI-powered |
| AIRiskZoneEvaluator | Slow (5s) | AI-powered |
| ButterflyEntryEvaluator | Fast (1s) | Deterministic |
| ButterflyProfitMgmtEvaluator | Fast (1s) | Deterministic |
| PromptDrivenEvaluator | Slow (5s) | AI-powered |
| AlgoAlertEvaluator | Slow (5s) | ML-driven |
| PortfolioPnLEvaluator | Fast (1s) | Deterministic |
| PortfolioTrailingEvaluator | Fast (1s) | Deterministic |
| GreeksThresholdEvaluator | Fast (1s) | Deterministic |

### Vexy AI Capabilities

| Capability | Status | Notes |
|-----------|--------|-------|
| chat | **ENABLED** | Dialog entrypoint, routes through kernel |
| routine | **ENABLED** | Daily briefing generation |
| journal | **ENABLED** | Trade analysis, feeds into echo |
| playbook | **ENABLED** | Playbook authoring + extraction |
| commentary | **ENABLED** | Market commentary gen |
| interaction | **ENABLED** | Two-layer dialog system |
| edge_lab | **ENABLED** | Distribution metrics, calls Distribution Core |
| aol | **ENABLED** | Doctrine validation, LPD+DCL enforcement |
| ml | **DORMANT** | Registered but not enabled |
| healer | **DORMANT** | Depends on disabled health_monitor |
| health_monitor | **DORMANT** | Not enabled |
| mesh | **DORMANT** | Pre-federation infrastructure |

### Dead / Legacy Code

| Item | Location | Status |
|------|----------|--------|
| Legacy routes (4) | `orchestrator.py:4335-4505` | DEAD — never called from v2 frontend |
| DummyCalculator | `copilot/intel/mel_calculator.py` | DEAD — imported but never instantiated |
| `models.py` (v1) | `journal/intel/models.py` | VESTIGIAL — v1 Trade class with hardcoded `*100` multiplier |
| `analytics.py` (v1) | `journal/intel/analytics.py` | VESTIGIAL — superseded by analytics_v2.py |
| `db.py` (v1) | `journal/intel/db.py` | VESTIGIAL — superseded by db_v2.py |
| Empty migration stubs | `db_v2.py` v30-v35 | VESTIGIAL — empty methods |
| `ml_feature_snapshots` table | DB | UNUSED — 0 queries |
| `user_trade_actions` table | DB | UNUSED — 0 queries |

---

## 3. DATA MODEL MAP

### Primary Models

#### Trade (PRE-CANONICAL) — `models_v2.py:106-206`

```python
Trade {
    id, log_id, user_id,
    symbol, underlying,
    strategy: str,      # 'single', 'vertical', 'butterfly', 'iron_condor' ← PRE-CANONICAL
    side: str,          # 'call', 'put', 'both' ← PRE-CANONICAL
    width: Optional[int],  # Wing distance ← PRE-CANONICAL
    strike: float,      # Center strike (scalar, not per-leg)
    quantity: int,
    entry_price, exit_price,  # cents (BIGINT)
    pnl, pnl_percent,
    planned_risk, r_multiple,
    max_profit, max_loss,
    status: 'open' | 'closed' | 'pending',
    settlement_source, settlement_method,
    tags: List[str],
    notes: str,
    ...
}
```

**Issues:**
- Stored geometry (`strategy`, `side`, `width`) — should be derived from legs
- Flat legs — cannot represent multi-leg strategies canonically
- Single scalar `strike` — not per-leg
- No Canonical Contract/Instrument reference
- `calculate_pnl()` has NO multiplier — different formula from `db_v2.close_trade()`

#### Position (CANONICAL) — `models_v2.py:1680-1770`

```python
Position {
    id, user_id, status,
    symbol, underlying, version,
    legs: List[Leg],    # Denormalized
    fills: List[Fill],  # Denormalized
}
```

**Status:** Canonical-aligned but UNDERUTILIZED. Tables exist (5 queries) but orchestrator bypasses them — creates Trade directly.

#### Leg (CANONICAL) — `models_v2.py:1773-1829`

```python
Leg {
    id, position_id,
    instrument_type: 'option' | 'stock' | 'future',
    expiry, strike, right: 'call' | 'put',
    quantity: int,  # Signed: positive=long, negative=short
}
```

#### Fill (CANONICAL) — `models_v2.py:1833-1880`

```python
Fill {
    id, leg_id,
    price: float,  # Dollars (not cents)
    quantity: int,
    occurred_at: datetime,
}
```

#### TradeRecord (Distribution Core, FROZEN) — `distribution_core/models.py`

```python
TradeRecord {
    trade_id, strategy_category: StrategyCategory,
    structure_signature: str,  # "{strategy}_{side}_{width}" (non-canonical)
    entry_timestamp, exit_timestamp,
    risk_unit, pnl_realized, r_multiple,
    regime_bucket: RegimeBucket,
    session_bucket: SessionBucket,
    price_zone: PriceZone,
    outcome_type: OutcomeType,
}
```

### Frontend Position Model (CANONICAL) — `packages/core/src/position/types.ts`

```typescript
Position {
    id, userId, symbol, underlying,
    positionType: PositionType,    // COMPUTED from legs
    direction: PositionDirection,   // COMPUTED from legs
    legs: PositionLeg[],           // SOURCE OF TRUTH
    primaryExpiration, dte,
    strike, width,                 // Convenience (for legacy compat)
}
```

**Strategy recognition:** Computed client-side in `packages/core/src/position/recognition.ts` from leg topology. No stored strategy field.

### Dual Model Architecture (Critical Finding)

| Model | Queries | Canonical? | Used By |
|-------|---------|------------|---------|
| **Trade** | 21 active | NO | Orchestrator, settlement, analytics, AFI, distribution adapter |
| **Position/Legs/Fills** | 8 total | YES | Risk graph (UI), position routes (SSE) |

These are **parallel, not unified**. The system has two ways to represent multi-leg strategies. Most code uses Trade; Position/Legs are bypassed for trade creation.

### Database Summary

**File:** `db_v2.py` — 9,407 lines, 288 methods, single `JournalDBv2` class (god-object)

| Domain | Tables | Status |
|--------|--------|--------|
| Trade Logs | 1 | CANONICAL (lifecycle management) |
| Trades | 1 | **PRE-CANONICAL** (strategy/side/width) |
| Positions/Legs/Fills | 3 | CANONICAL (underutilized) |
| Journal/Retrospectives | 4 | CANONICAL |
| Playbooks | 2 | CANONICAL |
| Tags | 1 | CANONICAL |
| Alerts (standard) | 1 | CANONICAL |
| Prompt Alerts | 2 | CANONICAL |
| Algo Alerts/Proposals | 2 | CANONICAL |
| Risk Graph | 3 | CANONICAL |
| Edge Lab | 6 | CANONICAL |
| ML | 6 | CANONICAL |
| Import Batches | 1 | CANONICAL |
| Settings/Symbols | 2 | CANONICAL |
| AFI Scores | 1 | CANONICAL |
| Echo/Activity | 4 | CANONICAL |
| **TOTAL** | ~40+ active | 90%+ geometrically sound |

**Schema migrations:** 35 methods (v1→v35), current SCHEMA_VERSION = 27. Several empty stubs (v30-v35). No rollback mechanism.

---

## 4. AFI & SCORING LOCATION MAP

### P&L Computation Paths

#### PATH 1: `db_v2.close_trade()` — AUTHORITATIVE (lines 3591-3665)

```python
multiplier = self._get_multiplier(trade.symbol)  # Symbol-aware: SPX=100, ES=50, etc.
pnl = (exit_price - trade.entry_price) * multiplier * trade.quantity
r_multiple = pnl / planned_risk  # if planned_risk > 0
```

- **Single authoritative P&L write point** — all other paths read from stored `trades.pnl`
- Called from: `orchestrator.close_trade()` (manual) + `_run_settlement_sweep()` (auto)
- Stores P&L in cents

#### PATH 2: `models_v2.Trade.calculate_pnl()` (lines 198-205)

```python
self.pnl = (self.exit_price - self.entry_price) * self.quantity  # NO MULTIPLIER
```

- **INCOMPLETE** — missing multiplier
- Called from `orchestrator.create_trade()` only when `pnl_realized` override is absent
- **Never used in production** — import path always provides override, manual close uses `db_v2.close_trade()`

#### PATH 3: Settlement → `close_trade()` (settlement.py + db_v2.py)

```
fetch_underlying_close() → compute_intrinsic(strategy, side, strike, width, spot) → cents → db_v2.close_trade()
```

- Intrinsic returns dollars/points (single contract, no multiplier)
- Multiplier applied by `close_trade()` — correct separation
- **Pre-canonical interface** (`strategy`, `side`, `width` params)

### Multiplier Divergence (Critical Finding)

| Location | Source | Mechanism | Issue |
|----------|--------|-----------|-------|
| `db_v2._get_multiplier()` | DB symbol lookup | Dynamic | **CORRECT** |
| `models_v2.calculate_pnl()` | None | `* quantity` only | **INCOMPLETE** (no multiplier) |
| `models.calculate_pnl()` (v1) | Hardcoded 100 | `* 100 * quantity` | **WRONG** (index-centric) |
| `analytics_v2._calculate_avg_r2r()` | Local dict | `{'SPX': 100, 'NDX': 100, ...}` | **DIVERGES** from DB lookup |

### Sharpe Ratio — Computed in 2 Independent Locations

| Location | Method | Issue |
|----------|--------|-------|
| `analytics_v2.py:184-210` | Per-trade returns / std * sqrt(252) | Independent — does not use Distribution Core |
| `afi_engine/scoring_engine.py` | Per-trade (not time-series) | Independent — does not use Distribution Core |

**Neither uses Distribution Core**, which is supposed to be the single source of truth for all distribution metrics.

### AFI Scoring Engine

**Location:** `journal/intel/afi_engine/scoring_engine.py`

**Components:**
- `scoring_engine.py` — Main AFI computation, WSS formula with hardcoded weights
- `component_engine.py` — Component scores (skew, gamma, theta, liquidity)
- `recency.py` — Recency weighting

**AFI Calculation in Orchestrator (lines 4506-4725):**
- 220 lines of inline score computation
- Capital integrity gate (lines 4529-4607)
- Version switching (v4 vs v5)
- Stores: `afi_score`, `afi_raw`, `wss`, `components`, `confidence`, `trend`, `leaderboard_eligible`

**AFI v4 Components:** Daily Sharpe, Drawdown Resilience, Payoff Asymmetry, Recovery Velocity

### Regime Logic Locations

| Location | Regime Source | Method |
|----------|-------------|--------|
| `distribution_core/regime_engine.py` | Fixed VIX thresholds | Deterministic (4 buckets: Zombieland ≤17, G1 17-24, G2 24-32, Chaos >32) |
| `copilot/intel/adi.py` | Market data analysis | Correlation + regime detection |
| `massive` workers | Redis keys | `massive:vix_regime`, `massive:market_mode` |
| UI | `VixRegimeCard` component | Reads from SSE, display only |

**Regime assignment:** ONCE at trade entry, never retroactive. UI aggregates Goldilocks 1+2 into single "Goldilocks" for display.

### Convexity Heuristics Location

| Metric | Authoritative Source | Other Locations |
|--------|---------------------|-----------------|
| Skew | `distribution_core/metric_engine.py` | None |
| LTC (Left Tail Contribution) | `distribution_core/metric_engine.py` | Copilot LTC breach detection (reads from dist_core) |
| CII (Convexity Integrity Index) | `distribution_core/normalization_engine.py` | None |
| Tail Contribution/Ratio | `distribution_core/metric_engine.py` | None |
| ROCPR | `distribution_core/metric_engine.py` | None |
| Drawdown Metrics | `distribution_core/drawdown_engine.py` | `analytics_v2.py` (independent max DD calc) |
| Strategy Mix | `distribution_core/metric_engine.py` | None |
| R-multiple | `db_v2.close_trade()` (computed) → `trade_adapter.py` (read) | `models_v2.calculate_pnl()` (alternate, unused) |

### Capital Math Locations

| Operation | Location | Storage |
|-----------|----------|---------|
| Starting capital | `trade_logs.starting_capital` | Cents (BIGINT) |
| Entry/exit prices | `trades.entry_price`, `trades.exit_price` | Cents (BIGINT) |
| P&L computation | `db_v2.close_trade()` | Cents (BIGINT) |
| P&L display | UI converts cents → dollars (`/ 100`) | Dollars |
| Import conversion | `orchestrator.create_trade()` | Auto-converts if < 10000 (dollars → cents) |
| Distribution Core | `trade_adapter.py` | Converts cents → dollars on ingest |

---

## 5. VEXY INTERACTION SURFACE

### Kernel Architecture

**File:** `vexy_ai/kernel.py` (1,140 LOC)

**All LLM calls route through `VexyKernel.reason()`** — verified compliant, no capability bypass detected.

**Key Methods:**
- `async reason()` — Main entry point (255 lines)
- `_assemble_system_prompt()` — Doctrine + outlet + tier assembly
- `_assemble_user_prompt()` — Context + playbooks + echo injection
- `_get_doctrine_playbook_injection()` — AOL v2.0 doctrine lookup
- `_get_playbook_injection()` — Tier-gated playbook retrieval
- `_get_echo_injection()` — Echo memory hydration
- `_capture_echo_signal()` — Structured echo writes
- `_check_despair_pre_llm()` — Pre-LLM despair detection
- `_fetch_distribution_state()` — CDIS Phase 1 (2.5s timeout)

### Two-Layer Interaction Architecture

**Layer 1 — Dialog (<250ms):** Tier gating, rate limiting, access validation, clarify/refuse/proceed
**Layer 2 — Cognition (async):** Echo hydration, agent selection, playbook injection, reasoning, validation

**Pub/Sub:** `vexy_interaction:{wp_user_id}` on market-redis

### AI Call Enforcement Audit

| Service | Enforcement | Status |
|---------|-------------|--------|
| **Vexy AI** (all capabilities) | All through `kernel.reason()` | COMPLIANT |
| **Copilot** (alerts) | Purely deterministic | N/A |
| **Copilot** (prompt evaluator) | Calls kernel via HTTP | COMPLIANT |
| **Copilot** (commentary) | **Direct AI calls via `AIProviderManager`** | **VIOLATION** |
| **SSE** (AI CSV analyzer) | Direct Claude call (`claude-3-5-haiku`) | VIOLATION (minor — utility only) |

### Commentary Kernel Bypass (Architecture Violation)

**File:** `copilot/intel/commentary.py:258`
```python
response = await self.ai_manager.generate(
    messages=messages,
    system_prompt=system,
    max_tokens=self.config.max_tokens,
    temperature=self.config.temperature,
)
```

**Impact:**
- No pre-LLM validation (despair check)
- No post-LLM validation (forbidden language)
- No echo integration
- No tier scope enforcement

**Recommendation:** Route through kernel via HTTP, or migrate Commentary to Vexy AI as capability.

### Echo Memory System

| Layer | TTL | Purpose | Status |
|-------|-----|---------|--------|
| **HOT** | 24h | Session echo, micro-signals, conversations | ACTIVE |
| **WARM** | N/A | Hydrator-built cognition snapshots (read-only) | ACTIVE |
| **COLD** | 48h | Activity trail (entropy metabolism) | ACTIVE |

**Key Patterns:**
- `echo:hot:{user_id}:conversations` — Trimmed exchanges
- `echo:hot:{user_id}:session` — Session state (24h TTL)
- `echo:hot:{user_id}:surface_state` — Latest context (1h TTL)
- `echo:activity:{user_id}:{date}` — Activity trail (48h TTL)
- `echo:warm_snapshot:{user_id}` — Hydrator snapshot

**Degraded mode:** EchoRedisClient safely returns None/empty when echo-redis unavailable.

### Hardcoded Config Issues

| Service | File | Pattern | Should Be |
|---------|------|---------|-----------|
| Vexy AI | `kernel.py:1129` | `http://localhost:3002/api/internal/distribution-state` | Truth config |
| Vexy AI | `capabilities/aol/capability.py` | `JOURNAL_BASE = "http://localhost:3002"` | Truth config |
| Vexy AI | `capabilities/edge_lab/service.py` | `JOURNAL_BASE = "http://localhost:3002"` | Truth config |
| Vexy AI | `interaction/cognition_layer.py` | `http://127.0.0.1:3007/hydrate` | Truth config |
| Vexy AI | `intel/scheduled_jobs.py` | `os.getenv("JOURNAL_MYSQL_*")` | Truth config |
| Copilot | `alert_engine.py:46` | `journal_api_url: str = "http://localhost:3002"` | Truth config |
| Copilot | `orchestrator.py` | `http://localhost:3002/api/internal/distribution-state` | Truth config |

### Monolithic Files (Decomposition Candidates)

| File | LOC | Suggested Split |
|------|-----|-----------------|
| `kernel.py` | 1,140 | Extract PromptAssembler, ValidationEngine, EchoSignalCapture |
| `path_os.py` | 1,157 | Extract EchoConsolidationEngine + PathStateValidator |
| `path_runtime.py` | 959 | Extract AgentSelector, DoctrineValidator, ORAEngine |
| `routine_briefing.py` | 902 | Extract MarketBriefingBuilder, EchoNarrative |
| `synthesizer.py` | 889 | Extract ModelRouter, PromptOptimizer |

---

## 6. UI DEPENDENCY MAP

### Routes

| Route | Component | Description |
|-------|-----------|-------------|
| `/` | `App.tsx` | Main trading dashboard |
| `/profile` | Profile page | User settings |
| `/workbench` | Placeholder | Coming soon |
| `/edge-lab` | Edge Lab page | Retrospective distribution analysis |
| `/admin` | Admin page | Admin dashboard |
| `/admin/ml-lab` | MLLab page | ML models + circuit breakers |
| `/admin/vexy` | Vexy admin | AI kernel administration |
| `/admin/economic-indicators` | Econ page | Economic indicator CRUD |
| `/admin/rss-intel` | RSS page | Feed management |
| `/admin/doctrine` | Doctrine page | AOL v2.0 governance (11 tabs) |
| `/admin/vp-editor` | VP editor | Volume profile line editor |

### Context Providers (Global State)

| Context | Purpose | SSE Source |
|---------|---------|------------|
| AlertContext | Alert definitions + instances | `/sse/alerts` |
| RiskGraphContext | Positions, Greeks, selected strategy | `/sse/risk-graph` |
| TradeLogContext | Current log, trades, events | `/sse/trade-log` |
| PositionsContext | Position list + management | `/sse/positions` |
| DealerGravityContext | Dealer positioning data | `/sse/dealer-gravity` |
| PathContext | Current Path execution state | — |
| UserPreferencesContext | Theme, timezone, display | — |
| TierGatesContext | User tier + feature gates | — |
| ApiClientContext | Sync status, network health | — |

### SSE Manager Singletons

All market data flows through SSE (HTTP/2 required — 7-8 concurrent streams exceed HTTP/1.1 limit of 6).

- `AlertSSEManager` — Alert events
- `VexyInteractionSSE` — Async cognitive progress
- `copilotAlertSSE` — Copilot alert stream
- Per-stream model state caching for diffing

### Major Dashboard Panels

| Panel | Components | Data Flow |
|-------|-----------|-----------|
| **Market Intelligence** | VixRegimeCard, BiasLfiQuadrantCard, MarketModeGaugeCard, MELStatusBar | SSE → context → render |
| **Risk Graph** (center) | PnLChart, RiskGraphPanel, PositionsList, AlertDesigner | Positions context + SSE spot + client-side Black-Scholes |
| **Heatmap** (below risk graph) | HeatmapGrid, HeatmapTile, dealer gravity overlay | SSE heatmap diffs |
| **GEX Panel** (right drawer) | GexChartPanel, VolumeProfilePrimitive | SSE GEX + candles |
| **Routine Drawer** (left) | StateOfTheMarket, MarketReadiness, AskVexyAffordance, ProcessEcho | SSE vexy + market mode |
| **Process Drawer** (right) | TradeLogPanel, TradeDetailModal, JournalModal | SSE trade-log |

### UI Direct Fetch Usage (20 files)

Files using `fetch()` directly instead of `api-client`:
- `LogManagerModal.tsx`
- `MLLab.tsx`
- `PeakUsageChart.tsx`
- `Admin.tsx`
- `VexyChat/index.tsx`
- 15 more

**Recommendation:** Audit and route all through `packages/api-client/`.

### API Client (`packages/api-client/`)

**Status:** Well-designed TypeScript abstraction layer

- `createClient()` — Main factory
- `createStrategiesEndpoint()` — Legacy strategy CRUD
- `createPositionsEndpoint()` — Leg-based position CRUD
- `SyncManager` — Offline mutation queueing
- `MutationQueue` — Persistent queue storage

### Process Bar (Phase Indicator)

**Phases (priority order):** Action → Routine → Process → Analysis → Structure → Selection → Neutral

Tracks where trader is in the workflow loop. Action phase is sticky for 4 seconds after commit events.

### Modals (20+)

TradeEntryModal, PositionCreateModal, TradeDetailModal, AlertCreationModal, JournalModal, PlaybookView, LogManagerModal, TosImportModal, TradeImportModal, ImportManager, SettingsModal, LeaderboardSettingsModal, OrphanedAlertDialog, DealerGravitySettings, RiskGraphBackdropSettings, LeaderboardView, ReportingView, TrackingAnalyticsDashboard, MonitorPanel, DailyOnboarding

### Drawers (3)

1. **Routine Drawer (Left)** — SOTm, intent, readiness, Echo, Vexy chat
2. **Process Drawer (Right)** — Trade log, journal, playbook, open loops
3. **GEX Drawer (Right)** — GEX chart + volume profile

---

## APPENDIX: CRITICAL FINDINGS SUMMARY

### Architecture Violations

| Finding | Severity | Location |
|---------|----------|----------|
| Trade model stores strategy/side/width as primary structure | **CRITICAL** | `models_v2.py:106-206` |
| Settlement uses strategy/side/width params | **CRITICAL** | `settlement.py:54-96` |
| Dual Position/Trade models (parallel, not unified) | **HIGH** | System-wide |
| Commentary bypasses VexyKernel | **HIGH** | `copilot/commentary.py:258` |
| Sharpe computed in 2 places independently (not via Distribution Core) | **MEDIUM** | `analytics_v2.py`, `afi_engine/scoring_engine.py` |
| Multiplier divergence (hardcoded dict vs DB lookup) | **MEDIUM** | `analytics_v2.py:165-168` vs `db_v2._get_multiplier()` |
| 5+ hardcoded localhost URLs across Vexy + Copilot | **MEDIUM** | See table above |
| Exposed debug endpoints without auth | **MEDIUM** | `admin.js:102-282` |
| RSS scoring duplicated (SSE admin.js + rss_relevance.py) | **LOW** | Two locations |
| DummyCalculator dead code | **LOW** | `mel_calculator.py` |
| 4 legacy routes still registered | **LOW** | `orchestrator.py:4335-4505` |

### What's Compliant

| Area | Status |
|------|--------|
| Single P&L write path (`db_v2.close_trade()`) | PASS |
| Distribution Core frozen + deterministic | PASS |
| VexyKernel routes all LLM calls (except commentary) | PASS |
| Echo memory system (HOT/WARM/COLD) | PASS |
| Settlement delegates to close_trade() (unified path) | PASS |
| Frontend Position model (canonical, leg-based) | PASS |
| Alert evaluators (all 14 implemented, no stubs) | PASS |
| MEL calculators (all 5 real, no placeholders) | PASS |
| Redis bus isolation (4 buses, no cross-wiring) | PASS |
| Tier gating enforced backend | PASS |

### Pre-Canonical Geometry (Blocks Engine Development)

Per Engine Admission Spec v1.0, these **must be resolved** before new engine development:

1. Trade model stores `strategy`, `side`, `width` as primary structure
2. Settlement `compute_intrinsic()` expects strategy/side/width parameters
3. Orchestrator creates Trade directly, ignoring Position/Legs
4. CSV import pipeline flattens geometry into Trade fields
5. No Canonical Contract/Instrument references anywhere
6. No leg-based multi-leg strategy support in primary flow

### Orchestrator Decomposition Summary

**File:** `orchestrator.py` — 7,826 lines, 154 route handlers

| Domain | Handlers | Lines | Notes |
|--------|----------|-------|-------|
| Trade CRUD | 22 | 649-1088 | Inline PnL calc, pre-canonical |
| Log Lifecycle | 14 | 118-605 | Clean |
| Analytics | 4 | 1113-1202 | Delegates to analytics_v2 |
| Import/Export | 2 (+helpers) | 1203-1502 | 187 lines inline parsing |
| Settings/Symbols/Tags | 17 | 1503-1912 | Clean |
| Journal/Retros | 13 | 2025-2593 | Clean |
| Playbook | 6 | 2922-3247 | Clean |
| Alerts (all types) | 27 | 3254-4134 | Clean |
| Legacy (dead) | 4 | 4335-4505 | Safe to remove |
| AFI/Leaderboard | 5 | 4506-4798 | 220 lines inline AFI |
| Settlement/Expiry | 4 | 4799-4930 | Delegates to settlement.py |
| Risk Graph | 14 | 4949-5495 | Clean |
| Positions | 8 | 5587-6016 | Clean |
| ML Feedback | 17 | 6017-6789 | Clean |
| Edge Lab | 16 | 7118-7695 | Clean, some duplicated camelCase conversion |
| Distribution State | 1 | 7695-7778 | Clean |

---

**Audit Complete.** This document serves as the baseline for Engine Admission Compliance and Canonical Conformance Transformation planning.
