# Heatmap Construction & Publishing Process  
**Massive → mmaker → Fly on the Wall (FOTW)**

---

## 1. Purpose

This document defines the **deterministic process** by which the Massive data plane (Spot, Chain, WebSocket) is transformed into a **Heatmap Model** composed of **Tiles**, published incrementally to the Fly on the Wall dashboard.

The design supports:
- Live markets
- Closed markets
- Historical replay
- Simulation
- Deterministic rebuilding and diff-based streaming

This is not a UI document.  
This is a **model construction and state publication contract**.

---

## 2. Core Concepts

### 2.1 Tile

A **Tile** is the atomic unit of the heatmap.

A tile represents:
- A deterministic **slot** (identity)
- A current **state** (value)
- A **timestamp** (freshness)

#### Tile Identity (immutable)
- Underlying (e.g. SPX)
- Expiration
- Strategy / Structure (single, vertical, fly, etc.)
- Strike(s)

#### Tile State (mutable)
- Leg prices
- Derived convexity score
- Metadata (source, timestamp, confidence)

---

### 2.2 Heatmap

A **Heatmap** is a collection of tiles over a defined domain.

- Dimensions are fixed per heatmap type
- Slots are deterministic
- Tiles may be missing or stale

The heatmap itself is **versioned**, immutable once published.

---

### 2.3 Staging Heatmap

The **Staging Heatmap** is a mutable workspace where tiles are accumulated prior to publication.

- Always active
- Never directly visible to clients
- May be partially filled
- May contain tiles newer than the last published heatmap

---

## 3. Data Sources

### 3.1 Chain Snapshots (REST)

Characteristics:
- Dense
- High information content (Greeks, OI, IV, metadata)
- Delayed by request–response latency
- Covers a wide strike range

Primary purpose:
- Establish heatmap topology
- Seed tiles
- Provide structural completeness

---

### 3.2 WebSocket Trades (WS)

Characteristics:
- Thin
- High-frequency
- Trade-based (not quotes)
- Minimal fields (price, size, timestamp)

Primary purpose:
- Update existing tiles with fresh price information
- Maintain real-time fidelity
- Drive incremental heatmap updates

---

### 3.3 Spot (Index / ETF)

Characteristics:
- Reference prices
- Low latency
- Used for contextual calculations

Primary purpose:
- Support derived metrics
- Normalize convexity and gradients

---

## 4. Tile Admission Rules (Hard Invariants)

A tile may enter the **Staging Heatmap** *iff* one of the following is true:

### Rule A — Slot Creation
> No tile exists for this slot.

- Typical during startup
- Typical during chain snapshot ingestion

---

### Rule B — Temporal Supersession
> A tile exists, but the incoming tile is **newer**.

Newness is determined by:
- Event timestamp
- (Optional) sequence or monotonic clock

Applies to:
- WebSocket trade updates
- Refreshed chain snapshots

---

### Rule C — No Regression
> Incoming tile is older or equal → **discard**

Guarantees:
- Monotonic state
- Replay determinism
- WS / REST race safety

---

## 5. Separation of Concerns

### 5.1 Producers (Never Publish)

Producers include:
- Chain snapshot ingestion loop
- WebSocket trade ingestion loop

Responsibilities:
- Parse raw data
- Construct candidate tiles
- Apply tile admission rules
- Insert tiles into staging

Producers **never**:
- Decide completeness
- Trigger publication
- Clear state

---

### 5.2 Publisher (Single Authority)

The Publisher is the only component allowed to:
- Declare a heatmap version
- Emit diffs
- Advance the canonical state

---

## 6. Publish Conditions (OR-Gated)

A staged heatmap is published when **any** condition is satisfied.

### Condition 1 — Structural Completeness
> All required tile slots are populated.

- Common during startup
- Common when market is closed
- Driven by chain snapshots

---

### Condition 2 — Value Completeness
> Sufficient new or changed tiles exist.

Examples (configurable):
- ≥ N tiles updated
- ≥ X% of tiles changed
- Aggregate delta threshold crossed

This is **real-time mode**.

---

### Condition 3 — Time Boundary
> Maximum publish interval elapsed.

Purpose:
- Prevent silent staleness
- Guarantee forward progress on quiet markets

---

## 7. Publish Semantics

On publish:

1. The staging heatmap becomes the **new canonical heatmap**
2. A version ID is assigned
3. The previous canonical heatmap becomes history
4. The staging area is **not cleared**
   - It continues staging against the new base

This enables:
- Diff-based SSE streaming
- Replay
- Backtesting
- Deterministic rebuilds

---

## 8. Market State Convergence

### 8.1 Market Closed

- Chain snapshots seed all tiles
- WS produces no updates
- One publish occurs
- Heatmap remains stable for hours

No special logic required.

---

### 8.2 Market Open

- Chain snapshots define structure
- WS updates tiles continuously
- Publisher emits updates opportunistically
- Fidelity increases monotonically

No “market open” flag required.

---

## 9. Snapshot Timing Strategy

Chain snapshot cadence is constrained by:
- Request–response latency
- Provider limits
- System throughput

Snapshot requests should:
- Never exceed response completion rate
- Optionally wait for publish cycle completion
- Be analytics-driven (adaptive over time)

---

## 10. Replay & Simulation Compatibility

This architecture supports:
- Offline replay
- Historical market reconstruction
- Deterministic testing of mmaker logic

Replay uses the **same staging + publish rules** as live data.

---

## 11. One-Line Invariant

> **Staging accepts facts. Publishing declares reality.**

---

## 12. Implementation Implications

- mmaker operates entirely on staged and published models
- UI consumes diffs only
- All data sources are orthogonal and composable
- No special cases for time of day, session, or mode

---

## 13. Status

This design is:
- Deterministic
- Replay-safe
- Scalable
- Production-ready

No speculative components remain.

---
## 14. Parallel Strategy Pipelines

The heatmap architecture supports **parallel publishing pipelines per strategy**.  
This is a first-class design feature, not an optimization.

---

### 14.1 Strategy as a First-Class Dimension

Each **strategy** (e.g. Single, Vertical, Fly, Custom) operates as an **independent model pipeline** with:

- Its own staging heatmap
- Its own publish cadence
- Its own completeness rules
- Its own SSE stream

Strategies do **not** block or depend on one another.

---

### 14.2 Pipeline Topology

For each strategy `S`:
```text
Raw Data (Spot / WS / Chain)
↓
Strategy-Specific Tile Builder
↓
Staging Heatmap (S)
↓
Publisher (S)
↓
massive:heatmap:{S}
```
```pcode
Examples:
- `massive:heatmap:single`
```
### 14.4 Asynchronous Strategy Tile Factories

Each strategy-based Tile factory runs **fully asynchronously** and **independently** of every other strategy.

There is **no coordination, locking, sequencing, or dependency** between strategy pipelines.

---

#### 14.4.1 Independence by Design

Key properties:

- Strategy Tile factories:
  - Run in separate async loops or tasks
  - Maintain their own staging state
  - Publish on their own cadence
- A slow or stalled strategy **does not affect** others
- A strategy can be added, removed, or restarted without impacting the system

This guarantees:
- Fault isolation
- Horizontal scalability
- Strategy-level experimentation without risk

---

#### 14.4.2 Shared Inputs, Decoupled Consumption

All strategy Tile factories consume the **same raw inputs**:

- Spot updates
- WebSocket trades
- Chain snapshots

However:
- Each strategy decides **what it cares about**
- Each strategy decides **when a Tile is complete**
- Each strategy decides **when a staged heatmap is publishable**

There is no fan-in bottleneck.

---

#### 14.4.3 Event Fan-Out Model
```pcode         
           ┌───────────────┐
           │ Raw Data Feeds│
           └───────┬───────┘
                   │
    ┌──────────────┼─────────────────┐
    │              │                 │
Single Tiles  Vertical Tiles     Fly Tiles
    │              │                 │
Heatmap:S       Heatmap:V         Heatmap:F
```
Each branch:
- Subscribes independently
- Stages independently
- Publishes independently

---

#### 14.4.4 Asynchronous Safety Guarantees

This design ensures:

- **No head-of-line blocking**
- **No shared mutable state**
- **No global publish locks**
- **No cross-strategy timing assumptions**

If:
- The Fly strategy publishes at 2 Hz
- The Single strategy publishes at 5 Hz
- The Vertical strategy publishes only on completeness

That behavior is expected and correct.

---

#### 14.4.5 Operational Consequences

This enables:

- Strategy-specific backtesting via replay
- Strategy-specific throttling
- Strategy-specific quality metrics
- Strategy-specific SSE subscriptions

Example SSE endpoints:
- `/sse/heatmap/single`
- `/sse/heatmap/fly`
- `/sse/heatmap/vertical`

Each reflects the **best-known state** of that strategy’s model.

---

**Conclusion:**  
Strategies are peers, not layers.  
They share inputs, not control.