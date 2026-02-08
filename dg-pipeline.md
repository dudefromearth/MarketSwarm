# **Dealer Gravity — Visualization-First Data Pipeline Design**

## **Purpose**

Dealer Gravity is designed as a **self-contained, service-level application** within Fly on the Wall (FOTW), similar to Risk Graph and TradeLog-Journal. It owns its data, persistence, APIs, and real-time sync, while remaining interoperable with other tools through clean, deterministic contracts.

The core architectural constraint that shapes the entire system is:

> **The pipeline must produce a compact, deterministic, visualization-ready dataset that minimizes server → client data throughput while preserving analytical fidelity.** 

This principle governs how data is stored, transformed, served, visualized, and shared with other services.

---

## **Core Design Principle**

### **Visualization Artifacts, Not Raw Data**

Dealer Gravity does **not** stream raw bars, raw volume data, or unprocessed distributions to the client.

Instead, it produces **renderable visualization artifacts**:

* Heavy computation happens **once**, server-side
* The client receives only what is required to draw the chart
* The frontend does **zero analytical math**
* All normalization, binning, and capping is deterministic and reproducible

### **Anti-Pattern (Explicitly Avoided)**

```
Raw bars → client
         → compute bins
         → normalize
         → infer levels
         → render
```

This leads to:

* Excessive bandwidth usage
* Inconsistent results across devices
* Duplicated logic
* Unreliable replayability

### **Correct Model**

```
Raw bars
  → server-side transformation
    → canonical raw profile
      → read-time normalization
        → visualization artifact
          → client renders pixels
```

The client is a **renderer**, not an analyst.

---

## **Minimal Throughput: What It Means in Practice**

### **1. Bins, Not Bars**

The server sends:

* min_price
* price_step
* normalized_bins[] (fixed-scale integers, e.g. 0–1000)
* A small set of derived levels (POC, VAH, VAL, HVN, LVN, Gamma Flip)

This typically results in:

* ~200–400 integers
* A handful of floats
* A few metadata fields

Measured in **kilobytes**, not megabytes.

---

### **2. Read-Time Normalization (Server-Side)**

Raw volumes are stored immutably. Normalization is applied **at read time** based on request parameters (e.g., capping_sigma).

Benefits:

* Incremental updates are possible without reprocessing history
* Different visualization modes are deterministic
* No client-side math or state drift
* Identical output across devices and sessions
---

### **3. Explicit Visualization Contracts**

The API returns a **stable visualization contract** that tells the client exactly how to draw the chart.

Example (conceptual):

```json
{
  "profile": {
    "min": 6500,
    "step": 1,
    "bins": [12, 87, 451, 1000, ...]
  },
  "levels": {
    "poc": 6523,
    "vah": 6581,
    "val": 6462,
    "hvn": [6510, 6550],
    "lvn": [6538],
    "gamma_flip": 6548
  },
  "meta": {
    "spot": 6542.25,
    "mode": "tv",
    "algorithm": "tv_microbins_30",
    "normalized_scale": 1000,
    "last_update": "2026-02-06T14:30:00Z"
  }
}
```

The frontend:

* Maps bins → pixels
* Draws overlays
* Applies styles

**No inference. No recomputation. No ambiguity.** 

---

## **Dealer Gravity as a Context Emitter**

Dealer Gravity is more than a charting tool — it is a **market context emitter**.

Other services (Trade Selector, Risk Graph, ML systems) do not need bins.

They need **facts**.

### **Examples of Context Outputs**

* Spot distance to POC
* Spot position within value area
* Proximity to HVN / LVN
* Gamma flip distance
* Profile shape classification
* Regime alignment

### **Context Snapshot Contract (For Other Services)**

```json
{
  "symbol": "SPX",
  "spot": 6542.25,
  "poc_dist_pct": -0.003,
  "value_area_position": 0.72,
  "profile_shape": "p",
  "gamma_alignment": "positive",
  "timestamp": "2026-02-06T14:30:00Z"
}
```

This payload is:

* Extremely small
* Deterministic
* ML-ready
* Replayable
* Suitable for journaling, scoring, and training
---

## **Two-Tier Output Model**

Dealer Gravity intentionally exposes **two distinct output tiers**:

### **Tier 1 — Visualization Artifact (UI-Focused)**

* Normalized bins
* Overlay levels
* Styling metadata
* Designed for fast rendering

### **Tier 2 — Context Snapshot (System-Focused)**

* Derived distances
* Structural classifications
* Regime context
* Designed for ML, Trade Selector, RiskGraph

This separation prevents UI concerns from polluting analytical systems and vice versa.

---

## **Performance and Architectural Benefits**

### **Performance**

* Minimal bandwidth usage
* Fast initial load
* Lightweight SSE updates
* Mobile-friendly by default

### **Architecture**

* Stateless clients
* Easy caching
* Deterministic replay
* Clear service boundaries
* Clean interoperability across FOTW tools
---

## **Alignment With the Broader FOTW System**

This design follows the same philosophy used across Fly on the Wall:

* **Raw data stays deep**
* **Meaning rises upward**
* **Clients consume meaning, not noise**

It enables:

* Incremental data pipelines
* Deterministic analytics
* ML-ready context capture
* AI analysis layered *on top*, not baked into the core pipeline

Dealer Gravity becomes a **market instrumentation service**, not just a chart.

---

## **Canonical Design Statement (For Specs)**

> **Dealer Gravity produces deterministic, visualization-ready artifacts and compact market context snapshots, ensuring minimal server-to-client data transfer while preserving analytical fidelity and cross-tool interoperability.** 

---

## **Implications for Implementation**

* Store raw volumes immutably
* Normalize only at read time
* Never send raw bars to the UI
* Treat the frontend as a renderer
* Expose context snapshots as first-class outputs
* Keep AI analysis layered and optional
---

## **Summary**

Dealer Gravity is architected around a single non-negotiable constraint:

> **Efficient visualization through compact, deterministic artifacts.** 

Everything else — incremental updates, SSE, AI analysis, ML integration — flows cleanly from that rule.

This keeps the system fast, scalable, reproducible, and deeply interoperable with the rest of Fly on the Wall.

