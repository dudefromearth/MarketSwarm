# # TradeLog–Journal as a Service  
## Deterministic Architecture & Integration with RiskGraph

This document refines and upgrades the proposed implementation plan so that **TradeLog–Journal becomes a true service-level application**, not just a frontend consolidation layer. The goal is **deterministic communication, clear ownership, and future composability** with RiskGraph (and later VolumeProfile-GEX).

---

## 0. Core Principle (Non-Negotiable)

> **UI is never the integration bus.**  
> Services communicate via **versioned contracts**, not React hooks calling each other.

- **TradeLog–Journal** owns *what happened / what was intended / what was felt*
- **RiskGraph** owns *risk, payoff, scenario artifacts*
- Communication happens via **snapshots, events, and artifact references**

---

## 1. What Claude’s Plan Gets Right

Claude’s plan is directionally correct in several important ways:

- Extracts TradeLog into a **centralized context**
- Removes duplicate state and polling
- Introduces **SSE + Redis pub/sub**
- Establishes a clean `useTradeLog()` frontend API
- Enables multi-tab / multi-device sync

These are **necessary**, but not **sufficient** for a service-level architecture.

---

## 2. Critical Gap: UI-Level “Interop” Is Not Service-Level Communication

This pattern is **not deterministic**:

```ts
const { addStrategy } = useRiskGraph();
const { getLogById } = useTradeLog();

addStrategy({...log});
```

Problems:

* UI becomes the integration layer
* No versioning, idempotency, or auditability
* RiskGraph has no authoritative contract with TradeLog

### **Required Upgrade**

**TradeLog ↔ RiskGraph communication must be API-based or event-based**, never implicit UI glue.

---

## **3. Authoritative Ownership (Bounded Contexts)**

### **TradeLog–Journal Service Owns**

* Positions / Trades (open, adjust, close)
* Orders & fills
* Journaling (notes, bias flags, reflection objects)
* Audit trail & versions
* Position snapshots (authoritative)

### **RiskGraph Service Owns**

* Risk strategies & scenarios
* Payoff curves, Greeks, tail metrics
* Strategy versioning (risk-side)
* Risk artifacts linked to positions

> **Rule:** 

> TradeLog never mutates RiskGraph state.

> RiskGraph never mutates TradeLog state.

---

## **4. Domain Model Fix: Normalize Around “Position + Legs”**

Claude’s types collapse options reality into shortcut fields:
```ts
strategy, side, strike, width, dte
```

This is fine for UI presets, but **not** for a service contract.

### **Canonical TradeLog Model**

#### **Position (Trade)**

* id
* status (planned | open | closed)
* symbol, underlying
* opened_at, closed_at
* version (monotonic)
* tags, campaign_id (optional)

#### **Leg**

* id
* position_id
* instrument_type (option | stock | future)
* expiry, strike, right
* quantity (+/-)

#### **Fill**

* id
* leg_id
* price
* quantity
* occurred_at
* recorded_at

#### **JournalEntry**

* id
* position_id
* object_of_reflection (**required**)
* bias_flags[]
* notes
* phase (setup | entry | management | exit | review)
* created_at

> Strategy type becomes **derived metadata**, not the storage primitive.

---

## **5. Deterministic API Requirements (Minimum Set)**

To support SSE + multi-device concurrency, the backend **must** add:

### **Idempotency**

* Every create/mutate endpoint accepts Idempotency-Key
* Retries never duplicate state

### **Versioning**

* Each aggregate has a version
* Mutations require If-Match: <version>
* Conflicts are explicit, not silent

### **Time Semantics**

* occurred_at (market reality)
* recorded_at (system reality)
---

## **6. TradeLog API Surface (Service-Level)**

### **Core Position Endpoints**

* POST /api/positions
* PATCH /api/positions/{id}
* POST /api/positions/{id}/fills
* POST /api/positions/{id}/close
* GET /api/positions/{id}

### **Snapshot Endpoint (for RiskGraph)**

* GET /api/positions/{id}/snapshot
```json
{
  "position_id": "uuid",
  "version": 7,
  "legs": [...],
  "fills": [...],
  "metadata": {...}
}
```

### **Journaling**

* POST /api/journal_entries
* GET /api/journal_entries?position_id=...
---

## **7. SSE: Make Events Deterministic**

Claude’s SSE payloads are too thin.

### **Required Event Envelope**
```json
{
  "event_id": "uuid",
  "event_seq": 1842,
  "type": "PositionAdjusted",
  "aggregate_type": "position",
  "aggregate_id": "uuid",
  "aggregate_version": 7,
  "occurred_at": "...",
  "payload": {...}
}
```

Benefits:

* Deduplication on reconnect
* Ordering guarantees
* Replayable streams
* Clean optimistic reconciliation
---

## **8. RiskGraph ↔ TradeLog Integration (Two Valid Patterns)**

### **Option A: Pull-Based (Simplest)**

1. RiskGraph requests snapshot:
```gcode
GET /api/positions/{id}/snapshot
```
2. RiskGraph computes risk
3. RiskGraph stores its own artifact
4. Optional callback:

```pcode
POST /api/tradelog/positions/{id}/risk-artifact
```

### **Option B: Event-Based (More Powerful)**

* TradeLog emits:

  * PositionOpened
  * FillRecorded
  * PositionAdjusted
  * PositionClosed
* RiskGraph subscribes and recomputes
* RiskGraph emits RiskArtifactComputed

TradeLog may store only the **artifact reference**, never the risk math.

---

## **9. Offline Mode: Be Explicit or Don’t Do It**

Claude proposes localStorage fallback.

⚠️ Without an **outbox + replay model**, offline writes create ghost state.

### **Recommendation**

* Phase 1: **read-only offline**
* Phase 2: queued writes with idempotency + reconciliation
---

## **10. Frontend Contexts (Still Valuable, But Secondary)**

### **TradeLogProvider Responsibilities**

* Cache server state
* Apply optimistic updates
* Reconcile via version
* Subscribe to SSE
* Never assume authority

### **RiskGraphProvider Responsibilities**

* Same pattern, but risk-side only

Contexts are **clients**, not systems of record.

---

## **11. Migration Strategy (No Big Bang)**

1. Add service endpoints + versioning
2. Introduce contexts as adapters
3. Move components to contexts
4. Enable SSE
5. Remove polling
6. Only then wire RiskGraph to snapshots/events

⠀
---

## **12. One Rule That Prevents Future Architecture Collapse**

> **All cross-app communication must survive the UI being deleted.** 

If RiskGraph and TradeLog can still coordinate headlessly:

* You built services

* If not:
* You built contexts pretending to be services
---

## **13. Next Step**

When you provide your **preliminary plan**, I’ll produce a full **Design Specification** covering:

* Bounded context definitions
* Persistence schema (positions / legs / fills / journals)
* API contracts (requests & responses)
* SSE event taxonomy + ordering rules
* Idempotency & concurrency model
* RiskGraph handshake patterns
* Migration checklist

This keeps Fly on the Wall composable, testable, and convex as it grows.