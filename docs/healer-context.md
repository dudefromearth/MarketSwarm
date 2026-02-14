# MarketSwarm System Context — AutoHealer Reference

## 1. Architecture Overview

MarketSwarm is a distributed real-time market intelligence platform. Services are Python (asyncio) or Node.js processes coordinated through Redis and a centralized Truth configuration system.

**Three-Redis Topology:**
- **system-redis** (127.0.0.1:6379) — Heartbeats, Truth config, service coordination, alert sync
- **market-redis** (127.0.0.1:6380) — Real-time market data, model snapshots, SSE streams. Can use 1GB+ during active trading
- **intel-redis** (127.0.0.1:6381) — RSS content, enriched articles, ML data (~1500 keys)

All three have `maxmemory: 0` (unlimited) and `noeviction` policy.

**Truth System:**
- Central configuration stored in system-redis under key `truth`
- Source files: `truth/mm_node.json` (root) + `truth/components/{service}.json` (per-service)
- Built via `scripts/ms-build-truth.sh` which merges components into a single JSON doc and writes to Redis
- Each service loads its config via `shared/setup_base.py` → `SetupBase.load()` at startup

**MySQL Database:**
- Host: 127.0.0.1:3306, User: fotw_app, Database: fotw_app
- Used by: journal (trades, positions, journals, alerts, ML) and sse (users, sessions, econ indicators)
- Journal uses `mysql.connector` (Python), SSE uses `mysql2/promise` (Node.js)

**Service Lifecycle:**
Every Python service follows this startup pattern:
1. `main.py` adds project root to `sys.path`
2. Creates `LogUtil(service_name)` for logging
3. Calls `SetupBase(service_name, logger).load()` to get config from Truth
4. Starts heartbeat thread via `shared.heartbeat.start_heartbeat()`
5. Runs async orchestrator loop (the main service logic)
6. Handles SIGINT/SIGTERM for graceful shutdown

## 2. Service Inventory

| Service | Lang | Entry Point | Port | Redis | Dependencies |
|---------|------|-------------|------|-------|-------------|
| **massive** | Python | `services/massive/main.py` | — | system + market | Redis only |
| **sse** | Node.js | `services/sse/src/index.js` | 3001 | system + market + intel | massive, journal, vexy_ai |
| **journal** | Python | `services/journal/main.py` | 3002 | system + market | MySQL |
| **copilot** | Python | `services/copilot/main.py` | 8095 | system + market | massive (models) |
| **vexy_ai** | Python | `services/vexy_ai/main.py` | 3005 | system + market + intel | massive, rss_agg, vigil |
| **rss_agg** | Python | `services/rss_agg/main.py` | — | system + intel | OpenAI API key |
| **content_anal** | Python | `services/content_anal/main.py` | — | system + intel | rss_agg |
| **vigil** | Python | `services/vigil/main.py` | — | system + market | massive (spot data) |
| **healer** | Python | `services/healer/main.py` | — | system | All (monitors heartbeats) |
| **mesh** | Python | `services/mesh/main.py` | — | system | None |

**What each service does:**
- **massive**: Primary market data ingestion. WebSocket connection to data provider, publishes spot prices, options chains, GEX heatmaps, and analytics models to market-redis.
- **sse**: SSE gateway + UI backend. Subscribes to Redis models, transforms into Server-Sent Events for React frontend. Proxies REST calls to journal (port 3002) and vexy_ai (port 3005). Handles auth/sessions.
- **journal**: Trade logging, journaling, analytics. FastAPI REST API for positions, trade logs, playbooks, alerts, leaderboard. Large codebase: `db_v2.py` (MySQL CRUD), `orchestrator.py` (FastAPI routes + business logic).
- **copilot**: AI analysis layer. MEL (Model Effectiveness scoring), ADI (canonical data export), Commentary (market observations), Alert evaluation engine.
- **vexy_ai**: AI market narrator. Epoch + event-driven play-by-play voice using multiple AI "voice agents". Chat/routine/journal/playbook capabilities. FastAPI on port 3005.
- **rss_agg**: RSS feed pipeline. Ingest -> fetch -> LLM enrichment -> publish to intel-redis.
- **content_anal**: LLM-driven content analysis. Reads enriched articles from rss_agg, produces synthetic insights.
- **vigil**: Market event watcher. Filters for significant price moves, VIX spikes, publishes events to vexy_ai.

## 3. Shared Modules

All shared code is in `/Users/ernie/MarketSwarm/shared/`. Every Python service imports from here.

**`shared/logutil.py` — LogUtil**
- Two-phase: bootstrap (console only) then configured (from Truth config)
- Levels: ERROR(0), WARN(1), INFO(2), DEBUG(3). Controlled by `LOG_LEVEL` env or Truth config
- Format: `[timestamp][service_name][LEVEL] emoji message`
- Usage: `logger = LogUtil("service_name")`, then `logger.info("msg", emoji="...")`, `logger.error("msg")`
- NOTE: `logger.exception()` does NOT exist — use `logger.error(f"...: {exc}")` instead

**`shared/setup_base.py` — SetupBase**
- Connects to system-redis, reads `truth` key, extracts `truth["components"][service_name]`
- Resolves env vars: shell env overrides Truth defaults. Skips unresolved `${VAR}` templates
- Returns config dict with: `service_name`, `meta`, `inputs`, `outputs`, `heartbeat`, `models`, `buses`, `shared_resources`, all env vars, and structural blocks
- Usage: `config = await SetupBase(SERVICE_NAME, logger).load()`

**`shared/heartbeat.py` — Heartbeat Thread**
- Runs outside asyncio (threading.Thread, daemon=True)
- Publishes `{service}:heartbeat` to system-redis every `config["heartbeat"]["interval_sec"]` seconds
- Uses SET with EX (TTL) = `config["heartbeat"]["ttl_sec"]`
- Payload: `{"service": name, "ts": unix_timestamp, "pid": os.getpid(), "status": "running"}`
- Key exists = alive; key expired = dead
- Returns `threading.Event` for shutdown
- BUG HISTORY: used to call `logger.exception()` which doesn't exist — fixed to `logger.error()`

**`shared/ai_client.py` — AI API Client**
- Async XAI (grok-4) primary, OpenAI (gpt-4o-mini) fallback
- Triple-fallback key resolution: config dict -> config.env -> shell env
- Usage: `response = await call_ai(system_prompt, user_message, config, ai_config, logger)`

## 4. File Layout

```
/Users/ernie/MarketSwarm/           # Project root (ROOT)
  services/{name}/main.py           # Python service entry point
  services/sse/src/index.js         # Node.js SSE gateway entry point
  services/{name}/intel/            # Service-specific business logic
  shared/*.py                       # Shared Python modules (logutil, heartbeat, setup_base, ai_client)
  truth/mm_node.json                # Root Truth config
  truth/components/{service}.json   # Per-service Truth component
  scripts/service_manager.py        # Admin server + ServiceManager
  scripts/ms-{service}.sh           # Per-service startup script
  scripts/ms-build-truth.sh         # Truth publisher (merges components -> Redis)
  scripts/admin_ui/                 # Admin dashboard (HTML/CSS/JS)
  logs/{service}.log                # Service stdout/stderr logs
  .pids/{service}.pid               # PID tracking
  .pids/{service}.started           # Startup timestamp (ISO 8601)
  .venv/                            # Python virtual environment
  ui/                               # React frontend (Vite build)
```

**Python executable:** `/Users/ernie/MarketSwarm/.venv/bin/python` (system Python does NOT have required packages)

**Common env vars set by startup scripts:**
- `SERVICE_ID` — service name
- `SYSTEM_REDIS_URL` — redis://127.0.0.1:6379
- `MARKET_REDIS_URL` — redis://127.0.0.1:6380
- `INTEL_REDIS_URL` — redis://127.0.0.1:6381
- `PYTHONUNBUFFERED=1`

## 5. Common Error Patterns

### Redis Connection Failures
- **Symptom:** `ConnectionRefusedError`, `redis.exceptions.ConnectionError`, service hangs on startup
- **Cause:** Redis instance not running or wrong URL
- **Fixable in service code?** NO — infrastructure issue
- **Diagnosis:** Check which Redis instance (6379/6380/6381) is mentioned in the error

### Truth Load Failures
- **Symptom:** `Truth key 'truth' not found`, `Component '{name}' missing in Truth`
- **Cause:** Truth not published to Redis, or service name doesn't match component ID
- **Fixable in service code?** Only if service_name constant is wrong. Usually NO (needs `ms-build-truth.sh`)

### Import / Module Errors
- **Symptom:** `ModuleNotFoundError`, `ImportError`, `AttributeError: module has no attribute`
- **Cause:** Missing import, wrong path, refactored shared module
- **Fixable in service code?** YES if the import is in `services/{name}/`. NO if it's in `shared/`
- **Common pattern:** Service imports `from shared.X import Y` but Y was renamed/removed

### Asyncio Task Crashes
- **Symptom:** `Task exception was never retrieved`, `CancelledError`, unhandled exception in orchestrator loop
- **Cause:** Missing try/except in async task, bad data from Redis, division by zero
- **Fixable in service code?** YES — usually needs exception handling in the orchestrator
- **Common in:** massive (workers), journal (background tasks), copilot (eval loops)

### API / External Service Timeouts
- **Symptom:** `TimeoutError`, `asyncio.TimeoutError`, `aiohttp.ClientError`
- **Cause:** External API down, rate limited, bad API key
- **Fixable in service code?** Only if timeout config is too aggressive. Usually NO (transient)

### WebSocket Disconnects (massive only)
- **Symptom:** `received 1008 (policy violation)`, `WebSocket connection closed`
- **Cause:** Market data provider rejecting connection (auth, rate limit, protocol)
- **Fixable in service code?** NO — transient or config issue. Service auto-reconnects after 5s

### Port Conflicts
- **Symptom:** `EADDRINUSE`, `Address already in use`
- **Cause:** Previous instance still running on the port
- **Fixable in service code?** NO — needs `kill $(lsof -ti:{port})`

### MySQL Connection Failures
- **Symptom:** `mysql.connector.errors.InterfaceError`, `Can't connect to MySQL server`
- **Cause:** MySQL not running, wrong credentials, database doesn't exist
- **Fixable in service code?** NO — infrastructure issue
- **Services affected:** journal (port 3002), sse (port 3001)

### Key/Attribute Errors from Bad Data
- **Symptom:** `KeyError`, `TypeError: 'NoneType'`, `AttributeError`
- **Cause:** Redis key missing or contains unexpected data shape
- **Fixable in service code?** YES — add defensive checks, handle None/missing keys
- **Common pattern:** Service reads `redis.get("massive:spot")` but massive isn't running yet

## 6. Service Communication

**Redis Pub/Sub Channels (market-redis):**
- `massive:spot` — live spot prices (SPX, NDX, VIX, etc.)
- `copilot:alerts:events` — alert triggers
- `copilot:commentary:message` — market observations
- `vexy:model:playbyplay` — Vexy epoch/event commentary
- `vigil:events` — market event detections
- `alerts:sync` (system-redis) — journal notifies copilot of alert changes

**Redis Key/Value (market-redis):**
- `massive:heatmap:model:{symbol}:latest` — GEX heatmap snapshots
- `massive:gex:model` — aggregate GEX model
- `massive:chain:latest` — options chain snapshot
- `copilot:mel:snapshot` — model effectiveness scores
- `copilot:adi:snapshot` — canonical market state

**HTTP Proxy Routes (sse -> backends):**
- `/api/logs/*`, `/api/trades/*`, `/api/journals/*`, `/api/leaderboard*` -> journal (localhost:3002)
- `/api/vexy/*` -> vexy_ai (localhost:3005)

**Heartbeat Pattern:**
- Every service publishes `{service}:heartbeat` to system-redis with TTL
- Fast services (massive, journal, copilot, sse): 5s interval, 15s TTL
- Slower services (vexy_ai, content_anal): 15s interval, 45s TTL
- HealthCollector checks every 15 seconds, fires `service_down` when key expires AND PID is dead

## 7. Diagnosis Checklist

When diagnosing a crashed service, follow this order:

1. **Read the log** — Look for the final exception/traceback before the crash. The error type tells you the category (import error, Redis error, asyncio crash, etc.)

2. **Identify the error category** — Match against Section 5. Is it a code bug or infrastructure issue?

3. **Check the traceback path** — Is the crash in `services/{name}/` code (fixable) or in `shared/` or external libraries (not fixable)?

4. **Check dependencies** — Look at the health snapshot. If upstream services are dead (e.g., massive is down and copilot crashed), the root cause is likely missing data, not a code bug

5. **Determine fixability:**
   - YES: Bug in `services/{name}/` code (import error, missing exception handling, bad logic)
   - NO: Infrastructure (Redis down, MySQL down, port conflict), shared code bug, transient error, external API issue, upstream service dependency
