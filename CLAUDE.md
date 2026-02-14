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
