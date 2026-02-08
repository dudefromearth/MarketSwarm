# # Dealer Gravity  
## Visualization-First Data Pipeline & Lexicon Specification  
**Fly on the Wall — Service-Level Application**

---

## 1. Purpose

Dealer Gravity is a **self-contained, service-level application** within Fly on the Wall (FOTW), comparable to **Risk Graph** and **TradeLog-Journal**.

It owns:

- Its own data pipeline  
- Persistence and storage  
- APIs  
- Real-time synchronization (SSE)  
- Visualization logic  

While autonomous, Dealer Gravity is **explicitly designed to interoperate** with other FOTW tools by emitting compact, deterministic visualization artifacts and market context snapshots.

---

## 2. North Star Constraint

> **Dealer Gravity must produce compact, deterministic, visualization-ready artifacts that minimize server → client data throughput while preserving analytical fidelity and long-horizon structure.**

This constraint governs **all architectural decisions**.

---

## 3. Core Design Philosophy

### 3.1 Visualization Artifacts, Not Raw Data

Dealer Gravity **does not** stream:

- Raw bars  
- Raw volume-at-price arrays  
- Unprocessed distributions  

Instead:

- Heavy computation happens **once**, server-side  
- Raw volumes are stored **immutably**  
- Normalization happens **only at read time**  
- The frontend receives a **render-ready artifact**  
- The frontend performs **zero analytical math**  

The client is a **renderer**, not an analyst.

---

## 4. Explicitly Rejected Model

The following model is **not allowed**:
```text
Raw bars → Client
→ Bin
→ Normalize
→ Infer structure
→ Render
```
This creates:

- Excessive bandwidth usage  
- Inconsistent results across devices  
- Duplicated logic  
- Poor replayability  
- Analytical drift  

---
## 5. Canonical Pipeline Model
```text
Raw bars
→ server-side transformation
→ canonical raw profile (immutable)
→ read-time normalization & capping
→ visualization artifact
→ client renders pixels
```
This guarantees:

- Incremental updates  
- Determinism  
- Minimal data transfer  
- Stable cross-device behavior  

---

## 6. Minimal Throughput: Practical Meaning

### 6.1 What the Client Receives

The client receives **only**:

- `min_price`  
- `price_step`  
- `normalized_bins[]` (fixed integer scale, e.g. 0–1000)  
- Derived structural levels  
- Minimal metadata  

Typical payload size:

- Hundreds of integers  
- A handful of floats  
- **Kilobytes, not megabytes**

---

## 7. Explicit Visualization Contract

Dealer Gravity APIs return a **stable visualization artifact** that tells the client exactly how to draw the chart.

### 7.1 Example (Conceptual)

```json
{
  "profile": {
    "min": 6500,
    "step": 1,
    "bins": [12, 87, 451, 1000]
  },
  "structures": {
    "volume_nodes": [6510, 6550],
    "volume_wells": [6538],
    "crevasses": [[6562, 6580]]
  },
  "meta": {
    "spot": 6542.25,
    "algorithm": "tv_microbins_30",
    "normalized_scale": 1000,
    "last_update": "2026-02-06T14:30:00Z"
  }
}
```
The frontend:

* Maps bins → pixels
* Draws overlays
* Applies color and opacity

**No inference. No recomputation. No ambiguity.** 

---

## **8. Dealer Gravity Lexicon (Authoritative)**

Dealer Gravity **does not use traditional Volume Profile language**.

### **8.1 Explicitly Banned Terms**

The following must **never** appear in code, UI, schemas, or documentation:

* POC
* VAH
* VAL
* Value Area
* Auction Market Theory terminology
---

## **9. Canonical Terminology**

### **9.1 Volume Node**

**Formerly:** HVN

**Definition** 

A **Volume Node** is a price level or band where market participation has concentrated meaningfully.

**Interpretation** 

* Represents **attention**, not value
* Indicates friction and engagement
* Reflects areas of **Market Memory**
---

### **9.2 Volume Well**

**Formerly:** LVN

**Definition** 

A **Volume Well** is a price level or band where there is a notable **absence of volume or engagement**.

**Interpretation** 

* Represents **neglect**, not rejection
* Indicates low informational resistance
* Often associated with acceleration
---

### **9.3 Crevasses**

**Definition** 

**Crevasses** are extended or extreme regions of persistent volume scarcity.

**Interpretation** 

* Structural voids in market attention
* Often created by regime shifts or violent repricing
* Zones where convex outcomes are more likely

**Behavioral Properties** 

* Rapid traversal
* Overshoot potential
* Tail amplification

Crevasses are **first-class structures** in Dealer Gravity.

---

### **9.4 Market Memory**

**Definition** 

**Market Memory** is the persistent topology revealed by transformed volume data across long time horizons.

**Key Properties** 

* Encodes historical market attention
* Decays slowly
* Persists across sessions and regimes

**Design Implication** 

* Structural topology must be preserved
* Over-smoothing is harmful
* Memory is **context**, not prediction
---

## **10. Conceptual Reframing**
| Traditional Concept | Dealer Gravity Concept | Conceptual Shift                  |
|--------------------|------------------------|-----------------------------------|
| HVN                | Volume Node            | Value → Attention                 |
| LVN                | Volume Well            | Rejection → Neglect               |
| Thin Liquidity     | Crevasse               | Thin → Structurally Unstable      |
| Auction Memory     | Market Memory          | Balance → Persistent Topology     |
## **11. Dealer Gravity as a Context Emitter**

Dealer Gravity is not just a visualization engine.

It is a **market context emitter**.

Other FOTW services do not need bins — they need **facts**.

### **11.1 Context Snapshot (For Other Tools)**
```json
{
"symbol": "SPX",
"spot": 6542.25,
"nearest_volume_node_dist": -0.003,
"volume_well_proximity": 0.012,
"in_crevasse": true,
"market_memory_strength": 0.82,
"timestamp": "2026-02-06T14:30:00Z"
}
```
Used by:

* Trade Selector
* ML systems
* Risk Graph
* Journaling and retrospectives
---

## **12. Two-Tier Output Model**

### **12.1 Tier 1 — Visualization Artifacts**

* Normalized bins
* Structural overlays
* Styling metadata
* Optimized for UI rendering

### **12.2 Tier 2 — Context Snapshots**

* Distances and relationships
* Structural classifications
* Market Memory metrics
* Optimized for ML and strategy logic

This separation is **intentional and non-negotiable**.

---

## **13. Architectural Benefits**

### **Performance**

* Minimal bandwidth usage
* Fast initial load
* Lightweight SSE updates
* Mobile-friendly

### **System Design**

* Stateless clients
* Deterministic replay
* Easy caching
* Clean service boundaries
* Cross-tool interoperability
---

## **14. Canonical Design Statement**

> Dealer Gravity does not model value or equilibrium.

> It models attention, neglect, and memory — revealing the persistent topology of market engagement and the structural voids where convexity emerges.

---

## **15. Implementation Mandates**

* Store raw volumes immutably
* Normalize only at read time
* Never send raw bars to the client
* Treat the frontend as a renderer
* Use Dealer Gravity lexicon exclusively
* Preserve Market Memory
* Treat Crevasses as first-class structures
---

## **16. Summary**

Dealer Gravity is a **market instrumentation service**, not a charting tool.

Its purpose is to:

* Reveal persistent structure
* Identify neglect and instability
* Emit compact, deterministic artifacts
* Support convexity-first decision-making

Everything else — incremental updates, SSE, AI analysis, ML integration — flows naturally from this foundation.