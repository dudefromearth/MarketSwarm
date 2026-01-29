# What a Normalizer Does in Massive – Plain English
A **Normalizer** is a small, focused function that takes raw option contract data — either from a full chain snapshot or from a single WebSocket update — and turns it into a **standardized, clean contract record** that lives inside the current epoch.
Think of it as a **translator and organizer**:
* •	The provider sends data in different formats (big chain dump vs tiny WS tick).
* •	The normalizer makes sure both formats end up looking exactly the same in Redis, so later stages (like model builders) can treat them identically.

⠀Key points:
* •	Normalizers **do not calculate** anything (no greeks, no strategy costs).
* •	They only **parse, select fields, and write** a compact JSON record to epoch:{epoch_id}:contract:{contract_id}.
* •	Every model that needs contract data has its own normalizer (or none, see GEX below).
* •	They are called automatically by the ChainWorker for chain snapshots and by the WsHydrator for WebSocket updates.

⠀**Heatmap Normalizer – What It Actually Does**
There are two code paths:
1. **1	Chain Snapshot Path** (the main one):
   * ◦	Receives the full list of contracts from a chain snapshot.
   * ◦	For each contract, pulls out the fields the heatmap cares about: strike, expiration, type, bid/ask/mid, delta/gamma/theta/vega, open interest, timestamp.
   * ◦	Writes a clean JSON blob to the epoch-scoped key for that contract ticker.
   * ◦	Sets a 300-second TTL.
2. **2	WebSocket Path** (hydration):
   * ◦	Receives a single live price update.
   * ◦	Parses the WS symbol (e.g., "O:SPXW260107C06850000") to get underlying, expiration, strike, type.
   * ◦	Updates **only** the price fields (mid, bid, ask, timestamp) in the same epoch contract key.
   * ◦	This is the "hydration" step — adding fresh prices to the contract that was originally created by the chain snapshot.

⠀Result: All contracts in the current epoch have the same structure whether they came from the initial chain load or live WS updates.
**GEX Normalizer – Why It’s a No-Op**
The GEX normalizer is deliberately empty (return None).
Reason:
* •	GEX (Gamma Exposure) calculation only needs the **raw chain snapshot** fields (strike, open interest, gamma, etc.).
* •	It does **not** need or use live price updates from WebSocket.
* •	The GEX ModelBuilder reads directly from the chain snapshot data published by ChainWorker — it bypasses the per-contract epoch substrate entirely.

⠀So a normalizer is registered (to satisfy the fan-out registry) but does nothing because GEX has no use for the normalized epoch contract format or WS hydration.
**Terminology Check: "Hydration"**
You are using "hydrated" **perfectly correctly**.
In Massive terminology:
* •	The chain snapshot provides the initial "dry" contract records (geometry + starting values).
* •	WebSocket "hydrates" them by pouring in fresh price/size data.
* •	The process of applying those live updates to existing epoch contracts is called **hydration** (done by WsHydrator calling the normalizer's WS path).

⠀Summary for newcomers:
* **•	Normalizers** = make sure every contract in an epoch looks the same, no matter where the data came from.
* **•	Heatmap normalizer** = does the work for both chain load and live WS price updates.
* **•	GEX normalizer** = intentionally empty because GEX works directly off raw chain data and doesn’t need live prices.

⠀That’s the whole purpose — a clean, uniform contract layer that model builders can rely on.

