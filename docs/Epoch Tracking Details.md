### Epoch Tracking in Massive – Detailed Explanation

#### 1. Objective & Core Principle
Epoch tracking exists to **isolate topology changes** in the options market while allowing continuous value updates.  
Chain snapshots define the board (strikes + expirations). WebSocket updates move the pieces (prices, greeks).  
When the board changes (e.g., new strikes appear, old ones drop, expiration added/removed), a **new epoch** is created.  
Between epochs, geometry is fixed → models can compute deterministically and incrementally.

Invariant: **WS never defines structure — only chain snapshots do.**

#### 2. Key Redis Structures (Epoch Manager – epoch_manager.py)

| Key Pattern                  | Type  | Purpose                                      | Lifecycle / Notes                          |
|------------------------------|-------|----------------------------------------------|--------------------------------------------|
| `epoch:active`               | HASH  | symbol → current epoch_id                    | Persistent; updated on promotion           |
| `epoch:meta:{epoch_id}`      | HASH  | Metadata: created_ts, strike_count, forced_dirty, dormant_count, etc. | Persistent until manual cleanup            |
| `epoch:dirty`                | SET   | Epoch_ids needing recompute (model builders watch this) | Members removed when marked clean          |
| `epoch:clean`                | SET   | Epoch_ids successfully processed             | Optional hygiene                           |
| `epoch:timeline:{symbol}`    | LIST  | Historical epoch_ids for this symbol          | For debugging / rollback                   |
| `epoch:{epoch_id}:had_ws_updates` | STRING (0/1) | Flag if this epoch ever received WS data | Used for dormancy detection                |

#### 3. Epoch Lifecycle Flow

1. **ChainWorker fetches a snapshot**  
   → Computes geometry hash (sorted strikes + expirations).  
   → Calls `epoch_manager.ensure_compatible_or_new(symbol, geometry_hash, snapshot)`.

2. **Compatibility Check**  
   - If geometry_hash matches current active epoch → return existing epoch_id.  
   - If different → generate new epoch_id (e.g., `SPX:1700000000:abc`), update `epoch:active`, push to timeline, mark old epoch clean.

3. **Normalizers run**  
   → Write to `epoch:{new_id}:contract:{id}`.  
   → Add epoch_id to `epoch:dirty` SET.

4. **Model Builders (Heatmap, GEX, etc.)**  
   → Poll `epoch:dirty` or watch active epoch.  
   → Compute → mark epoch clean (`epoch_manager.mark_epoch_clean(epoch_id)`).

5. **Dormancy Detection** (critical for correctness)  
   - If WS silent for > `MASSIVE_EPOCH_DORMANT_THRESHOLD` seconds (default 5s), increment dormant_count.  
   - If dormant_count exceeds threshold → force new epoch (even if geometry identical) to guarantee recompute with latest values.  
   - HARD INVARIANT: A full epoch MUST be recalculated if WS is dormant.

#### 4. Why This Design (First Principles)

- **Topology Authority:** Only chain snapshots can change structure → prevents WS noise from inventing strikes.
- **Incremental Efficiency:** Between epochs, only dirty contracts recompute → low latency.
- **Deterministic Replay:** Epochs are immutable windows → replay_worker can recreate exact state.
- **Antifragile under Stress:**  
  - Burst contracts → new epoch isolates explosion.  
  - WS disconnect → dormancy forces fresh snapshot.  
  - API failure → fallback to prior epoch (still valid geometry).

#### 5. Operational Inspection (epoch-inspect.sh output example – Jan 03, 2026)

```
SYMBOL  EPOCH_ID                     AGE(s)  DIRTY  DORMANT  FORCED  WS  HEATMAP  GEX
------------------------------------------------------------------------------------------------
SPX     SPX:1700000000:1f3a         45      no     0        no      yes 1245     842
NDX     NDX:1700000000:9b2e         120     yes    2        yes     no  0        0
```

- DIRTY = still in `epoch:dirty` → models pending.
- DORMANT >0 → WS silence detected.
- FORCED = new epoch forced due to dormancy.
- WS = had_ws_updates flag.
- HEATMAP/GEX = contract counts in latest snapshot (diagnostics).

#### 6. Summary – Mental Model

Think of epochs as **photographic plates**:

- Chain snapshot exposes the plate → fixes geometry.
- WS hydrates the image → adds real-time values.
- When plate warps (geometry change) or developer dries up (WS dormant) → expose a new plate.
- Models develop only changed plates → efficient, correct, resilient.

This is how Massive achieves sub-second model updates while remaining structurally authoritative under any market condition.