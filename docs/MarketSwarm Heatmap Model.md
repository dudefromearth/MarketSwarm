# **MarketSwarm Heatmap Model**

**Canonical Architecture & Operational Guide** 

---

## **1. Purpose & Scope**

The **Heatmap model** is the core real-time options surface within the MarketSwarm system.

It visualizes **strategy cost, convexity, and structure** across strikes, widths, and expirations.

This document defines:

* The **data pipeline**

* The **model geometry**

* The **contracts**

* The **epoch rules**

* The **update mechanics**

* The **calculation lifecycle**

* The **Redis integration**

* The **interactions with Chain Snapshots and WebSocket (WS)**

This is the **system of record** for Heatmap behavior.

---

## **2. Conceptual Overview**

The Heatmap is a **3D model**:

|  **Axis**  |  **Meaning**  | 
|---|---|
|  **X**  |  Width (butterfly / vertical width)  | 
|  **Y**  |  Primary Strike  | 
|  **Z**  |  DTE (Expiration / temporal depth)  | 
You can think of the heatmap as:

> **A stack of 2D planes (cards)** 

> where each plane represents a **single DTE**,

> and the stack represents **temporal depth**.

---

## **3. Core Objects**

### **3.1 Contracts (Atomic Layer)**

**Contracts** are raw options instruments:

* Calls and puts

* Identified by strike + expiration

* Updated via:

  * Chain Snapshots (slow, authoritative)

  * WebSocket (fast, incremental)

Contracts:

* Are **NOT tiles**

* Are **NOT strategies**

* Are **direct WS targets**

They live as **contract rows** inside the heatmap geometry.

---

### **3.2 Tiles (Derived Strategy Layer)**

**Tiles** exist at the intersection of:

* Strike (Y)

* Width (X)

* DTE (Z)

A Tile represents **a strategy**, not a contract.

Each Tile:

* References multiple contracts

* Computes **debit/credit**

* Can represent:

  * Call Butterfly

  * Put Butterfly

  * Vertical

  * Single (width = 0)

Tiles **do not store contracts**, they **reference them**.

---

### **3.3 Tile Attributes (Minimal Required)**

Tiles contain:

* primary_strike

* width

* dte

* strategy_type

* debit_or_credit

* dirty_flag

* calculated_flag

* color (assigned externally)

* Sufficient metadata to:

  * Render popup

  * Generate ToS-passable order

Tiles are **model outputs**, not ingestion artifacts.

---

## **4. Data Inputs**

### **4.1 Chain Snapshots (Authoritative, Slow)**

Chain Snapshots:

* Define **geometry**

* Define **strike range**

* Define **available expirations**

* Define **contract universe**

They are:

* Slow (seconds)

* Discrete

* Complete

* Canonical

> **The Chain is the master.** 

---

### **4.2 WebSocket Stream (Incremental, Fast)**

WS provides:

* Bid/ask updates

* Trade updates

* Contract-level changes

It:

* Operates at high frequency

* Updates existing contracts

* Never changes geometry

> WS is a **hydration and mutation stream**, not a geometry source.

---

## **5. Geometry & Epochs**

### **5.1 Geometry Definition (Heatmap)**

Geometry is defined by:

* Strike ladder

* Strike spacing

* Width domain

* DTE set

This geometry determines:

* Heatmap surface dimensions

* WS subscription filters

* Tile coordinate system

---

### **5.2 Epoch Rule (Critical)**

> **A new Heatmap epoch is created ONLY when geometry changes.** 

#### **Triggers for New Epoch**

* Strike range expands/contracts

* Strike spacing changes

* Width domain changes

* DTE set changes

#### **Non-Triggers (NO new epoch)**

* WS updates

* Price changes

* IV changes

* Greeks

* Volume

* OI

* Tile recalculations

* Dirty/clean transitions

This guarantees:

* Visual continuity

* Incremental computation

* Stable WS subscriptions

---

## **6. Pipeline Stages (End-to-End)**

### **Stage 1 — Chain Snapshot Ingest**

* ChainWorker fetches snapshot

* Geometry is extracted

* Geometry hash is computed

**Decision**:

* Geometry changed → new epoch

* Geometry unchanged → continue

---

### **Stage 2 — Geometry Preparation**

If geometry changed:

* Heatmap surface is pre-allocated

* WS filter is prepared

* Contract arrays are initialized

This happens **before WS pause**.

---

### **Stage 3 — WS Pause & Switch-Over**

* WS is briefly paused

* New filter is applied

* New heatmap surface is swapped in

* WS resumes immediately

This minimizes data loss and churn.

---

### **Stage 4 — WS Hydration**

* Contracts are updated in-place

* Contract rows are marked **dirty**

* No tile calculations occur yet

---

### **Stage 5 — Snapshot Window (Freeze)**

After a configurable window (e.g. 200ms):

* WS updates are frozen

* Current contract state is snapshotted

This creates a **stable calculation boundary**.

---

### **Stage 6 — Dirty Row Detection**

Only rows with changed contracts are marked:

* Dirty rows → eligible for calculation

* Clean rows → skipped

This is the key to performance.

---

### **Stage 7 — Tile Calculation**

For each dirty row:

* Tiles are recalculated

* Debit/credit is computed

* Strategy validity is checked

Tiles are marked:

* calculated = true

* dirty = false

---

### **Stage 8 — Model Emission**

Only **affected tiles** are:

* Wrapped in a JSON model schema

* Published to Redis model keys

This is **sparse, incremental output**.

---

## **7. Redis Contracts (Heatmap)**

### **7.1 Input Keys**

* massive:chain:snapshot:*

* massive:chain:latest:*

* massive:ws:stream

---

### **7.2 Heatmap Model Output (Example)**

```
massive:heatmap:model
massive:heatmap:model:{epoch}
massive:heatmap:model:{epoch}:{dte}
```

(Exact keying is model-specific but must remain stable per epoch.)

---

### **7.3 Tile Emission Contract (Conceptual)**

```
{
  "epoch": "...",
  "dte": "...",
  "strike": 6900,
  "width": 50,
  "strategy": "call_butterfly",
  "debit": 1.25,
  "calculated_at": 1767099000.123
}
```

---

## **8. Separation of Concerns**

|  **Component**  |  **Responsibility**  | 
|---|---|
|  ChainWorker  |  Geometry + authority  |
|  WS Worker  |  Fast contract hydration  |
|  Heatmap Builder  |  Surface + tile orchestration  |
|  Decomposer  |  Snapshot → model-specific format  |
|  Colorizer  |  External, stateless  |
|  UI  |  Consumer only  |
This prevents cross-contamination and keeps the system extensible.

---

## **9. Model Extensibility**

The Heatmap is **one model** in a larger ecosystem.

Other models:

* GEX → Chain-only updates

* Volume Profile → Spot-driven

* Others → Mixed inputs

Each model:

* Defines its own epoch rules

* Defines its own decomposer

* Writes to its own Redis contract

The pipeline remains consistent.

---

## **10. Key Design Principles (Non-Negotiable)**

* Chain is the master

* Geometry drives epochs

* WS never defines structure

* Calculations are dirty-driven

* Models emit sparsely

* Redis is the system backbone

* Visual continuity matters

* Performance comes from restraint

---

## **11. Mental Model Summary**

> **Chain defines the board** 

> **WS moves the pieces** 

> **Tiles compute only when touched** 

> **Epochs change only when the board changes** 

This is how MarketSwarm achieves **authority, stability, and real-time power**.

---

If you want, the next natural documents would be:

* **Heatmap JSON schema**

* **GEX model architecture**

* **Epoch manager specification**

* **WS filter lifecycle**

* **UI consumption guide**

Just say the word.