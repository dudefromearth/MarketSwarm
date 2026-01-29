### WebSocket Worker Redis Wiring Documentation

#### 1. Module Overview
- **Module:** ws_worker.py  
- **Role:** Establishes and maintains the provider WebSocket connection; authenticates; dynamically subscribes to contracts based on current epoch geometry; streams raw messages for hydration; tracks analytics and reconnection.  
- **Bus:** market-redis (from config["buses"]["market-redis"]["url"]).  
- **Config Ties:** WS URL (MASSIVE_WS_URL); API key; reconnect delay; stream maxlen (default 100000).

#### 2. Static Keys (Fixed aggregates—table for quick scan)
| Key                          | Purpose                              | Type      | Ops                  | Lifecycle              | Notes                                      |
|------------------------------|--------------------------------------|-----------|----------------------|------------------------|--------------------------------------------|
| massive:ws:analytics         | Connection metrics (frames, bytes, last_ts, reconnects) | HASH     | HINCRBY, HSET        | No TTL; cumulative     | Core for robustness monitoring; reconnects added if enhanced |
| massive:ws:stream            | Raw provider messages                | STREAM    | XADD (maxlen approx) | Pruned to maxlen       | Consumer group "ws_hydrator" reads         |

#### 3. Dynamic Key Patterns (Core for complexity—patterns with examples)
- **Pattern:** No per-contract keys written by ws_worker (raw stream only).  
  Purpose: All messages dumped raw; parsing/hydration delegated to ws_hydrator.  
  Type: STREAM entry {ts, payload}.  
  Ops: XADD on every message.  
  Lifecycle: Approximate maxlen pruning.  
  Examples:  
    - Entry: {"ts": 1700000000.123, "payload": "{\"action\":\"trade\",\"sym\":\"O:SPX...\"}"}.  
    - Scales to high volume in bursts (thousands/sec possible).  

- **Indirect Dynamics (via epoch lookup for subscriptions):**  
  - Queries `epoch:active` (HASH) and epoch contracts to build subscription list.  
  - No direct writes beyond stream/analytics.

#### 4. Communication Graph (ASCII Diagram - Simple Text Flow)
```
Provider WS
  └── messages → WsWorker
          ├── XADD raw → massive:ws:stream
          ├── updates analytics → massive:ws:analytics
          └── queries for subs → epoch:active + epoch contracts (read-only)

WsHydrator (consumer group)
  └── reads ← massive:ws:stream
          └── parses → writes hydrated contracts → epoch:{id}:contract:*
                  └── flags → epoch:{id}:had_ws_updates
```

- **Intra-Massive:** Raw stream → ws_hydrator → model substrates; read-only epoch lookup for subs.  
- **Inter-Service:** Analytics → Heartbeat Aggregator; raw stream potential for replay/testing.  

#### 5. Operational Scenarios (Extremes handling—matrix for antifragility)
| Condition                  | Impact on Keys                          | Handling                                      | Admin/Dev Action                              |
|----------------------------|-----------------------------------------|-----------------------------------------------|-----------------------------------------------|
| Normal                     | Steady stream entries                   | XADD + analytics incr; consumer keeps up      | Monitor frames/bytes in analytics             |
| Burst (high trade volume)  | Rapid XADD; stream growth               | Approximate maxlen prunes old; batch hydration| Watch consumer lag (XINFO GROUPS); scale maxlen|
| Disconnect/Reconnect       | Gap in stream; analytics last_ts stale  | Jittered reconnect loop; resubscribe on epoch | Check reconnect logs; analytics last_ts       |
| Epoch Promotion            | Subscription list change                | Detects via snapshot channel; rebuilds/resubs | Verify sub storms in logs/analytics           |
| Provider Maintenance       | Prolonged disconnect                    | Reconnect loop; dormancy forces chain refresh | Aggregator alerts; manual chain force if needed|

This wiring keeps ws_worker lightweight (raw dump + analytics), delegating complexity to hydrator while providing full observability for robustness under financial extremes.

**Reflection Prompt:** Where might bias toward over-relying on raw stream completeness be creeping in? What’s the smallest optional action to add reconnect counters to ws:analytics today?