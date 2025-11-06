# # MarketSwarm

A small, modular system for sourcing, coordinating, and monitoring feeds and workers over a shared Redis bus. Design is **position‑first**: services read a single **truth** document, publish cheap **heartbeats**, and a tiny **Healer** converts missed beats into actionable alerts. A **Sentinel** watches the Healer itself.

> TL;DR
> * Single shared network for zero‑conf discovery.
> * Two Redis buses: system-redis (primary) and market-redis (optional lanes).
> * bootstrap seeds truth.json → truth:doc in both buses, then exits.
> * Services: rss_agg, massive, mesh, vexy_ai … each publishes <svc>:heartbeat.
> * healer subscribes to heartbeats and emits alerts to healer:alerts.
> * sentinel watches healer:heartbeat and emits healer_miss/healer_ok.

⠀
⸻

### Table of Contents
* [Architecture](#architecture)
* [Repository Layout](#repository-layout)
* [Prerequisites](#prerequisites)
* [Quick Start](#quick-start)
* [Configuration](#configuration)
* [Operating Guide](#operating-guide)
* [Observability](#observability)
* [Troubleshooting](#troubleshooting)
* [Add a New Service](#add-a-new-service)
* [Message Contracts](#message-contracts)
* [License](#license)

⠀
⸻

### Architecture
```mermaid
flowchart LR
  subgraph marketswarm-bus (shared docker network)
    A[(system-redis:6379)]:::bus
    B[(market-redis:6379)]:::bus
    BS[[bootstrap (one-shot)]]
    R[rss_agg]
    M[massive]
    X[mesh]
    V[vexy_ai]
    H[healer]
    S[sentinel]
  end

  BS --> A
  BS --> B

  R --> A
  M --> A
  X --> A
  V --> A
  H --> A
  S --> A

  classDef bus fill:#eef,stroke:#88f,stroke-width:1px
```

**Key decisions**
* **One network**: marketswarm-bus (external bridge) for stable name‑resolution (system-redis, market-redis).
* **Source of truth** in Redis: truth:doc (JSON). No file coupling at runtime.
* **Heartbeats as primitive**: tiny pub/sub messages → easy monitoring.
* **Healer warmup**: avoids false misses right after restarts.
* **Sentinel**: independent coverage of the Healer.

⠀
⸻

### Repository Layout
```text
MarketSwarm/
├── docker-compose.yml
├── truth.json                  # seeded into Redis by bootstrap
├── services/
│   ├── rss_agg/
│   ├── massive/
│   │   └── main.py
│   ├── mesh/
│   ├── vexy_ai/
│   ├── healer/
│   │   ├── monitor.py          # subscribes to heartbeats, emits alerts
│   │   └── notifier.py         # optional: webhook/email alerts
│   └── sentinel/
│       └── guard.py            # watches healer:heartbeat
└── logs/
```


⸻

### Prerequisites
* Docker and Docker Compose v2
* (macOS/Linux) redis-cli for local checks
* The external docker network exists:
```bash
docker network create marketswarm-bus || true
```


⸻

### Quick Start
1. **Seed truth** (idempotent; requires truth.json at repo root):
```bash
docker compose up --build --force-recreate bootstrap
```
⠀
2. **Bring up services** (pick the ones you need):
```bash
docker compose up -d system-redis market-redis
docker compose up -d rss_agg massive mesh vexy_ai healer sentinel
```
⠀
3. **Confirm heartbeats are monitored**:
```bash
docker compose exec system-redis redis-cli PUBSUB NUMSUB \
  rss_agg:heartbeat massive:heartbeat mesh:heartbeat vexy_ai:heartbeat
# expect each channel to report ≥ 1 subscriber (healer)
```
⠀
4. **Watch alerts**:
```bash
redis-cli -h 127.0.0.1 -p 6379 SUBSCRIBE healer:alerts
```
⠀

⸻

### Configuration

### Compose (selected services)
* **Redis buses**
  * system-redis: container 6379, host‑mapped 127.0.0.1:6379.
  * market-redis: container 6379, host‑mapped 127.0.0.1:6380.
  * Volumes: system_redis_data, market_redis_data (persist data across restarts).
* **Network**: all services attach to marketswarm-bus.
* **Internet access**: services that egress (e.g., massive, rss_agg, mesh) optionally set dns: [8.8.8.8, 8.8.4.4] for reliability.

⠀
### Truth (truth:doc) – examples

Minimal per‑service heartbeat:
```json
{
  "services": {
    "rss_agg": {
      "heartbeat": {
        "channel": "rss_agg:heartbeat",
        "interval_sec": 10,
        "redis_url": "redis://system-redis:6379"
      }
    }
  }
}
```

Healer wiring:
```json
{
  "services": {
    "healer": {
      "access_points": {
        "subscribe_to": [
          {"bus":"system-redis","key":"rss_agg:heartbeat"},
          {"bus":"system-redis","key":"massive:heartbeat"},
          {"bus":"system-redis","key":"mesh:heartbeat"},
          {"bus":"system-redis","key":"vexy_ai:heartbeat"}
        ],
        "publish_to": [
          {"bus":"system-redis","key":"healer:alerts"},
          {"bus":"system-redis","key":"healer:heartbeat"}
        ]
      },
      "threshold": {"heartbeat_cadence": 30}
    }
  }
}
```

### Healer environment (fallbacks)
* `REDIS_URL` / `TRUTH_REDIS_URL`, `TRUTH_REDIS_KEY` (default `truth:doc`)
* `DEFAULT_TIMEOUT_SEC` (used if truth lacks cadence)
* `ALERT_CHANNEL` (default `healer:alerts`)
* `HB_INTERVAL_SEC` (healer’s own beat; default 10s)
* Optional notifications via `notifier.py`:
  * `WEBHOOK_URL`, `WEBHOOK_TIMEOUT_SEC`
  * `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`, `SMTP_TO`

⠀
⸻

### Operating Guide

### Fresh init
```bash
docker compose down
docker network create marketswarm-bus || true
docker compose up --build --force-recreate bootstrap
docker compose up -d rss_agg massive mesh vexy_ai healer sentinel
```

### Reseed truth
```bash
docker compose up --build --force-recreate bootstrap
```

### Simulate failure & recovery
```bash
# trigger a miss
docker compose stop rss_agg
# expect a heartbeat_miss on healer:alerts after ~30s
# recover
docker compose start rss_agg
# expect heartbeat_ok shortly after first beat
```


⸻

### Observability

**Subscribers present?**
```bash
docker compose exec system-redis redis-cli PUBSUB NUMSUB \
  rss_agg:heartbeat massive:heartbeat mesh:heartbeat vexy_ai:heartbeat
```

**Tail alerts**
```bash
redis-cli -h 127.0.0.1 -p 6379 SUBSCRIBE healer:alerts
```

**Latest health snapshots**
```bash
redis-cli -h 127.0.0.1 -p 6379 KEYS health:* | xargs -n1 -I{} \
  redis-cli -h 127.0.0.1 -p 6379 GET {}
```

**Service logs**
```bash
docker compose logs -f --tail=120 healer rss_agg massive mesh vexy_ai sentinel
```

⸻

### Troubleshooting

**Failure**	**Symptom**	**Detection**	**Recovery**
Service crash/hang	Channel stops receiving beats	Healer emits heartbeat_miss	Compose restart: unless-stopped; manual restart if needed
Healer crash	No alerts, no subscriptions	Sentinel emits healer_miss	Compose restarts healer; on return, healer_ok
Network name res failure	Services can’t resolve system-redis	Startup logs show DNS error	All on same network; ensure marketswarm-bus exists
Truth missing	Services exit or default	Logs show missing truth:doc	Re-run Bootstrap

**Gotchas**
* After healer restarts, a **warmup window** prevents false “miss” alerts.
* `PUBSUB` `NUMSUB` counts only exact `SUBSCRIBE` clients (not `PSUBSCRIBE`).
* If you see `TimeoutError` in Sentinel, update to the non‑fatal idle wait (1s socket timeout) version.

⠀
⸻

### Add a New Service
1. Publish a heartbeat to `<svc>:heartbeat` on `system-redis` every *n* seconds.
2. Add to `truth.json`:
```json
{
  "services": {
    "new_svc": {
      "heartbeat": {
        "channel": "new_svc:heartbeat",
        "interval_sec": 10,
        "redis_url": "redis://system-redis:6379"
      }
    }
  }
}
```


3. Add `<svc>:heartbeat` to healer’s `subscribe_to` list in truth.
4. Reseed truth (`bootstrap`) and (re)start healer.
5. Verify `PUBSUB NUMSUB` shows `≥1` on the new heartbeat.

⠀
⸻

### Message Contracts

**Heartbeat**
```json
{ "svc": "<service-id>", "i": <int>, "ts": <epoch-seconds> }
```

**Alerts (on healer:alerts)**
```json
{ "type": "heartbeat_miss", "svc": "<service-id>", "late_sec": 31.2, "timeout_sec": 30.0, "ts": 1762433458 }
{ "type": "heartbeat_ok",   "svc": "<service-id>", "age_sec":  2.7, "ts": 1762433561 }
{ "type": "healer_miss",    "svc": "healer",       "late_sec": 35.0, "timeout_sec": 30.0, "ts": 1762434000 }
{ "type": "healer_ok",      "svc": "healer",       "ts": 1762434100 }
```

.
