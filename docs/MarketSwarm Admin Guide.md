# # MarketSwarm Admin Guide

This guide shows **exactly** how to run the MarketSwarm admin console, load the “truth,” and wire services for self-discovery. It assumes Docker is running and you’re in the project root.

Only admins should have this file. Do **not** commit secrets.

⸻

### 0) Checklist (one-time)
* Docker Desktop + Compose installed
* Project-local venv **not required** to activate manually (./admin manages it)
* Redis exposed to localhost (see §1.1)
* Create local admin env: .env.admin (see §1.2)
* Create truth.json and truth_secrets.json locally (see §2)

⠀
⸻

### 1) Host & Admin Environment

### 1.1 Expose Redis to localhost

In docker-compose.yml:
```yaml
main-redis:
  image: redis:7-alpine
  command: ["redis-server", "--appendonly", "yes"]
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
    interval: 10s
    timeout: 3s
    retries: 5
    start_period: 5s
  ports:
    - "127.0.0.1:6379:6379"   # host-only bind
  restart: unless-stopped
```
Apply:
```bash
docker compose up -d main-redis
docker compose exec -T main-redis redis-cli PING   # should return PONG
```
### 1.2 Admin env (gitignored)

Create .env.admin in repo root:
```dotenv
BOOTSTRAP_REDIS_URL=redis://localhost:6379
TRUTH_REDIS_KEY=truth:doc
TRUTH_FILE=/Users/ernie/.marketswarm/truth.json
TRUTH_SECRETS_FILE=/Users/ernie/.marketswarm/truth_secrets.json
```
**Note:** We do **not** use UID/GID or build-time env here.

### 1.3 Bootstrap the admin tool
```bash
chmod +x admin
./admin setup           # creates .venv and installs redis client there
./admin print-python    # shows the interpreter it will use (./.venv/bin/python)
```

⸻

### 2) Prepare Truth Files (local only)

Create the folder and files referenced in .env.admin:

```bash
mkdir -p ~/.marketswarm
```

~/.marketswarm/truth.json (example; adjust as needed):
```json
{
  "version": "1.0",
  "core": {
    "redis_main_url": "redis://main-redis:6379",
    "redis_market_url": "redis://market-redis:6379?password=swarmpass",
    "polygon_api_key": "",
    "system_ts": 0
  },
  "heartbeats": {
    "massive": { "id": "massive", "frequency": 5, "status": "active" },
    "logger": { "id": "logger", "frequency": 10, "status": "active" },
    "mesh_coordinator": { "id": "mesh_coordinator", "frequency": 3, "status": "active" },
    "rss_agg": { "id": "rss_agg", "frequency": 30, "status": "active" },
    "vexy_ai": { "id": "vexy_ai", "frequency": 15, "status": "active" }
  },
  "components": {
    "massive": {
      "meta": {
        "name": "Massive",
        "description": "Market data gateway (formerly Polygon): REST/WebSocket to ingest market data and publish to Market Redis.",
        "service_id": "massive"
      },
      "market_redis_setup": { "init_keys": ["market_prices", "spot_fetches"] }
    },
    "logger": {
      "meta": {
        "name": "Logger",
        "description": "Central log/telemetry collector and channel forwarder.",
        "service_id": "logger"
      },
      "log_channels": ["heartbeats", "errors"]
    },
    "mesh_coordinator": {
      "meta": {
        "name": "Mesh Coordinator",
        "description": "Dispatch coordinator for task queues between services.",
        "service_id": "mesh_coordinator"
      },
      "dispatch_queues": ["vexy_tasks", "rss_updates"]
    },
    "rss_agg": {
      "meta": {
        "name": "RSS Ingestor",
        "description": "Polls configured RSS feeds and publishes items into Redis.",
        "service_id": "rss_agg"
      },
      "poll_interval_min": 5,
      "enabled_categories": ["tech", "world"],
      "categories": {
        "tech": [
          "https://hnrss.org/frontpage",
          "https://feeds.arstechnica.com/arstechnica/index"
        ],
        "world": [
          "https://feeds.bbci.co.uk/news/rss.xml",
          "https://feeds.reuters.com/reuters/topNews"
        ],
        "macro": [
          "https://www.federalreserve.gov/feeds/press_all.xml"
        ]
      }
    },
    "vexy_ai": {
      "meta": {
        "name": "Vexy AI",
        "description": "Consumes RSS items, produces summaries/analysis back to Redis.",
        "service_id": "vexy_ai"
      },
      "model": "gpt-4o-mini",
      "prompt_template": "Analyze: {data}"
    }
  }
}
```

~/.marketswarm/truth_secrets.json (placeholders are fine; do **not** commit):
```json
{
  "secrets": {
    "massive": { "api_key": "PUT_MASSIVE_API_KEY_HERE" },
    "vexy_ai": { "openai_api_key": "PUT_OPENAI_KEY_HERE" },
    "rss_agg": { "user_agent": "MarketSwarm/1.0 (+https://your.site/contact)" }
  }
}
```

⸻

**3) Admin Commands (day-to-day)**

**3.1 Load the truth**
```bash
./admin load-truth
```

This merges truth.json + truth_secrets.json and writes:
* truth:doc (full merged doc)
* truth:version
* truth:ts

⠀
### 3.2 Inspect components (with metadata)
```bash
./admin components
./admin components --json   # machine-readable
```

**3.3 Wire services to components (self-discovery)**
```bash
./admin register --service-id rss_agg  --component rss_agg
./admin register --service-id massive  --component massive
./admin register --service-id vexy_ai  --component vexy_ai
./admin services
```

Each service should run with:
```yaml
environment:
  SERVICE_ID: "<its id>"                # e.g., rss_agg
  BOOTSTRAP_REDIS_URL: "redis://main-redis:6379"
```

> Services use SERVICE_ID to fetch their config + secrets from truth:doc.

### 3.4 Show mapping + config for one service
```bash
./admin show --service-id massive
```

Prints component config and **names** of secret fields (never values).

### 3.5 Check keys
```bash
./admin keys
```

Shows presence and counts of the admin keys.

⸻

### 4) Env Vars (admin tool)
| **Variable** | **Purpose** | **Default** |
|:-:|:-:|:-:|
| BOOTSTRAP_REDIS_URL | Redis URL used by admin and services | redis://localhost:6379 in .env.admin; services use redis://main-redis:6379 inside Compose |
| TRUTH_REDIS_KEY | Redis key storing merged truth | truth:doc |
| TRUTH_FILE | Path to local truth.json | *(none; required for load)* |
| TRUTH_SECRETS_FILE | Path to local truth_secrets.json | *(optional)* |
> The admin wrapper **whitelists** these keys from .env.admin. It ignores build-time vars like UID/GID.

⸻

### 5) Troubleshooting

**“Missing dependency ‘redis’” when running ./admin**
* Run ./admin setup (installs into ./.venv which the wrapper always uses).
* Or: ./.venv/bin/python -m pip install 'redis>=5.0'.

⠀
**Error 8 connecting to main-redis:6379 (nodename unknown)**
* You’re on the host. Use BOOTSTRAP_REDIS_URL=redis://localhost:6379 and expose main-redis with 127.0.0.1:6379:6379 (see §1.1).

⠀
**FileNotFoundError: truth.json**
* Create the files at the paths in .env.admin, or pass --truth/--secrets explicitly.

⠀
**Compose error: invalid spec: :/app/truth.json:ro**
* A service (e.g., a legacy truth_sync) referenced ${TRUTH_FILE}/${TRUTH_SECRETS_FILE} without defaults. Remove that service or gate it behind a profile with safe fallbacks.

⠀
**Shell error: UID: readonly variable**
* Don’t export UID/GID in admin env. The wrapper ignores them; .env.admin should only include the admin keys above.

⠀
⸻

### 6) Optional: One-shot verification
```bash
# Verify Redis is reachable from host
redis-cli -u redis://localhost:6379 PING

# Verify truth is present after load
./admin keys
./admin components
./admin show --service-id rss_agg
```

⸻

### 7) Security Notes
* Keep truth_secrets.json out of the repo (.gitignore).
* The admin wrapper never prints secret values—only names.
* Redis port is bound to 127.0.0.1 (localhost only). Do not expose externally.

⠀
⸻

### 8) Command Cheat-Sheet
```bash
# bootstrap admin tool
./admin setup

# load/inspect truth
./admin load-truth
./admin components
./admin components --json
./admin keys

# service mapping
./admin register --service-id rss_agg --component rss_agg
./admin services
./admin show --service-id rss_agg

# diagnostics
./admin print-python
```

