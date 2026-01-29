### Chain Worker Redis Wiring Documentation

#### 1. Module Overview
- **Module:** chain_worker.py  
- **Role:** Canonical engine for fetching full option chain snapshots per underlying; defines topology (strikes, expirations, contracts); fans out to normalizers; self-adjusts cadence based on latency.  
- **Bus:** market-redis (from config["buses"]["market-redis"]["url"]).  
- **Config Ties:** Symbols from MASSIVE_CHAIN_SYMBOLS (e.g., I:SPX,I:NDX); interval from MASSIVE_CHAIN_INTERVAL_SEC (default 30s); expirations from MASSIVE_CHAIN_NUM_EXPIRATIONS (default 5).

#### 2. Static Keys
| Key                          | Purpose                              | Type      | Ops                  | Lifecycle              | Notes                                      |
|------------------------------|--------------------------------------|-----------|----------------------|------------------------|--------------------------------------------|
| massive:chain:analytics      | Aggregate metrics (snapshots, contracts, latencies, health categories) | HASH/ZSET | HINCRBY, ZADD, HSET | No TTL; cumulative     | Core health monitoring; time-series for trends |
| massive:chain:latest         | Latest raw snapshot per symbol (for diagnostics) | STRING (JSON) | SET                  | No TTL; overwritten    | Optional capture fallback                  |

#### 3. Dynamic Key Patterns
- **Pattern:** `massive:chain:snapshot:{underlying}:{expiration}:*`  
  Purpose: Per-contract details from a snapshot fetch (greeks, oi, etc.).  
  Type: STRING (JSON payload).  
  Ops: SET per contract; PUBLISH on completion.  
  Lifecycle: TTL ~300s (epoch hygiene); pruned on new epoch.  
  Examples:  
    - massive:chain:snapshot:SPX:20260117:C4500000 (single call contract).  
    - Scales to 5k–20k+ keys in bursts (high vol days with wide strikes).  

- **Pattern:** `epoch:{epoch_id}:contract:{contract_id}`  
  Purpose: Normalized contract substrate for model builders (via normalizers like heatmap/gex).  
  Type: STRING (compact JSON).  
  Ops: SET via normalizers.  
  Lifecycle: TTL 300s; scoped to epoch.  
  Examples:  
    - epoch:SPX:1700000000:abc:contract:O:SPXW260107C06850000.  
    - Explosion: One per contract in snapshot (thousands under extremes).  

- **Pattern:** `epoch:active` (HASH: symbol → epoch_id) + `epoch:meta:{epoch_id}` (HASH)  
  Purpose: Active epoch tracking and metadata (created_ts, strike_count, etc.).  
  Type: HASH.  
  Ops: HSET/HGET for promotion.  
  Lifecycle: Persistent until dormancy/force.  
  Examples: epoch:active → {"SPX": "SPX:1700000000:abc"}.

#### 4. Communication Graph (ASCII Diagram - Simple Text Flow)
```
ChainWorker
  ├── fetches from API → Provider
  ├── publishes snapshots → massive:chain:snapshot:{symbol}:{exp}:* (per-contract JSON)
  ├── updates analytics → massive:chain:analytics
  └── triggers → Normalizers (heatmap.py, gex.py)
          ├── writes substrates → epoch:{id}:contract:* (normalized contracts)
          └── flags dirty → epoch:dirty SET

Model Builders (Heatmap / Gex)
  ├── reads substrates ← epoch:{id}:*
  └── publishes models → massive:{model}:model:{symbol} (final JSON)
```

- **Intra-Massive:** Snapshots → normalizers → model substrates → builders (orchestrator wiring).  
- **Inter-Service:** Analytics/monitors → Heartbeat Aggregator; models → UI/SSE, Vigil (events), Vexy (intel).  

#### 5. Operational Scenarios
| Condition                  | Impact on Keys                          | Handling                                      | Admin/Dev Action                              |
|----------------------------|-----------------------------------------|-----------------------------------------------|-----------------------------------------------|
| Normal (e.g., 2k contracts) | Predictable dynamics (~10k keys/epoch) | Latency-driven cadence; TTL prune             | Monitor analytics latencies; redis-cli epoch:dirty |
| Burst (e.g., 20k+ contracts) | Massive key explosion; memory/CPU spike | Debounce interval; partial flags in analytics | Scale Redis; watch for 'partial'/'slow' in analytics; throttle expirations via config |
| Stale (API slow/downtime)  | Delayed/no new snapshots                | Fallback to prior epoch; dormant threshold    | Check epoch:meta dormant_count; Supervisor restart |
| Failure (API error)        | No publish; analytics violations        | Controlled shutdown; heartbeat flags faulty   | Aggregator notifies; manual intervention if persistent |
| Off-hours/Holiday          | Thin chains (few expirations)           | Empty geometry valid; low contract counts     | Verify models handle 0-levels (e.g., GEX off-hours safe) |

This ASCII diagram is plain text—reliable everywhere (Markdown, terminals, docs). No rendering issues. If you prefer PlantUML or another, let me know!