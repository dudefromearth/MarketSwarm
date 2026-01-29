# # mmaker Heatmap Pipeline v2  
### Four-Stage Deterministic Model Construction

---

## 0. Goal (Non-Negotiable)

Produce **fully populated, fully calculated heatmaps** for:

- **All symbols**: SPX, NDX  
- **All eligible expiries**: ~5 DTEs per symbol (skipping non-trading days like Jan 1)  
- Deterministically reproducible  
- Operable **with or without WebSocket**  
- Promotion cadence independent of ingestion rate  

Anything less than this is **not done**.

---

## 1. Why the 3-Stage Pipeline Failed

### Old mental model
Chain → Staging → Model
### Failure modes
- Calculations ran while data was mutating
- WebSocket and chain snapshots raced the calculator
- Dirty state was unstable
- Partial geometry leaked into models
- No deterministic cut line

**Core flaw**

> You cannot calculate truth inside a surface that is still being written to.

---

## 2. New Architecture: Four Explicit Stages
`INGEST → STAGING → CALC → MODEL`

```text
Each stage has:
- One responsibility  
- One writer  
- Clear invariants  

---

## 3. Stage Definitions (Authoritative)

---

### 3.1 INGEST (Producers)

**Sources**
- Massive chain snapshots (5–20s cadence)
- WebSocket trades / quotes (sub-second)

**Responsibilities**
- Normalize contracts
- Route data to STAGING only
- Never calculate
- Never promote

**Writes to**
```

`massive:chain:latest:staging`

```text
**Properties**
- High-frequency
- Non-deterministic arrival
- Allowed to overwrite
- Allowed to race

---

### 3.2 STAGING (Mutable Working Surface)

This is **not truth**.  
This is **raw accumulation**.

**Responsibilities**
- Hold latest known contracts per strike
- Track per-tile `dirty` state
- Accept writes from INGEST
- Never calculate butterflies
- Never publish to consumers

**Dirty rules**

A tile becomes dirty if:
- A required contract is missing  
- OR a newer contract arrives  
- OR a chain snapshot replaces older data  

**Writes to**
```

`mmaker:heatmap:staging`

```text
**Reads from**
- INGEST only

**Critical rule**

> STAGING is allowed to be inconsistent.

That is its purpose.

---

### 3.3 CALC (Deterministic Snapshot & Compute)

This is the **critical isolation layer**.

**Triggered by**
- Fixed cadence timer (e.g. 200 ms)

**On each trigger**
1. **Atomic snapshot**
   - Copy entire STAGING surface:
     - dirty tiles
     - clean tiles
     - all contracts
2. Write snapshot to:
```

`mmaker:heatmap:calc`

```text
3. **Reset STAGING dirty flags**
   - Flags only, not contracts
   - STAGING resumes ingest immediately

---

#### CALC Responsibilities

- Perform **topological butterfly calculations**
- Read-only view
- Deterministic
- No mutation during calculation

**Tile eligibility rule**
- If any required strike is missing → tile is dropped
- No partial math
- No placeholders

**Why full copy matters**
- Clean tiles may provide wing contracts
- Dirty ≠ incomplete
- Geometry depends on neighbors

---

### 3.4 MODEL (Published Truth)

This is the **consumer-facing surface**.

**Receives**
- Only fully calculated tiles from CALC

**Writes to**
```

`mmaker:heatmap:model`

```text
**Properties**
- Deterministic
- Complete
- Geometry-sound
- Stable until next promotion

**Rule**
> If it’s here, it’s valid.

No dirty flags exist in MODEL.

---

## 4. Promotion Flow (Timeline)
```

`t0 INGEST writes to STAGING`
`t+ INGEST writes again`
`t+200 CALC snapshot taken`
`t+210 STAGING dirty flags reset`
`t+240 CALC finishes butterflies`
`t+260 MODEL promoted`

```text
- INGEST never stops  
- CALC never races INGEST  
- MODEL never sees partial data  

---

## 5. Startup Behavior (Cold Start)

On startup:

1. Discover eligible expiries (skip holidays)
2. Build empty STAGING heatmaps (all tiles)
3. Hydrate STAGING from chain snapshots
4. First CALC tick:
   - snapshot
   - compute
   - promote
5. MODEL exists **before WebSocket starts**

This is the **first mmaker model push**.

After this:
- WebSocket mutates STAGING
- Promotion cadence continues unchanged

---

## 6. Module Impact Analysis

### Unchanged
- `chain_inspector`
- Expiry discovery
- Chain hydration logic
- Strike indexing
- Butterfly math

### Modified
- `heatmap.py`
  - Remove calculation from staging
  - Mark dirty only
- Orchestrator
  - Add CALC loop
  - Add timed snapshot logic

### New
- `calc_worker` (or equivalent)
  - Snapshot
  - Compute
  - Publish

---

## 7. Invariants (Non-Negotiable)

1. Never calculate in STAGING  
2. Never ingest into CALC  
3. MODEL only receives complete tiles  
4. Snapshot is atomic  
5. Dirty ≠ incomplete  
6. Missing strike ⇒ drop tile  

---

## 8. Current State vs Goal

### What exists
- Working INGEST
- Correct STAGING structure
- Correct dirty semantics
- Correct butterfly computation logic
- Correct promotion mechanics

### What’s missing
- Formal CALC layer
- Atomic snapshot + reset
- Deterministic compute boundary

This is not “half done”.

It is:

> All organs built. Nervous system not yet wired.

---

## 9. Why This Design Is Correct

- Works with or without WebSocket
- Handles bursty snapshots
- Deterministic under replay
- Scales cleanly
- Matches the intended mental model exactly

**Principle**

> Truth is computed, not streamed.
```

