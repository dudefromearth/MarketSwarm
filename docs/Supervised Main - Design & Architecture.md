# **Supervised Main — Design & Architecture**

## **1. Problem Statement**

MarketSwarm services (e.g., **Massive**) are long-running, asynchronous, multi-task systems that depend on:

* External network connections (WebSockets, APIs)
* Redis buses
* Timed heartbeats
* Complex orchestration across multiple workers

Failures **will happen**, especially:

* Provider-initiated WebSocket restarts (1012)
* Network blips
* Partial worker crashes
* Off-hours provider maintenance

The original main.py correctly bootstraps identity, config, logging, and heartbeats—but once control is handed to the orchestrator, **there is no recovery boundary**. A fatal exception tears down the entire service.

### **Goal**

Introduce a **Supervisor Layer** that:

* Preserves the existing service contract
* Adds *controlled restart capability*
* Remains invisible during healthy operation
* Acts only when necessary
* Is reusable across all MarketSwarm services

---

## **2. Core Principle: Identity Lives at the Edge**

A critical architectural rule in MarketSwarm:

> **Service identity is established exactly once, at process entry.** 

That identity governs:

* Truth ingestion
* Config resolution
* Redis keys
* Heartbeats
* Observability

### **Consequence**

The supervisor **must not**:

* Re-run SetupBase
* Re-establish service identity
* Mutate service_name
* Reconfigure logging or shared services

Instead, the supervisor **inherits** identity via the resolved config.

---

## **3. Role of**

## **supervised_main**

supervised_main.py is a **thin wrapper**, not a new runtime.

It mirrors main.py exactly in **four critical phases**, then inserts the supervisor **after identity is locked**.

### **Lifecycle Phases**

```
┌──────────────────────────┐
│  supervised_main.py      │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ Phase 1: Bootstrap       │
│ - sys.path               │
│ - LogUtil (env only)     │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ Phase 2: Identity        │
│ - SetupBase(service)     │
│ - Truth ingestion        │
│ - Config resolution      │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ Phase 3: Shared Services │
│ - Logger promotion       │
│ - Heartbeat start        │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ Phase 4: Supervisor      │
│ - Owns orchestrator      │
│ - Restart logic          │
└──────────────────────────┘
```

Everything up to Phase 3 is **identical** to main.py.

---

## **4. Supervisor Layer — Responsibilities**

The supervisor is a **runtime control loop**, not a service initializer.

### **It Owns:**

* Orchestrator lifecycle
* Restart logic
* Failure classification
* Backoff and retry
* Escalation decisions

### **It Does NOT Own:**

* Logging setup
* Heartbeats
* Redis connections
* Config loading
* Service identity

This separation is what keeps the system clean.

---

## **5. Control Flow: Normal Operation**

```
supervised_main
    ↓
MassiveSupervisor.run()
    ↓
orchestrator.run()
    ↓
Workers run indefinitely
```

During healthy operation:

* Supervisor is dormant
* Zero overhead beyond one await boundary
* No polling, no noise

---

## **6. Control Flow: Failure & Recovery**

### **Example: WebSocket provider restart**

1. WsWorker raises ConnectionClosedError (1012)
2. Error propagates to orchestrator
3. Orchestrator exits with exception
4. Supervisor catches exception
5. Supervisor decides:

   * Recoverable? → Restart orchestrator
   * Fatal? → Escalate and stop service

⠀
### **Restart Sequence**

```
orchestrator exits
    ↓
supervisor logs incident
    ↓
optional backoff
    ↓
new orchestrator task
    ↓
system resumes
```

No heartbeat interruption

No identity reset

No Redis churn

---

## **7. Failure Classification Model (Extensible)**

Supervisors can evolve to classify failures:

|  **Failure Type**  |  **Action**  | 
|---|---|
|  Provider restart  |  Restart immediately  |
|  Network blip  |  Restart w/ backoff  |
|  Logic bug  |  Limited retries, then escalate  |
|  Config error  |  Fatal, do not restart  |
This logic belongs **only** in the supervisor.

---

## **8. Observability & Notifications**

The supervisor is the **only place** where:

* Restart counts are tracked
* Downtime is measured
* Escalation thresholds are enforced

This makes it the natural integration point for:

* Slack / email alerts
* System Redis “incident” keys
* Operator dashboards

Importantly:

* **No worker needs to know**
* **No orchestrator pollution**

---

## **9. Why This Scales Across MarketSwarm**

This pattern generalizes cleanly:

|  **Service**  |  **supervised_main**  |  **supervisor**  | 
|---|---|---|
|  massive  |  ✅  |  MassiveSupervisor  |
|  intel  |  ✅  |  IntelSupervisor  |
|  sentiment  |  ✅  |  SentimentSupervisor  |
|  execution  |  ✅  |  ExecutionSupervisor  |
Each service:

* Keeps its existing main.py
* Adds a supervised_main.py
* Implements a service-specific supervisor

Shared logic (retry, backoff, alerting) can later be abstracted into a base supervisor.

---

## **10. Operating Contract (Formalized)**

If adopted system-wide, this becomes an **operating contract**:

1. **Identity is established once**
2. **Shared services live outside supervision**
3. **Orchestrator is restartable**
4. **Supervisor is silent unless acting**
5. **Failures are observable and classified**
6. **Restart is preferred over death**

⠀
This is how you get:

* Long-running resilience
* Minimal operator burden
* Deterministic recovery
* Testable failure modes

---

## **11. Why This Matters Architecturally**

This is not just “restart logic.”

It’s the difference between:

* *Processes that run*
* *Systems that endure*

You’ve effectively separated:

* **What the system is**
* **How it survives stress**

That separation is what lets you roll this pattern out confidently across MarketSwarm.

---

If you want next steps, the natural continuations are:

* A BaseSupervisor abstraction
* Fault injection hooks
* Restart telemetry
* Supervisor contract documentation

But structurally—you’ve already made the correct architectural move.