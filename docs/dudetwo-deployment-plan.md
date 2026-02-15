# MarketSwarm — DudeTwo Deployment Plan

> **Purpose:** Full setup guide for deploying MarketSwarm on DudeTwo, replacing the old MVP.
> **Reference Machine:** DudeOne (192.168.1.11) — current production.
> **Proxy Server:** MiniThree (100.94.9.60) — nginx reverse proxy, SSL termination.
> **Domain:** flyonthewall.io (Let's Encrypt SSL on MiniThree).
>
> DudeTwo is currently offline. This plan is ready to execute when it comes online.

---

## Table of Contents

1. [Network Topology](#1-network-topology)
2. [Prerequisites & OS Setup](#2-prerequisites--os-setup)
3. [Clone Repository](#3-clone-repository)
4. [Python Environment](#4-python-environment)
5. [Node.js Environment](#5-nodejs-environment)
6. [Redis Setup (4 Instances)](#6-redis-setup-4-instances)
7. [MySQL Setup](#7-mysql-setup)
8. [Truth Configuration System](#8-truth-configuration-system)
9. [Environment Files & Secrets](#9-environment-files--secrets)
10. [Service Inventory & Startup Order](#10-service-inventory--startup-order)
11. [Admin Server (Service Manager)](#11-admin-server-service-manager)
12. [UI Build (React Frontend)](#12-ui-build-react-frontend)
13. [Nginx Configuration (MiniThree)](#13-nginx-configuration-minithree)
14. [SSL Certificates](#14-ssl-certificates)
15. [Tier Gating (Production Access Control)](#15-tier-gating-production-access-control)
16. [AutoHealer](#16-autohealer)
17. [Health Verification Checklist](#17-health-verification-checklist)
18. [Deployment Script](#18-deployment-script)
19. [Rollback Plan](#19-rollback-plan)
20. [Post-Deploy Monitoring](#20-post-deploy-monitoring)

---

## 1. Network Topology

```
                     Internet
                        │
                   ┌────▼────┐
                   │  Nginx  │  flyonthewall.io
                   │MiniThree│  100.94.9.60
                   │  :443   │  SSL termination
                   └────┬────┘
                        │ LAN (proxy_pass)
                   ┌────▼────┐
                   │ DudeTwo │  <IP TBD>
                   │ Backend │  All services run here
                   └─────────┘
```

**Current state:** MiniThree proxies to DudeOne at 192.168.1.11.
**Target state:** MiniThree proxies to DudeTwo at `<DUDETWO_IP>`.

All upstream IPs in the nginx config must change from `192.168.1.11` → `<DUDETWO_IP>`.

**Ports used on DudeTwo (all bound to 127.0.0.1 or LAN IP):**

| Port  | Service           | Protocol |
|-------|-------------------|----------|
| 3001  | SSE Gateway       | HTTP     |
| 3002  | Journal API       | HTTP     |
| 3005  | Vexy AI           | HTTP     |
| 3006  | Vexy Proxy        | HTTP     |
| 3007  | Vexy Hydrator     | HTTP     |
| 3306  | MySQL             | TCP      |
| 5173  | UI (Vite/static)  | HTTP     |
| 6379  | system-redis      | TCP      |
| 6380  | market-redis      | TCP      |
| 6381  | intel-redis       | TCP      |
| 6382  | echo-redis        | TCP      |
| 8095  | Copilot           | HTTP/WS  |
| 8099  | Admin Server      | HTTP     |

---

## 2. Prerequisites & OS Setup

DudeTwo needs these installed before anything else.

### macOS (if Mac)

```bash
# Install Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Core dependencies
brew install python@3.12 node redis mysql git bash

# Verify versions
python3 --version   # 3.12+
node --version      # 18+
redis-server --version  # 7+
mysql --version     # 8+
git --version
```

### Linux (Ubuntu/Debian)

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.12 python3.12-venv python3-pip \
    nodejs npm redis-server mysql-server git curl build-essential

# Node.js 18+ (if apt version is old)
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs
```

### Firewall

Open ports for MiniThree's proxy connections. Redis and MySQL should be local-only:

```bash
# Allow MiniThree (100.94.9.60) to reach service ports
# Ports: 3001, 3002, 3005, 3006, 3007, 5173, 8095
# Redis (6379-6382) and MySQL (3306) stay local (127.0.0.1 bind)
# Admin (8099) stays local unless needed remotely
```

---

## 3. Clone Repository

```bash
# Create user (or use existing)
# Assumes user: ernie (adjust if different on DudeTwo)

cd ~
git clone git@github.com:<org>/MarketSwarm.git
cd MarketSwarm

# Create required directories
mkdir -p logs .pids redis/{system,market,intel}/data
```

---

## 4. Python Environment

```bash
cd ~/MarketSwarm

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install root requirements
pip install -r requirements.txt

# Install service-specific requirements
pip install -r services/copilot/requirements.txt
pip install -r services/vexy_ai/requirements.txt
pip install -r services/rss_agg/requirements.txt
pip install -r services/mesh/requirements.txt
pip install -r services/healer/requirements.txt

# Install uvicorn for admin server + vexy_ai (FastAPI)
pip install uvicorn fastapi pydantic

# Verify key packages
python -c "import redis; print('redis OK')"
python -c "import mysql.connector; print('mysql OK')"
python -c "import uvicorn; print('uvicorn OK')"
python -c "import openai; print('openai OK')"
```

**Important:** The admin server **must** be started with `.venv/bin/python`, not system Python. System Python does NOT have `uvicorn`.

---

## 5. Node.js Environment

```bash
# SSE Gateway
cd ~/MarketSwarm/services/sse
npm install

# Vexy Proxy
cd ~/MarketSwarm/services/vexy_proxy
npm install

# UI (React frontend)
cd ~/MarketSwarm/ui
npm install

cd ~/MarketSwarm
```

---

## 6. Redis Setup (4 Instances)

MarketSwarm uses 4 isolated Redis instances for different data domains.

### Configuration

Create/update `ms-busses.env` in the MarketSwarm root (adjust paths for DudeTwo):

```bash
# ms-busses.env
MS_ROOT="${HOME}/MarketSwarm"

# Adjust BREW_PREFIX for platform:
# macOS Homebrew: /opt/homebrew
# Linux: /usr (redis-server at /usr/bin/redis-server)
BREW_PREFIX="/opt/homebrew"
BASH_PATH="${BREW_PREFIX}/bin/bash"
REDIS_SERVER_PATH="${BREW_PREFIX}/bin/redis-server"
REDIS_CLI_PATH="${BREW_PREFIX}/bin/redis-cli"

REDIS_SYSTEM_PORT="6379"
REDIS_MARKET_PORT="6380"
REDIS_INTEL_PORT="6381"
REDIS_ECHO_PORT="6382"

REDIS_SYSTEM_URL="redis://localhost:6379"
REDIS_MARKET_URL="redis://localhost:6380"
REDIS_INTEL_URL="redis://localhost:6381"
REDIS_ECHO_URL="redis://localhost:6382"

# Passwords (blank = no auth, set for production)
REDIS_SYSTEM_PASS=""
REDIS_MARKET_PASS=""
REDIS_INTEL_PASS=""
REDIS_ECHO_PASS=""

TRUTH_JSON_PATH="${MS_ROOT}/scripts/truth.json"
```

### Start Redis

```bash
cd ~/MarketSwarm
./scripts/ms-busses.sh up

# Verify all 4 instances
./scripts/ms-busses.sh status
```

Each instance:
- Binds to `127.0.0.1` (local only)
- Saves RDB snapshots: every 900s/1 change, 300s/10 changes, 60s/10000 changes
- Logs to `logs/redis-{name}.log`
- PID files in `redis/{name}/redis.pid`
- Data in `redis/{name}/data/`

### Instance Roles

| Instance     | Port | Role | What's stored |
|--------------|------|------|---------------|
| system-redis | 6379 | Governance | Truth config, heartbeats, tier gates, mesh state, healer |
| market-redis | 6380 | Market data | Spot prices, options chains, GEX models, heatmaps, dealer gravity, vigil events |
| intel-redis  | 6381 | Intelligence | RSS feeds, enriched articles, sentiment, ML data (~1500 keys) |
| echo-redis   | 6382 | Cognitive memory | Vexy AI snapshots, activity tracking (no persistence, hot tier) |

### Memory Policy

All instances use `maxmemory: 0` (unlimited) and `noeviction`. Market-redis can use 1GB+ during active trading hours. Monitor with:

```bash
redis-cli -p 6379 info memory | grep used_memory_human
redis-cli -p 6380 info memory | grep used_memory_human
redis-cli -p 6381 info memory | grep used_memory_human
redis-cli -p 6382 info memory | grep used_memory_human
```

---

## 7. MySQL Setup

### Create Database and User

```bash
# Connect as root
mysql -u root

# Create database and user
CREATE DATABASE fotw_app CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'fotw_app'@'localhost' IDENTIFIED BY '<CHOOSE_STRONG_PASSWORD>';
GRANT ALL PRIVILEGES ON fotw_app.* TO 'fotw_app'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

### Schema Migration

The Journal service auto-migrates on startup via `services/journal/run_migration.py`. No manual schema setup needed — just create the empty database and user.

### Services Using MySQL

| Service | Connection | Purpose |
|---------|-----------|---------|
| SSE Gateway | `DATABASE_URL` env var | User sessions, activity tracking |
| Journal | `JOURNAL_MYSQL_*` env vars | Trade logs, journals, playbooks, alerts, positions |

### Database Connection Strings

```
# SSE Gateway format (in truth/components/sse.json):
DATABASE_URL=mysql://fotw_app:<password>@127.0.0.1:3306/fotw_app

# Journal format (in truth/components/journal.json):
JOURNAL_MYSQL_HOST=127.0.0.1
JOURNAL_MYSQL_PORT=3306
JOURNAL_MYSQL_USER=fotw_app
JOURNAL_MYSQL_PASSWORD=<password>
JOURNAL_MYSQL_DATABASE=fotw_app
```

---

## 8. Truth Configuration System

Truth is MarketSwarm's central configuration system. A JSON document is built from component files and loaded into system-redis.

### Structure

```
truth/
├── mm_node.json              # Root config: node name, env, Redis URLs, component list
└── components/
    ├── sse.json              # SSE Gateway config (ports, DB, session secret)
    ├── journal.json          # Journal config (MySQL creds, attachments path)
    ├── vexy_ai.json          # Vexy AI config (API keys, mode, prompts)
    ├── vexy_proxy.json       # Vexy Proxy config (port, target)
    ├── vexy_hydrator.json    # Hydrator config (port, echo-redis)
    ├── copilot.json          # Copilot config (MEL/ADI/alerts, API keys)
    ├── massive.json          # Massive config (Polygon API, symbols, WebSocket)
    ├── rss_agg.json          # RSS config (feeds, enrichment model)
    ├── content_anal.json     # Content analysis config
    ├── mesh.json             # Service mesh config
    ├── healer.json           # AutoHealer config
    ├── vigil.json            # Event vigilance config
    └── template.json         # Template for new services
```

### Key Values to Update for DudeTwo

In `truth/mm_node.json`:
- `node.name`: Change to `"marketswarm-dudetwo"` (or keep `"marketswarm-local"`)
- `node.env`: Set to `"production"` for production mode
- `buses.*`: Redis URLs stay as `redis://127.0.0.1:*` (local)

In component JSON files:
- Update MySQL passwords in `sse.json` and `journal.json`
- Update API keys: `XAI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` in vexy_ai, copilot, rss_agg
- Update `MASSIVE_API_KEY` (Polygon) in `massive.json`
- Update `APP_SESSION_SECRET` in `sse.json` (generate new one)
- Update file paths if user home directory differs

### Loading Truth

```bash
cd ~/MarketSwarm

# Build the combined truth document and load into system-redis
./scripts/ms-truth.sh --load

# Verify it loaded
redis-cli -p 6379 GET truth | python3 -m json.tool | head -20
```

All services read their config from Truth on startup via `shared/setup_base.py`. Services do NOT use `.env` files — everything comes from Truth (Redis key `truth` on system-redis).

---

## 9. Environment Files & Secrets

### Secrets to Configure (in Truth component files)

| Secret | Where Used | Component File |
|--------|-----------|----------------|
| `MASSIVE_API_KEY` | Polygon.io market data | `massive.json` |
| `XAI_API_KEY` | xAI/Grok LLM | `vexy_ai.json`, `copilot.json` |
| `OPENAI_API_KEY` | OpenAI GPT | `vexy_ai.json`, `copilot.json`, `rss_agg.json` |
| `ANTHROPIC_API_KEY` | Claude API | `copilot.json` |
| `APP_SESSION_SECRET` | Session cookie signing | `sse.json` |
| `JOURNAL_MYSQL_PASSWORD` | MySQL access | `journal.json` |
| `DATABASE_URL` | MySQL access (SSE) | `sse.json` |
| `WP_JWT_SECRET` | WordPress SSO JWT validation | `sse.json` (auth config) |

### WordPress SSO Configuration

The SSE Gateway validates JWTs from the WordPress site for authentication. In `sse.json` env section:

```json
{
  "WP_JWT_SECRET": "<shared secret with WordPress>",
  "PUBLIC_MODE": "0"
}
```

Set `PUBLIC_MODE=0` for production (auth enforced). Set to `1` only for development/testing.

### File: `.env` (root)

```bash
# Only needed for standalone scripts, not services
POLYGON_API_KEY=<key>
MODE=historical
GROUP=spx_complex
```

### File: `ms-busses.env`

Already covered in Redis section above. Adjust paths for DudeTwo's platform.

---

## 10. Service Inventory & Startup Order

### All Services

| # | Service | Language | Entry Point | Port | Redis Used | Purpose |
|---|---------|----------|-------------|------|------------|---------|
| 1 | massive | Python | `services/massive/main.py` | — | market | Market data ingestion (spot, options, WebSocket) |
| 2 | rss_agg | Python | `services/rss_agg/main.py` | — | intel | RSS feed aggregation & LLM enrichment |
| 3 | content_anal | Python | `services/content_anal/main.py` | — | intel | Content analysis & classification |
| 4 | vigil | Python | `services/vigil/main.py` | — | market | Event vigilance & anomaly detection |
| 5 | copilot | Python | `services/copilot/main.py` | 8095 | market, system | MEL, ADI, commentary, alerts |
| 6 | vexy_ai | Python | `services/vexy_ai/main.py` | 3005 | market, intel, echo | AI assistant (chat, routines, journal, ML) |
| 7 | vexy_proxy | Node.js | `services/vexy_proxy/src/index.js` | 3006 | — | Low-latency auth proxy for Vexy |
| 8 | vexy_hydrator | Python | `services/vexy_hydrator/main.py` | 3007 | echo | Cognitive memory hydration |
| 9 | journal | Python | `services/journal/main.py` | 3002 | market, system | Trade journal, alerts, playbooks (MySQL) |
| 10 | sse | Node.js | `services/sse/src/index.js` | 3001 | market, system, intel | SSE Gateway, auth, API proxy (MySQL) |
| 11 | mesh | Python | `services/mesh/main.py` | — | system | Service mesh coordination |
| 12 | healer | Python | (via admin) | — | system | AutoHealer (Claude CLI subprocess) |

### Startup Order

Dependencies flow bottom-up. Start in this order:

```
Phase 1 — Infrastructure (must be running first):
  1. Redis (all 4 instances)
  2. MySQL
  3. Truth (load into Redis)

Phase 2 — Data Producers (no dependencies on other services):
  4. massive        — market data ingestion
  5. rss_agg        — RSS feed aggregation

Phase 3 — Analysis Layer:
  6. content_anal   — depends on intel-redis data
  7. vigil          — depends on market-redis data
  8. copilot        — depends on massive (market data)

Phase 4 — AI & Journal:
  9. vexy_ai        — depends on massive, rss_agg, vigil
  10. vexy_proxy    — depends on vexy_ai
  11. vexy_hydrator — depends on vexy_ai, echo-redis
  12. journal       — depends on massive (market data)

Phase 5 — Gateway (last, depends on all backend services):
  13. sse           — proxies to journal, vexy_ai; serves UI
  14. mesh          — monitors all services
  15. Admin server  — manages all services
```

### Starting Services

**Option A: Via Admin Server (recommended)**

```bash
# Start admin server first
~/MarketSwarm/.venv/bin/python scripts/service_manager.py serve &

# Then start services via API
curl -X POST http://localhost:8099/api/services/massive/start
curl -X POST http://localhost:8099/api/services/rss_agg/start
# ... etc
```

**Option B: Via shell scripts**

```bash
# Each service has a startup script
./scripts/ms-massive.sh
./scripts/ms-sse.sh
# ... etc
```

**Option C: Direct process launch**

```bash
PYTHON=~/MarketSwarm/.venv/bin/python

# Python services
nohup $PYTHON services/massive/main.py >> logs/massive.log 2>&1 &
nohup $PYTHON services/rss_agg/main.py >> logs/rss_agg.log 2>&1 &
nohup $PYTHON services/content_anal/main.py >> logs/content_anal.log 2>&1 &
nohup $PYTHON services/vigil/main.py >> logs/vigil.log 2>&1 &
nohup $PYTHON services/copilot/main.py >> logs/copilot.log 2>&1 &
nohup $PYTHON services/vexy_ai/main.py >> logs/vexy_ai.log 2>&1 &
nohup $PYTHON services/vexy_hydrator/main.py >> logs/vexy_hydrator.log 2>&1 &
nohup $PYTHON services/journal/main.py >> logs/journal.log 2>&1 &
nohup $PYTHON services/mesh/main.py >> logs/mesh.log 2>&1 &

# Node.js services
nohup node services/sse/src/index.js >> logs/sse.log 2>&1 &
nohup node services/vexy_proxy/src/index.js >> logs/vexy_proxy.log 2>&1 &
```

### Heartbeat Pattern

All services publish heartbeats to system-redis:
- Key: `{service}:heartbeat` with TTL (SET + EX)
- Payload: `{"service": "name", "ts": unix_timestamp}`
- Typical interval: 5-15 seconds
- Key exists = alive, key expired = dead

---

## 11. Admin Server (Service Manager)

The admin server provides a web UI and REST API for managing all services.

```bash
# MUST use .venv Python (uvicorn not in system Python)
~/MarketSwarm/.venv/bin/python scripts/service_manager.py serve
```

- **Port:** 8099
- **Web UI:** http://localhost:8099
- **API:** http://localhost:8099/api/*

### Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Admin server health |
| `/api/services` | GET | All service status |
| `/api/services/{name}/start` | POST | Start a service |
| `/api/services/{name}/stop` | POST | Stop a service |
| `/api/services/{name}/restart` | POST | Restart a service |
| `/api/health/deep` | GET | Deep health (Redis, heartbeats, HTTP) |
| `/api/health/healer/toggle` | POST | Enable/disable AutoHealer |
| `/api/tier-gates` | GET/POST | Tier gating configuration |

### Features

- Live service status (5s refresh)
- Log viewing and tailing
- Health monitoring (Redis, heartbeats, HTTP checks)
- AutoHealer control
- Tier gate management
- Analytics dashboard

---

## 12. UI Build (React Frontend)

The React UI is built with Vite and served as static files.

### Build for Production

```bash
cd ~/MarketSwarm/ui
npm install
npx vite build
```

Output goes to `ui/dist/`. The SSE Gateway serves these files at the root path (`/`).

### Development Mode (optional)

```bash
cd ~/MarketSwarm/ui
npx vite dev --host 0.0.0.0 --port 5173
```

In production, `express.static(UI_DIST)` in the SSE Gateway serves the built files. No separate dev server needed.

### Key UI Dependencies

- React 19.2, TypeScript 5.9
- echarts 6.0 (charting)
- lightweight-charts 5.1 (TradingView charts)
- react-markdown (Vexy output)
- Vite 7.2 (bundler)

---

## 13. Nginx Configuration (MiniThree)

MiniThree currently proxies the old MVP. The nginx config needs updating to point to DudeTwo.

### What Changes

The **only change** is the upstream server IPs. Replace `192.168.1.11` with DudeTwo's IP:

```nginx
# BEFORE (DudeOne):
upstream static_frontend {
    server 192.168.1.11:5173;
}
upstream sse_gateway {
    server 192.168.1.11:3001;
}
upstream journal_api {
    server 192.168.1.11:3002;
}
upstream vexy_api {
    server 192.168.1.11:3005;
}
upstream copilot_api {
    server 192.168.1.11:8095;
}
upstream vexy_proxy {
    server 192.168.1.11:3006;
}

# AFTER (DudeTwo):
upstream static_frontend {
    server <DUDETWO_IP>:5173;
}
upstream sse_gateway {
    server <DUDETWO_IP>:3001;
}
# ... etc for all upstreams
```

### Route Map (what nginx proxies where)

| Path | Upstream | Port | Service |
|------|----------|------|---------|
| `/sse/*` | sse_gateway | 3001 | SSE streams (no buffering, 24h timeout) |
| `/api/auth/*` | sse_gateway | 3001 | Authentication |
| `/api/models/*` | sse_gateway | 3001 | Market data snapshots |
| `/api/health` | sse_gateway | 3001 | Health check |
| `/api/admin/*` | sse_gateway | 3001 | Admin endpoints |
| `/api/positions*` | sse_gateway | 3001 | Position management |
| `/api/vexy/chat` | vexy_proxy | 3006 | Chat (latency-sensitive) |
| `/api/vexy/interaction` | vexy_proxy | 3006 | Interactions |
| `/api/vexy/*` | vexy_api | 3005 | All other Vexy endpoints |
| `/api/logs` | journal_api | 3002 | Trade logs |
| `/api/journal/*` | journal_api | 3002 | Journal entries |
| `/api/trades` | journal_api | 3002 | Trade history |
| `/api/playbook/*` | journal_api | 3002 | Playbooks |
| `/api/alerts` | journal_api | 3002 | Alerts |
| `/api/risk-graph/*` | journal_api | 3002 | Risk graph data |
| `/api/analytics` | journal_api | 3002 | Analytics |
| `/api/mel/*` | copilot_api | 8095 | Model effectiveness |
| `/api/adi/*` | copilot_api | 8095 | Abnormality detection |
| `/ws/mel` | copilot_api | 8095 | MEL WebSocket |
| `/ws/commentary` | copilot_api | 8095 | Commentary WebSocket |
| `/api/*` (catch-all) | sse_gateway | 3001 | Everything else (tier gates, imports, etc.) |
| `/` | static_frontend | 5173 | React app |

### Deployment Steps on MiniThree

```bash
# 1. Create DudeTwo version of config
cd ~/MarketSwarm
cp deploy/marketswarm-https.conf deploy/marketswarm-https-dudetwo.conf

# 2. Edit: replace all 192.168.1.11 with <DUDETWO_IP>
sed -i 's/192.168.1.11/<DUDETWO_IP>/g' deploy/marketswarm-https-dudetwo.conf

# 3. Copy to MiniThree
scp deploy/marketswarm-https-dudetwo.conf MiniThree:/tmp/marketswarm-https.conf

# 4. On MiniThree: test and reload
ssh MiniThree
cp /tmp/marketswarm-https.conf /opt/homebrew/etc/nginx/servers/marketswarm.conf
nginx -t                    # Test config syntax
brew services reload nginx  # Reload nginx
```

### Or use the deploy script

```bash
./deploy/deploy.sh --nginx
```

(After updating the config file with DudeTwo's IP.)

---

## 14. SSL Certificates

SSL is handled on MiniThree via Let's Encrypt. **No changes needed on DudeTwo** — it receives plain HTTP from nginx.

### Current SSL Setup (MiniThree)

```
Certificate: /etc/letsencrypt/live/flyonthewall.io/fullchain.pem
Private Key: /etc/letsencrypt/live/flyonthewall.io/privkey.pem
ACME root:   /opt/homebrew/var/www/letsencrypt/
```

### Renewal

Let's Encrypt renews automatically via the ACME challenge path in nginx:

```nginx
location ^~ /.well-known/acme-challenge/ {
    root /opt/homebrew/var/www/letsencrypt;
}
```

Verify renewal works: `sudo certbot renew --dry-run` on MiniThree.

---

## 15. Tier Gating (Production Access Control)

The tier gating system controls which subscription tiers can access MarketSwarm.

### Tiers (lowest → highest)

1. **observer** — view-only, lowest tier
2. **activator** — basic access
3. **navigator** — full access
4. **coaching** — premium (always allowed)
5. **administrator** — always allowed

### Configuration

Set via Admin UI or API:

```bash
# Toggle Observer off (production default)
curl -X POST http://localhost:8099/api/tier-gates \
  -H 'Content-Type: application/json' \
  -d '{"allowed_tiers": {"observer": false, "activator": true, "navigator": true}}'
```

### How It Works

1. User visits flyonthewall.io → redirected to WordPress SSO
2. WordPress issues JWT with user roles + subscription tier
3. SSE Gateway validates JWT, resolves tier via `tierFromRoles()`
4. **Global middleware** checks `allowed_tiers` on every authenticated request
5. If tier is blocked → 403 response, session cookie cleared
6. Blocked users never get a database row (rejected before DB upsert)

### Production Setting

For production, Observer should be toggled OFF:

```json
{
  "allowed_tiers": {
    "observer": false,
    "activator": true,
    "navigator": true,
    "coaching": true
  }
}
```

This config is stored in system-redis and propagated via pub/sub (`tier_gates:updated`). Changes take effect immediately on all connected clients.

---

## 16. AutoHealer

The AutoHealer monitors services and uses Claude CLI to diagnose and fix crashes.

### Requirements

- Claude CLI installed on DudeTwo (`/opt/homebrew/bin/claude` or equivalent)
- Logged into Claude terminal subscription
- Admin server running

### Enable

```bash
curl -X POST http://localhost:8099/api/health/healer/toggle \
  -H 'Content-Type: application/json' \
  -d '{"enabled": true}'
```

### How It Works

1. HealthCollector detects alive→dead transition for a service
2. Phase 1: Claude CLI diagnoses (read-only, 3min timeout)
3. Phase 2: Claude CLI applies fix (guarded edits, git stash safety)
4. Verify: service restarted, heartbeat checked
5. Notifications sent to Slack

### Configuration

- Cooldown: 600 seconds between heal attempts per service
- Context: `docs/healer-context.md` injected into prompt
- Last 200 log lines pre-read into prompt
- Health snapshot (Redis status, heartbeats, PIDs) injected

---

## 17. Health Verification Checklist

Run this after deployment to verify everything is working.

### Infrastructure

```bash
# Redis — all 4 should respond PONG
redis-cli -p 6379 ping    # system
redis-cli -p 6380 ping    # market
redis-cli -p 6381 ping    # intel
redis-cli -p 6382 ping    # echo

# MySQL
mysql -u fotw_app -p -e "SELECT 1;"

# Truth loaded
redis-cli -p 6379 EXISTS truth   # Should return 1
```

### Services

```bash
# HTTP health checks
curl http://localhost:3001/api/health   # SSE Gateway
curl http://localhost:3002/health       # Journal
curl http://localhost:3005/health       # Vexy AI
curl http://localhost:3006/health       # Vexy Proxy
curl http://localhost:3007/health       # Vexy Hydrator
curl http://localhost:8095/health       # Copilot
curl http://localhost:8099/api/health   # Admin Server
```

### Heartbeats

```bash
# Check all heartbeat keys in system-redis
redis-cli -p 6379 KEYS '*:heartbeat'

# Each should have a recent timestamp
redis-cli -p 6379 GET massive:heartbeat
redis-cli -p 6379 GET sse:heartbeat
redis-cli -p 6379 GET journal:heartbeat
redis-cli -p 6379 GET vexy_ai:heartbeat
redis-cli -p 6379 GET copilot:heartbeat
```

### End-to-End (via MiniThree)

```bash
# From any machine:
curl -sk https://flyonthewall.io/api/health
# Should return: {"status":"healthy","service":"sse-gateway",...}

# SSE stream test:
curl -sk -N https://flyonthewall.io/sse/spot
# Should receive SSE events (data: {...})
```

### Deep Health (via Admin)

```bash
curl http://localhost:8099/api/health/deep | python3 -m json.tool
# Should show all Redis UP, heartbeats alive, health score > 0.8
```

### Or use the deploy script

```bash
./deploy/deploy.sh --verify
```

---

## 18. Deployment Script

The existing `deploy/deploy.sh` automates most of this. For DudeTwo, update:

1. `MARKETSWARM_DIR` — path on DudeTwo (default: `/Users/ernie/MarketSwarm`)
2. `NGINX_HOST` — MiniThree hostname (default: `MiniThree`)
3. `PYTHON` path — `.venv/bin/python3`

### Full Deploy (after initial setup)

```bash
cd ~/MarketSwarm
./deploy/deploy.sh
```

This runs: prerequisites → git pull → migrations → truth reload → UI build → restart services → sync nginx → verify health.

### Individual Steps

```bash
./deploy/deploy.sh --pull-only   # Just git pull
./deploy/deploy.sh --restart     # Just restart services
./deploy/deploy.sh --nginx       # Just sync nginx
./deploy/deploy.sh --status      # Check service status
./deploy/deploy.sh --verify      # HTTP health checks + nginx
```

---

## 19. Rollback Plan

If something goes wrong after deploying to DudeTwo:

### Quick Rollback (MiniThree nginx)

Point nginx back to DudeOne:

```bash
# On MiniThree
sed -i 's/<DUDETWO_IP>/192.168.1.11/g' /opt/homebrew/etc/nginx/servers/marketswarm.conf
nginx -t && brew services reload nginx
```

### Code Rollback (DudeTwo)

```bash
cd ~/MarketSwarm
git log --oneline -5          # Find the last known-good commit
git checkout <commit-hash>    # Roll back
./deploy/deploy.sh --restart  # Restart services
```

### Keep DudeOne Running

During migration, keep DudeOne running as a fallback. Only shut it down after DudeTwo is verified stable for 24+ hours.

---

## 20. Post-Deploy Monitoring

### Logs

```bash
# Tail all service logs
tail -f ~/MarketSwarm/logs/sse.log
tail -f ~/MarketSwarm/logs/journal.log
tail -f ~/MarketSwarm/logs/vexy_ai.log
tail -f ~/MarketSwarm/logs/copilot.log
tail -f ~/MarketSwarm/logs/massive.log
tail -f ~/MarketSwarm/logs/rss_agg.log
tail -f ~/MarketSwarm/logs/healer.log
```

### Admin Dashboard

http://localhost:8099 — live service status, health scores, log viewer.

### Key Metrics to Watch

- **Health score** > 0.8 (via `/api/health/deep`)
- **Redis memory** — market-redis can spike during market hours
- **SSE client count** — via `/api/health` response
- **Heartbeat status** — all services should show alive
- **MySQL connections** — watch for connection pool exhaustion

### Automated Monitoring

- AutoHealer watches for service crashes and attempts fixes
- HealthCollector runs every 30 seconds
- Heartbeats have TTL-based expiry (dead key = dead service)

---

## Execution Summary

When DudeTwo comes online, execute in this order:

```
1. OS setup + install prerequisites (brew/apt, Python, Node, Redis, MySQL, git)
2. Clone MarketSwarm repo
3. Create Python venv + install all requirements
4. Install Node deps (sse, vexy_proxy, ui)
5. Create ms-busses.env for DudeTwo's paths
6. Start Redis (4 instances via ms-busses.sh up)
7. Create MySQL database + user
8. Update Truth component configs (API keys, passwords, paths)
9. Load Truth into Redis (ms-truth.sh --load)
10. Build UI (npx vite build in ui/)
11. Start services in dependency order (Phase 2→5)
12. Start admin server
13. Run health verification checklist
14. Update nginx config with DudeTwo IP
15. Deploy nginx to MiniThree
16. Test end-to-end via https://flyonthewall.io
17. Set tier gates for production (Observer off)
18. Enable AutoHealer
19. Monitor for 24 hours before decommissioning DudeOne
```
