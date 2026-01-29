# What a Model Builder Is – Plain English

A **Model Builder** is a worker that runs in a loop (usually every second) and converts the raw, organized contract data from an epoch into the final “models” that the dashboard and UI require to display features such as heatmaps and GEX charts.

Think of it like a **factory machine**:
- **Raw materials** are received (via contracts from normalizers and WebSocket hydration).
- The machine **processes** them into finished products (the heatmap grid or GEX levels).
- It packages and ships the products to Redis for the UI to retrieve.

Model Builders are not the entire pipeline — they sit in the Calculate stage (after Staging/Normalizers and Hydration). They consume the epoch substrate and produce published models that trigger the next stage (Models/Publication for UI/SSE).

#### Where They Fit in the Massive Pipeline
1. **Massive Ingestion** → raw chain snapshots + WS stream.
2. **Staging (Normalizers/Hydrator)** → epoch contract records.
3. **Calculate Strategy (Model Builders)** ← **HERE** → read epoch → compute models.
4. **Models/Publication** → SSE diffs to UI dashboard.

#### HeatmapModelBuilder – What It Does Right Now (Incomplete)

This builder runs every 1 second and does **two things** for each symbol (SPX, NDX):

1. **Reads all contracts** from the current epoch (`epoch:{id}:contract:*`).
2. **Builds and publishes geometry**:
   - Groups contracts by underlying.
   - Deletes the old ZSET and rebuilds `epoch:{id}:heatmap:{underlying}:all` — a sorted list of all contracts by strike (for fast range queries later).
3. **Takes a snapshot** — a simple JSON list of all current contracts + metadata, published to `massive:heatmap:snapshot:{symbol}` (5-second TTL for UI).
4. **Marks the epoch clean** so it won't be reprocessed until something new happens.

**What it's missing** (unfinished, as you noted):
- No actual **tile calculation** (butterfly/vertical debits, convexity).
- No final **heatmap model** published to `massive:heatmap:model:{symbol}` (just geometry and raw snapshot).
- No incremental diffs — full rebuild every second.

**Does completion promote to next stage?** Yes — when finished, it would publish the calculated tile grid to `massive:heatmap:model:*`, which the UI/SSE gateway reads to send diffs to the dashboard (next stage).

#### GexModelBuilder – What It Does Right Now (More Complete)

This one runs every 1 second and computes **gamma exposure (GEX)** directly from raw chain snapshots:

1. **Scans recent snapshots** (`massive:chain:snapshot:{symbol}:*`).
2. **Aggregates GEX per strike/expiration**:
   - For calls and puts separately.
   - GEX = gamma × open_interest × multiplier (usually 100).
   - Groups by expiration → dict of strike → total GEX.
3. **Publishes two models**:
   - `massive:gex