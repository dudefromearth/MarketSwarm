# # Addendum: Redis Boundary Correction — Dealer Gravity Artifacts Only (Delivery Layer)

## Purpose

This addendum corrects the Dealer Gravity development plan regarding Redis usage.

**New requirement:** Redis must be used only as a **delivery/cache layer for final, renderable artifacts**.  
All interim computation, transformations, and intermediate states must live on **disk / durable storage** (files, parquet, database, etc.), not Redis.

This aligns Dealer Gravity with the Fly on the Wall service model: deterministic outputs, clear ownership, and minimal operational complexity.

---

## Core Correction

### Previous Assumption (To Remove)

- Redis stores raw volume arrays and transformation intermediates
- Incremental updates mutate Redis-stored structures
- Read-time normalization computes stats from Redis arrays

This introduces avoidable complexity:
- concurrency risk (lost writes, partial writes)
- compute load in the delivery layer
- unclear source-of-truth boundaries
- harder reproducibility and replay

### Correct Model (Required)

> **Redis contains only final visualization artifacts.**  
> **Disk/durable storage contains all raw data + intermediate computation outputs.**

Redis is not a compute substrate.

---

## Authoritative Data Flow

### 1) Disk-Based Pipeline (Authoritative / Replayable)

All of these live on disk/durable storage:

- raw bars / raw volumes
- transformation outputs (micro-binning, TV distribution, etc.)
- structural extraction results (Nodes / Wells / Crevasses)
- Market Memory metrics
- AI analysis artifacts
- versioned metadata and logs for reproducibility

Pipeline example:
```text
Raw data (disk)
→ Transform (disk)
→ Structure extraction (disk)
→ Artifact builder (disk)
→ Final artifact publish (Redis)
```
### 2) Redis Publish Step (Final Only)

After the pipeline produces a “last known good” visualization dataset, publish to Redis:

- compact bins (already normalized/scaled)
- structures (Nodes/Wells/Crevasses as levels/intervals)
- GEX render dataset (if enabled)
- structural lines (AI or computed)
- artifact metadata (versions/timestamps)

Redis holds **only what the client needs to render**.

---

## Redis Content Policy (Non-Negotiable)

### Allowed in Redis
- final renderable bins (fixed scale, e.g., 0–1000 integers)
- structural lines (price levels / intervals)
- GEX render arrays
- artifact_version, created_at, symbol, transform_version
- minimal metadata required for rendering and audit

### Not Allowed in Redis
- raw volume arrays (unbounded growth + reprocessing concerns)
- intermediate transforms
- incremental accumulation state
- statistical accumulators (sum/sumsq)
- feature engineering artifacts
- training data or ML feature snapshots

---

## System Responsibilities (Clarified Ownership)

### Massive Service (Python) — Compute Owner
- performs batch + incremental processing on disk
- produces transformed datasets and structural outputs on disk
- builds final visualization artifacts
- publishes final artifact to Redis
- publishes update event to Redis pub/sub (for SSE fanout)

### SSE Gateway (Node.js) — Delivery Owner
- serves `/api/dealer-gravity/artifact` by reading the artifact from Redis
- fans out update events over `/sse/dealer-gravity`
- does **not** normalize, compute, or derive structure
- does **not** mutate artifacts

### Dealer Gravity UI + Risk Graph — Render Consumers
- fetch artifacts and render them
- subscribe to SSE updates
- do not compute structure or normalization

---

## Artifact Contract (Implication)

Because Redis stores only final artifacts, the artifact must be fully render-ready:

- bins are already in final display scale
- opacity-safe defaults exist
- structures are expressed in Dealer Gravity lexicon:
  - `volume_nodes`
  - `volume_wells`
  - `crevasses`
  - `market_memory_strength`
- structural lines are included when available

**Risk Graph backdrop is sourced from the same artifact** and remains live-bound through SSE.

---

## Live Binding Requirement (Implication)

When Dealer Gravity recomputes structure (computed or AI-assisted), the system must:

1. produce a new artifact on disk
2. publish the new artifact to Redis (overwrite last)
3. publish an SSE update event with new `artifact_version`
4. Dealer Gravity UI and Risk Graph re-fetch and re-render

This ensures:
- Dealer Gravity app and Risk Graph backdrop always match
- no stale snapshots
- deterministic cross-tool consistency

---

## Event Schema Recommendation (Minimal)

When a new artifact is published:

```json
{
  "type": "dealer_gravity_artifact_updated",
  "symbol": "SPX",
  "artifact_version": "v123",
  "occurred_at": "2026-02-06T14:30:00Z"
}
```

Consumers update only when artifact_version changes.

---

## **Implementation Impact (Summary)**

### **Remove / Replace**

* Redis raw storage formats for volumes
* Redis-based incremental mutation logic
* read-time normalization computed from raw arrays in Redis

### **Add / Emphasize**

* disk-based pipeline stages + versioning
* artifact build step producing compact render dataset
* Redis as last-known-good artifact cache
* SSE update events keyed by artifact_version
---

## **Canonical Statement**

> **Redis is a delivery layer for final visualization artifacts only.**
> **Dealer Gravity computation and intermediate state live on disk/durable storage.**
> **This keeps the system deterministic, replayable, and operationally simple.**