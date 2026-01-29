# The Hydrator – Plain English

The **Hydrator** is the worker that takes the fast, live price updates coming from the WebSocket and applies them to the current set of option contracts that the system already knows about.

### Analogy
Think of the chain snapshot as a complete photo of every option contract (like a big group photo of everyone in the room).  
The WebSocket is like someone shouting out "that person just changed their shirt color!" over and over for different people.  
The Hydrator is the person who listens to those shouts, finds the right person in the photo, and quickly updates just their shirt color (the price, size, timestamp). It ignores shouts about people who aren't in the photo (contracts not in the current epoch).

### Where It Fits in the Massive Pipeline
The pipeline stages are roughly:
1. **Ingestion** – ChainWorker gets full snapshots, WsWorker gets raw WebSocket messages.
2. **Staging** – Normalizers turn snapshots into clean contract records for the current epoch.
3. **Hydration** ← **Hydrator lives here** – It reads the raw WebSocket stream and updates prices on those clean contract records.
4. **Calculation** – Model builders (heatmap, GEX) use the updated contracts to compute models.
5. **Publication** – Models sent to UI.

So the Hydrator sits in the **Staging/Hydration stage**, right after the raw WebSocket data arrives and before the model builders run.

### Essential Function
Its **one job** is:  
**Update live prices (and size/timestamp) on existing contracts in the current epoch, using only the data from the WebSocket stream.**

It does this safely:
- Only updates contracts that already exist in the epoch (no inventing new ones).
- Marks the epoch as "dirty" when it makes changes so model builders know to recalculate.
- Keeps lots of counters for debugging (how many messages seen, how many missed because of geometry, etc.).

## Does the Hydrator Change the State of the Contract?
**Yes, the hydrator absolutely changes the state of the contract.**

Here's how the state evolves in simple terms:

- **When the epoch is first created** (from a chain snapshot):
  - The previous state is whatever was in the old epoch (or nothing if it's the very first).
  - The normalizer writes the **initial state** — all fields from the chain snapshot (strike, expiration, type, starting bid/ask/mid, greeks, open interest, timestamp).
  - This is the "baseline" version of each contract.

- **As WebSocket messages arrive** (at any time, many per second):
  - The hydrator finds the contract in the current epoch.
  - It **overwrites** just the price-related fields (last/mid, bid, ask, size, timestamp).
  - The previous state for those fields was whatever the last known value was (initial from chain or previous WS update).
  - Fixed fields (strike, expiration) never change.

- **When a heatmap snapshot is "peeled off"** (builder runs ~every 1 second):
  - The snapshot captures the contract **exactly as it is right now** — including all WS updates that have happened since the last snapshot.
  - The previous snapshot state was the values from the prior capture (1 second ago).
  - So between snapshots, the state can change many times (from WS), but each snapshot freezes the state at that instant.

### Timing Summary
- **Chain** → epoch creation → initial state (once per epoch).
- **WS** → hydrator updates → state changes **immediately on message arrival** (many times per second).
- **Builder** → snapshot → captures current state **every ~1 second**.

The hydrator is what keeps the contracts "alive" with fresh prices between the slower chain snapshots. It's the bridge that makes the heatmap feel real-time even though the underlying contract list only changes occasionally.

> [!NOTE] **In short**: The Hydrator is the bridge that keeps the option prices fresh and current without changing the underlying structure of what contracts exist. It’s what makes the heatmap feel "live" even though the contract list only changes occasionally.