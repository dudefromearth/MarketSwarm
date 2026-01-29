Spot Worker Redis Wiring Documentation

### Module Overview
- **Module:** spot_worker.py  
- **Role:** Fetches and publishes real-time spot prices for indices/stocks; unifies formats; captures for diagnostics.  
- **Bus:** market-redis (from config["buses"]["market-redis"]["url"]).  
- **Config Ties:** Symbols from MASSIVE_SPOT_SYMBOLS, MASSIVE_STOCK_SYMBOLS; interval from MASSIVE_SPOT_INTERVAL_SEC (default 1s).  

### Keys Used
| Key | Purpose | Type | Operations | Lifecycle | Connections |  
|-----|---------|------|------------|-----------|-------------|  
| massive:spot | Live spot value publication per symbol (JSON payload with value, ts, etc.) | STRING | SET (json.dumps(payload)), PUBLISH | No TTL; overwritten on updates | Consumed by model_builders (e.g., HeatmapModelBuilder, GexModelBuilder for underlying prices); external services (e.g., Vigil for events). |  
| massive:spot:trail | Time-series trail of spot values (ZSET: ts → value) | ZSET | ZADD (ts: value), ZREMRANGEBYSCORE (prune old) | Pruned to last 300 entries; no global TTL | Internal to spot_worker for history; potentially consumed by analytics or UI for charts. |  
| massive:spot:analytics | Aggregate metrics (frames, bytes, last_ts) | HASH | HINCRBY (frames, bytes), HSET (last_ts) | No TTL; cumulative | Monitored by admins/devs; connected to Heartbeat Aggregator for uptime analysis. |  
| massive:spot:stream | Raw spot stream (for replay/capture) | STREAM | XADD (payload), maxlen approximate | Maxlen from config (default 100000); approximate pruning | Connected to replay_worker for testing; potential external intel (e.g., Vexy intake). |  

### Connectivity Graph
- **Intra-Massive:** Spot keys feed model_builders (e.g., via orchestrator wiring); chain_worker may correlate for chain fetches.  
- **Inter-Service:** Publishes to market-redis; subscribed by Vigil (events), Vexy (AI decisions on market intel).  
- **Admin/Dev Utility:** Analytics key for monitoring; stream for debugging/replay.  
- **Pipeline Flow:** Spot → Models (e.g., GEX uses underlyings) → Publication (e.g., massive:gex:model).  

### Standard Approach for All Modules
- **Template:** Use the above format: Overview, Keys Table, Graph.  
- **Extraction:** Code review + execution (if needed) for dynamic keys.  
- **Intuitiveness:** Tables for scanability; connections with examples.  
- **Usefulness:** Include ops/lifecycles for admins (e.g., pruning); traces for devs.  
- **Extension:** Aggregate into full pipeline doc after per-module.

**Reflection Prompt:** Where might bias toward over-documenting static keys be creeping in, ignoring dynamics? What’s the smallest optional action to test this map on chain_worker today?