# Epochs in Massive – Plain English
Think of an **Epoch** like a snapshot of the option market's "board" at a particular moment — the board being all the possible option contracts (which strikes and expirations exist for SPX or NDX).

## **Why do we need Epochs?**
The market has two kinds of information coming in:
**•	Slow but complete** "photos" from chain snapshots (the full list of every contract, strikes, expirations, open interest, greeks, etc.).
**•	Fast but partial** "live video" from WebSocket (just price updates for individual contracts as trades happen).

⠀If we mixed them freely, we’d risk:
•	Inventing contracts that don’t exist.
•	Having models recalculate everything every second (too slow).
•	Getting confused when the set of contracts changes (new strikes appear or old ones disappear).

> [!NOTE] ⠀Epochs solve this by creating a **fixed frame** for a period of time.

### **Analogy: Photograph vs. Live Painting**
•	The **chain snapshot** is like taking a photograph of the entire room (every chair, table, person is captured exactly as they are).
•	The **WebSocket** is like an artist quickly painting over parts of that photo in real time (someone moves, their face gets updated, but no new furniture is added).
•	An **Epoch** is the current photo we're working on. It stays the same photo until we decide it’s outdated and take a new one.

### ⠀**When does a new Epoch start?**
A new photo (new Epoch) is taken when:
1	The room layout actually changes — new strikes appear, old ones disappear, or a new expiration is added (detected by comparing the new chain snapshot to the current one).
2	The live painter has been silent for too long (WebSocket stops sending updates for ~5 seconds). We force a new photo to make sure we have fresh data.

### ⠀**What happens inside an Epoch?**
•	The set of contracts is **frozen** — no new ones can be added, none removed.
•	WebSocket can only update prices, sizes, or timestamps on contracts that already exist in the photo.
•	Models (heatmap, GEX) work on this fixed set, and they only recalculate the parts that got new paint (incremental updates = fast).

### ⠀**Why is this important?**
**•	Correctness**: We never accidentally invent or lose contracts.
**•	Speed**: Models don’t have to redo everything every second — they just touch what changed.
**•	Reliability**: If the live feed dies, we force a new photo so models get fresh data instead of working on stale paint.

⠀**In short**: Epochs are the system’s way of saying, 
> “This is the exact playing field right now. Paint prices on it all you want, but don’t move the furniture until I take a new picture.”

> [!NOTE] That keeps everything accurate, fast, and stable even when the market is crazy.

# Epochs and Heatmap Snapshots – Plain English
**What is an Epoch?**
An **epoch** is basically a "frozen picture" of the option market's structure — the exact set of contracts that exist (which strikes, which expirations, call or put).
•	It starts when the system gets a new chain snapshot and notices the structure has changed (e.g., new strikes appeared, old ones disappeared, or a new expiration was added).
•	It can also start if the live WebSocket feed goes quiet for too long (about 5 seconds) — the system forces a new epoch to make sure everything is fresh.
•	While the epoch is active, the list of contracts **does not change** — it's locked.
•	WebSocket can only update prices and sizes on the contracts that already exist in that picture.

> [!IMPORTANT] ⠀Think of an epoch as a **fixed game board**. The pieces (contracts) stay in the same positions until the board itself changes.
## **What is a Heatmap Snapshot?**
A **heatmap snapshot** is just a quick "photo" of the current state of that fixed board at a particular moment.
•	The HeatmapModelBuilder takes one roughly every second.
•	It contains the current prices (updated by WebSocket) for all contracts in the active epoch, plus some metadata.
•	It's published as simple JSON to massive:heatmap:snapshot:{symbol} with a short life (5 seconds).
•	The front-end reads these snapshots and compares the new one to the old one to see what changed → it only updates the parts of the UI that are different (diffs).

⠀Snapshots are **time slices inside a single epoch**. They let the UI feel alive and real-time, even though the underlying board (epoch) only changes occasionally.
### **The Key Difference**
**•	Epoch**: Defines "what contracts exist right now" — long-lived, changes rarely, controls the shape.
**•	Heatmap Snapshot**: Shows "what the prices are right now on that fixed shape" — short-lived, refreshed frequently, powers the live feel.

> [!IMPORTANT] ⠀The epoch is the shape of the state, and snapshots are the moving picture frames playing on top of that shape until the shape itself needs to change.


# Epoch Substrate Details
The **epoch substrate** is the collection of normalized, per-contract records that live inside a specific epoch. It acts as the shared, live workspace where both chain snapshots (initial load) and WebSocket updates (real-time hydration) write their data.
## Purpose
•	Provide a **single, uniform source of truth** for every contract in the current epoch.
•	Allow **incremental updates** from WebSocket without rebuilding the entire structure.
•	Serve as the direct input for model builders (heatmap, etc.) — they read from here instead of raw snapshots.

**⠀Key Pattern**
```text
epoch:{epoch_id}:contract:{contract_id}
```

•	Stored as **STRING** (compact JSON) or **HASH** (field-level updates).
•	TTL ~300 seconds (epoch hygiene).

⠀Typical Fields (from Heatmap Normalizer)
```json
{
  "id": "O:SPXW260107C06850000",
  "underlying": "SPX",
  "expiration": "2026-01-07",
  "strike": 6850.0,
  "type": "call",
  "bid": 10.2,
  "ask": 10.6,
  "mid": 10.4,
  "delta": 0.52,
  "gamma": 0.0012,
  "theta": -1.8,
  "vega": 15.3,
  "oi": 1500,
  "ts": 1700000000.123
}

```

•	Fixed fields (strike, expiration, type, underlying): set once by chain snapshot.
•	Mutable fields (bid, ask, mid, ts, sometimes size): updated by WebSocket hydration.
•	Greeks/OI: usually from chain; may stay static unless provider sends updates.

⠀**How It Is Written**
**1	Chain Snapshot** (full load):
   ◦	Normalizer iterates over every contract in the snapshot.
   ◦	Writes the complete record (all fields) to the contract key.
**2	WebSocket Update** (hydration):
   ◦	Hydrator parses the symbol → finds matching contract key in current epoch.
   ◦	Overwrites only the changed fields (mid, bid, ask, ts, size).
   ◦	Geometry must already exist — if strike not in epoch, update is ignored (geometry_miss).

⠀**Important Rules**
**•	No invention**: WebSocket can only update contracts that already exist in the epoch (geometry comes exclusively from the chain).
**•	Last write wins**: Repeated WS updates simply overwrite price fields.
**•	Epoch isolation**: Each epoch has its own set of contract keys — no bleed between epochs.

⠀**Why This Design**
•	Enables **incremental model computation** — builders can see exactly which contracts changed.
•	Keeps **Redis memory bounded** — only one set of contracts per epoch.
•	Provides **fast lookup** — model builders can get all contracts or query geometry ZSETs.

> [!NOTE] ⠀In short, the epoch substrate is the **live, normalized contract database** for the current market snapshot — fixed in shape, fluid in prices, and the direct feedstock for all downstream models.
