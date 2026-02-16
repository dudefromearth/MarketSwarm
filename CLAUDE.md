# CLAUDE.md — MarketSwarm Constitutional Authority

You are operating inside the MarketSwarm system.

The following authority hierarchy governs all development:

1. architecture/00_manifest/ARCHITECTURE_ROOT.md
2. architecture/01_canonical/canonical_schema_v1.0.md
3. architecture/04_transformation/canonical_conformance_transformation_v1.0.md
4. architecture/02_doctrine/
5. Engine specifications under architecture/03_engines/

If any proposed change conflicts with these documents:
Architecture wins.

Before producing structural changes, you must:

- Identify which architecture section governs the change.
- Confirm compliance with canonical schema.
- Confirm no wrappers, adapters, compatibility layers, or dual schemas are introduced.
- Reject any divergence from canonical geometry.

No structural decisions may be made outside this authority hierarchy.

---

# **MarketSwarm — Enterprise Session Bootstrap (v4.1)**

---

# **1. System Identity**

MarketSwarm is a **real-time, distributed, stateful, event-driven options trading platform** with AI orchestration.

It is:

* Multi-service
* Multi-Redis bus
* Tier-gated
* Financially sensitive
* Production-critical
* AI-governed (Vexy Cognitive Kernel v1)

This is not a prototype system.

Every modification must assume capital impact.

---

# **2. Authoritative Sources**

| **Domain**               | **Authority**                        |
|--------------------------|--------------------------------------|
| Code                     | GitHub `main` branch                 |
| Configuration            | `truth/components/*.json`            |
| Runtime Configuration    | Redis `truth` key                    |
| AI Doctrine              | Path v4.0 markdown (`/Users/ernie/path`) |
| LLM Access               | `VexyKernel.reason()`                |
| Redis Topology           | `ms-busses.env`                      |
| Production Host          | `DudeOne.local`                      |
| Development Host         | `StudioTwo.local`                    |
No other source overrides these.

---

# **3. Infrastructure Overview**

## **Hosts**

|  **Host**        |  **Role**        |
|------------------|------------------|
|  StudioTwo.local |  Development     |
|  DudeOne.local   |  Production      |
|  MiniThree       |  Nginx reverse proxy (HTTP/2 required)  |
## **Core Services**

| **Service**    | **Port** | **Language** | **Responsibility**        |
|----------------|----------|--------------|----------------------------|
| sse            | 3001     | Node.js      | Gateway + SSE streams      |
| journal        | 3002     | Python       | Trade state + DB layer     |
| vexy_ai        | 3005     | Python       | Cognitive kernel (Vexy)    |
| vexy_proxy     | 3006     | Node.js      | JWT auth proxy to Vexy     |
| copilot        | 8095     | Python       | Alerts + MEL + Commentary  |
Background:

massive, rss_agg, vigil, mesh, healer

---

# **4. Deployment Discipline**

### **Promotion Path**

```
StudioTwo → git push → promote.sh → DudeOne
```

### **Non-Negotiable Rules**

* Git must be clean
* Never deploy directly to production
* Always rebase on DudeOne
* Always rebuild UI on production
* Always verify health endpoints
---

# **5. Redis Bus Discipline**

Three buses. No exceptions.

| **Bus**          | **Port** | **Domain**                         |
|------------------|----------|------------------------------------|
| system-redis     | 6379     | Truth + governance                 |
| market-redis     | 6380     | Market + alerts + interaction      |
| intel-redis      | 6381     | RSS + enrichment                   |
## **Redis Key Discipline**

All keys must follow:

```
{service}:{domain}:{model}:{optional_scope}
```

Examples:

```
massive:model:spot:SPX
copilot:alerts:events
vexy_interaction:{wp_user_id}
massive:econ:result:{date}:{indicator}
```

Never use ad-hoc Redis keys.

Never use redis-cli SET truth.

---

# **6. Truth System Governance**

Truth is the configuration authority.

Never edit:

```
scripts/truth.json
```

Always edit:

```
truth/components/{service}.json
```

### **Proper Update Workflow**

```
1. Edit component file
2. scripts/ms-build-truth.sh        (interactive menu)
3. scripts/ms-truth.sh              (interactive menu)
4. POST /api/reload-truth
```

**Non-interactive (scripts/automation):**

```
1. Edit component file
2. scripts/ms-build-truth.sh --build   (validates + builds truth.json)
3. scripts/ms-truth.sh --load          (loads into system-redis)
4. POST /api/reload-truth
```

No shortcuts. No manual Redis mutation.

Secrets must come from environment variables — never from truth files.

---

# **7. Authentication Boundary**

```
WordPress SSO → SSE → App JWT → ms_session cookie
```

Critical rule:

* wp_user_id ≠ users.id

All DB operations must resolve WP ID → DB ID.

---

# **8. Vexy Cognitive Kernel (v1)**

All AI calls must pass through:

```
VexyKernel.reason()
```

No capability may call call_ai() directly.

## **Kernel Enforcement Responsibilities**

* Path v4.0 enforcement
* ORA validation
* Tier semantic scope validation
* Forbidden language enforcement
* Despair detection
* Echo persistence
* Agent selection
* Post-LLM validation
* Silence support

If a new feature needs AI:

It must integrate via kernel.

Never create side-channel LLM calls.

---

# **9. Two-Layer Interaction Architecture**

## **Layer 1 — Dialog (<250ms)**

* Tier gating
* Rate limiting
* Access validation
* Clarify / refuse / proceed
* Never blocks request thread

## **Layer 2 — Cognition (async)**

* hydrate_echo
* select_playbooks
* fetch_context
* reason
* validate
* finalize

Pub/Sub channel:

```
vexy_interaction:{wp_user_id}
```

---

# **10. Tier Governance**

|  **Tier**  |  **Echo Depth**  |
|---|---|
|  Observer (trial)  |  7  |
|  Observer (restricted)  |  7  |
|  Activator  |  30  |
|  Navigator  |  90  |
|  Administrator  |  90  |
Observers:

* Limited cognitive depth
* Limited playbook injection
* Contextual upgrade reminders
* No aggressive upsell

Tier logic must never leak via frontend-only enforcement. Backend must enforce.

---

# **11. UI Architecture Discipline**

Stack:

* React 19
* TypeScript
* Vite
* ECharts
* TipTap

Rules:

* No direct EventSource in components
* Use singleton SSE managers
* Context provider order must not change
* Do not use optimistic updates with client-generated IDs
* Respect server timestamps
---

# **12. Alert System Architecture**

Alert Types:

* Threshold alerts
* Prompt alerts
* Algo alerts
* ML alerts (future)

Copilot:

* Fast loop (1s deterministic)
* Slow loop (5s AI)

Event channel:

```
copilot:alerts:events
```

Alert triggers must be idempotent and deduplicated.

---

# **13. ML & Learning System**

ML is confirmatory only.

Never prescriptive.

Confidence ladder:

```
SILENT → WEAK_ECHO → EMERGING → CONSISTENT → PERSISTENT
```

ML cannot:

* Issue trade commands
* Override user sovereignty
* Inject urgency mechanics
---

# **14. Observability & Telemetry Expectations**

Every new subsystem must define:

* Health endpoint
* Heartbeat publishing
* Structured logs
* Redis usage
* Failure mode
* Recovery behavior

Kernel must log:

* Selected agent
* Validation result
* Tier
* Latency
* Despair severity

Logs are for debugging doctrine drift — not user surveillance.

---

# **15. Failure Mode Doctrine**

When uncertain:

* Prefer silence
* Never hallucinate missing market data
* Never fabricate Redis values
* Never synthesize nonexistent positions
* Never auto-correct trades

If Redis model missing:

Return clean state — do not guess.

---

# **16. Multi-Node Forward Compatibility**

MarketSwarm is architected as a node in a future mesh.

Prepare for:

* FOTW Node (production)
* Dev Node
* Ops Node
* Generic Nodes

Avoid:

* Hardcoded filesystem assumptions
* Single-machine echo storage dependency
* Local-only rate limiting
---

# **17. Configuration Mutation Protocol**

Before changing any config:

1. Does this belong in truth?
2. Is this environment-specific?
3. Does it require Redis reload?
4. Does it affect tier gating?
5. Does it affect kernel enforcement?
6. Does it require coordinated deployment?

---

# **18. Production Freeze Checklist**

Before promoting:

* Git clean
* Truth rebuilt
* Health endpoints verified
* Redis keys stable
* No new LLM pathways
* SSE streams reconnect cleanly
* Logs inspected
* WP vs DB ID unaffected
---

# **19. Hard AI Invariants**

Never allow:

* Optimization language
* Urgency mechanics
* Prescriptive commands
* Capital allocation advice beyond tier
* Reflection without object
* Kernel bypass

Path v4.0 is executable doctrine — not prompt decoration.

---

# **20. Session Start Protocol (Mandatory)**

At beginning of session:

1. Confirm subsystem
2. Confirm dev vs prod
3. Confirm truth mutation
4. Confirm Redis bus involved
5. Confirm kernel involvement
6. Confirm tier impact
7. Confirm SSE impact

---

# **21. The Path (Doctrine OS)**

The Path is the **antifragile cognitive operating system** that governs all of MarketSwarm.

Canonical definition: *"The Path is an antifragile cognitive operating system that transforms stress into structured adaptation through sovereign reflection."*

* **Location:** `/Users/ernie/path/` (whitepaper, design spec, constitution, playbooks)
* The Path is NOT a reflection engine — it is an **anti-decay enforcement system**
* The seven-question filter is enforcement, not philosophy
* Echo is **structured forgetting** (entropy metabolism), not retention
* Convex-oriented Playbooks are apps running on The Path, giving it domain context
* Everything in MarketSwarm is an extension of The Path

**Hierarchy:** The Path governs → FOTW guides → Vexy operationalizes both.

---

# **22. FOTW Product Identity & Mission**

Fly on the Wall (FOTW) is the trader-facing product built on MarketSwarm.

**Core identity:** Doctrine-aware, NOT doctrine-enforcing. Guides traders toward structural maturity under uncertainty.

**Mission:** *"You are here to become the best loser possible."*

**Real KPIs:** Loss quality, routine adherence, discipline improvement, convexity integrity, structural maturity. Profit is second-order.

**Anti-Addiction Rules:**

* No signal-of-the-day
* No gamification, streaks, or leaderboards
* No urgency mechanics
* No prescriptive trade commands
* Sovereignty preserved always

**Three Surfaces:**

1. **Edge Lab** — retrospective distribution measurement
2. **AOL** — governance and structural integrity (observational only)
3. **Alerts** — forward-facing discipline enforcement (Tier 1: structural/algo, Tier 2: behavioral/prompt, Tier 3: governance/AOL)

---

# **23. Distribution Core v1.0.0**

**Location:** `services/journal/intel/distribution_core/`

Single authoritative source for ALL return distribution metrics. **No other module may independently compute skew, LTC, CII, or any distribution metric.** All consumers (Edge Lab, SEE, ALE, AOL) must import from here.

## **Module Structure**

| File | Responsibility |
|------|---------------|
| `models.py` | Frozen enums, TradeRecord, DrawdownProfile, all data contracts |
| `metric_engine.py` | Skew, kurtosis, LTC, ROCPR, profit factor, tail contribution/ratio, strategy mix |
| `regime_engine.py` | Fixed VIX threshold classification (4 structural regimes) |
| `window_engine.py` | 7/30/90/180D rolling windows, MIN_SAMPLE=10 |
| `normalization_engine.py` | Frozen normalization bounds, CII computation |
| `drawdown_engine.py` | UCSP foundation: depth/duration/recovery, peak equity series |
| `versioning.py` | Semver tagging (1.0.0), compatibility checks |
| `__init__.py` | Public API entry points |

## **Public API**

```python
from distribution_core import compute_distribution_metrics, compute_regime_segmented_metrics, compute_strategy_mix
```

## **CII v1.0.0 Formula (Frozen)**

```
CII = (0.35 × normalized_skew)
    + (0.30 × normalized_LTC)
    + (0.20 × normalized_ROCPR)
    - (0.15 × normalized_drawdown_volatility)
```

* ALL components pass through `normalization_engine` — no mixing raw + normalized
* Result clamped to [0, 1]
* CII must **NEVER** include Sharpe
* < 0.5 → Convexity at risk
* < 0.4 → Structural warning
* < 0.3 → Convexity collapse
* Changing weights or bounds requires major version bump

## **Frozen Normalization Bounds**

| Component | Raw Range | Normalized | Cap |
|-----------|-----------|------------|-----|
| Skew | [-1, +1] | [0, 1] | — |
| LTC | [0, 1] | [0, 1] | clamped |
| ROCPR | [0, cap] | [0, 1] | 2.0 |
| Drawdown Vol | [0, cap] | [0, 1] | 1.0 |

## **4 Structural Regimes (Fixed VIX Thresholds)**

| Regime | VIX Range | Internal Enum |
|--------|-----------|---------------|
| Zombieland | VIX ≤ 17 | `ZOMBIELAND` |
| Goldilocks 1 | 17 < VIX ≤ 24 | `GOLDILOCKS_1` |
| Goldilocks 2 | 24 < VIX ≤ 32 | `GOLDILOCKS_2` |
| Chaos | VIX > 32 | `CHAOS` |

* No percentiles. No rolling history. Pure deterministic.
* Regime assigned ONCE at trade entry, never retroactive.
* UI aggregates Goldilocks 1+2 into single "Goldilocks" for display.

## **3D Convexity Model**

Every trade maps to a coordinate: **(T, P, Γ)**

* **T** = `SessionBucket` (Morning, Afternoon, Closing) — time axis
* **P** = `PriceZone` (Below/Inside/Above Convex Band) — price axis
* **Γ** = `RegimeBucket` (Zombieland/Goldilocks 1&2/Chaos) — gamma/regime axis

Phase 0: Coordinates captured at entry. Phase 1+: Full 3D slicing.

## **Strategy Categories (Frozen Enum)**

* `CONVEX_EXPANSION` — OTM flies, gamma scalps, convex stacks
* `EVENT_COMPRESSION` — Pre-event iron flies, event condors
* `PREMIUM_COLLECTION` — Short straddles, iron condors, ratio spreads

## **Base Unit**

R-multiple: `R = pnl_realized / risk_unit`. Never raw PnL. `risk_unit > 0` enforced. R-multiple consistency validated on TradeRecord creation.

## **Design Constraints**

* Pure computation. No HTTP, no Redis, no UI, no IO.
* Deterministic. Same inputs → identical outputs. Injectable `reference_time` for replay.
* Minimum sample: ≥10 trades per window, else metrics return None.
* Empty inputs return zero-filled safe structures, never raise.
* Performance: <200ms for 10K trades (verified by benchmark test).
* 52 unit tests in `distribution_core/tests/`.

---

# **24. CDIS (Continuous Distribution Intelligence System)**

The closed loop that transforms FOTW from a strategy platform into a Distribution Engineering Lab.

```
Trade → ALE → Echo → Edge Lab → SEE → AOL → Trader adapts → next trade
```

**No loop bypass allowed.** Every organ must participate.

**Four Organs:**

1. **ALE** (Alert Lifecycle Engine) — execution discipline, state machine
2. **Edge Lab** — measurement engine, calls Distribution Core
3. **SEE** (Strategy Evolution Engine) — advisory simulation
4. **AOL** — governance, tone, structural integrity (observational only)

**Distribution State Vector** (shared nervous system):

```
{ skew, ltc, cii, drawdown_profile, regime_sensitivity, strategy_mix_exposure }
```

---

# **25. Quantitative Doctrine**

## **The North Star**

Engineer **positively skewed return distributions**. Small controlled left tails, rare meaningful right-tail expansions. This is not about winning more — it's about engineering the shape of outcomes.

## **Metric Hierarchy (Non-Negotiable Order)**

1. **Survival** (Tier 1) — Max drawdown, LTC, halt compliance. If this fails, nothing else matters.
2. **Distribution Shape** (Tier 2) — Skew, tail contribution, tail ratio, kurtosis. The heart.
3. **Risk Efficiency** (Tier 3) — ROCPR, profit factor, Sortino. Secondary to skew. Always.
4. **Smoothness** (Tier 4) — Sharpe. Never displayed alone. Must pair with skew + drawdown.

Win rate **never appears** as a primary metric.

## **Guardrail Rules**

1. Sharpe ↑ + Skew ↓ → "Smoothness increasing at cost of convexity"
2. ROCPR ↑ + MaxDD ↑ → "Risk concentration rising"
3. Win Rate ↑ + AvgW/AvgL ↓ → "Fragile win-rate drift"
4. Tail Contribution collapses → "Right tail suppression"
5. LTC drops → Immediate Tier 1 warning

## **Mandatory Visualization Pairings**

No single metric panels allowed. Always paired:

* Sharpe + Skew
* AvgW/AvgL + Tail Contribution
* Drawdown + Regime State
* ROCPR + Max Risk Deployed

## **UCSP (Universal Compounding Stability Protocol)**

Drawdown elasticity > 1 when scaling position size — drawdowns amplify superlinearly. Distribution Core's DrawdownEngine exposes primitives (depth series, peak equity, recovery metrics) for governance systems to detect instability before it compounds.

## **Survival First Hard Stop**

If Tier 1 breaches threshold: CII is muted, tail metrics contextual only. System prompts: *"Stabilize survival before pursuing expansion."*

---

# **26. Formal System Architecture Diagram**

## **26.1 High-Level Topology**

```
INTERNET
                                          │
                                          ▼
                               ┌───────────────────┐
                               │     MiniThree     │
                               │   Nginx (HTTP/2)  │
                               │ flyonthewall.io   │
                               └─────────┬─────────┘
                                         │
                ┌────────────────────────┼────────────────────────┐
                │                        │                        │
                ▼                        ▼                        ▼
        ┌─────────────┐          ┌─────────────┐          ┌─────────────┐
        │ SSE Gateway │          │ Vexy Proxy  │          │  Copilot    │
        │   :3001     │          │   :3006     │          │   :8095     │
        │  Node.js    │          │  Node.js    │          │   Python    │
        └──────┬──────┘          └──────┬──────┘          └──────┬──────┘
               │                        │                        │
               │                        ▼                        │
               │                ┌─────────────┐                   │
               │                │  Vexy AI    │◄──────────────────┘
               │                │   :3005     │
               │                │   Python    │
               │                └─────────────┘
               │
               ▼
        ┌─────────────┐
        │   Journal   │
        │    :3002    │
        │   Python    │
        └─────────────┘
```

---

## **26.2 Background & Coordination Layer**

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
 │ Massive  │   │ RSS Agg  │   │  Vigil   │   │   Mesh   │   │  Healer  │
 │ (Market) │   │ (Intel)  │   │ (Events) │   │ (Coord)  │   │ (Health) │
 └────┬─────┘   └────┬─────┘   └────┬─────┘   └────┬─────┘   └────┬─────┘
      │               │               │               │               │
      └───────────────┴───────────────┴───────────────┴───────────────┘
                              │
                              ▼
                        Redis Buses
```

---

## **26.3 Redis Bus Segmentation**

```
system-redis :6379
    - truth
    - service:heartbeat
    - mesh:broadcast
    - alerts:sync

market-redis :6380
    - massive:model:*
    - copilot:alerts:events
    - vexy_interaction:{wp_id}
    - som:unscheduled_developments

intel-redis :6381
    - RSS ingestion
    - enrichment artifacts
    - sentiment scoring
```

**Invariant:** Buses are isolated by purpose. Never cross-wire.

---

# **27. Data Flow Diagrams**

---

## **27.1 Market Engine → UI Flow**

```
Polygon WebSocket / REST APIs
            │
            ▼
         Massive
   (spot / chain / GEX / heatmap)
            │
            ▼
      market-redis
            │
            ▼
      SSE Gateway :3001
            │
            ▼
  Browser EventSource (/sse/*)
            │
            ▼
  React Context Providers
            │
            ▼
 Charts / Risk Graph / Panels
```

### **Design Constraints**

* Massive writes model state.
* SSE streams diffs, not full payloads.
* UI never polls Massive directly.
* HTTP/2 required (7–8 concurrent streams).
---

## **27.2 Alert System Data Flow**

### **Fast Loop (Deterministic — 1s)**

```
massive:model:*  (market-redis)
            │
            ▼
     Copilot Alert Engine
            │
            ▼
 copilot:alerts:events (pub/sub)
            │
            ▼
       SSE Gateway
            │
            ▼
 alertSSEManager (singleton)
            │
            ▼
 AlertContext / AlgoAlertContext
```

### **Slow Loop (AI — 5s)**

```
Copilot
   │
   ▼
AIProviderManager
   │
   ▼
shared/ai_client.py
   │
   ▼
LLM Provider
   │
   ▼
Alert Evaluation Result
   │
   ▼
copilot:alerts:events
```

**Invariant:**

* Fast loop must never block.
* AI loop must not affect deterministic evaluation timing.
* ML is confirmatory, never prescriptive.
---

## **27.3 Vexy AI Interaction Flow**

```
Browser
  │
  ▼
/api/vexy/interaction
  │
  ▼
Vexy Proxy (JWT validation)
  │
  ▼
Vexy AI
  │
  ▼
Dialog Layer (<250ms)
  ├─ Rate limit
  ├─ Tier check
  ├─ Clarify / Refuse / Proceed
  ▼
Async Job Created
  │
  ▼
VexyKernel.reason()
  │
  ├─ PathRuntime doctrine load
  ├─ Agent selection
  ├─ Echo hydration
  ├─ Playbook injection
  ▼
shared/ai_client.py
  ▼
LLM Provider
  ▼
Post-LLM Validation
  ├─ ORA semantic check
  ├─ Forbidden language check
  ├─ Tier scope enforcement
  ├─ Despair detection
  ▼
vexy_interaction:{wp_user_id}
  │
  ▼
SSE → vexyInteractionSSE singleton
  │
  ▼
UI Update
```

**Non-Negotiable Rule:**

All LLM calls must route through VexyKernel.reason(). No exceptions.

---

## **27.4 AI + Market + Alerts Cross-System View**

```
Massive (Market Models)
                      │
                      ▼
                market-redis
                      │
        ┌─────────────┼─────────────┐
        ▼                             ▼
   Copilot (Alerts)               Vexy AI
        │                             │
        ▼                             ▼
  copilot:alerts:*           vexy_interaction:{id}
        │                             │
        ▼                             ▼
       SSE Gateway  ←───────────────→ Browser
```

This represents the **three intelligent subsystems**:

1. Market intelligence (Massive)
2. Deterministic + AI alerts (Copilot)
3. Reflective cognition (Vexy)

All coordinated through Redis and SSE.

---

End of Enterprise Bootstrap v4.1
