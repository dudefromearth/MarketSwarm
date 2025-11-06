# # MarketSwarm – Architecture & Design

**Position-first summary**: Every service positions itself from a single source of truth and a shared internal network. Heartbeats create a cheap, ubiquitous signal. Healer converts missed beats into alerts; Sentinel covers the healer itself. No hero boxes.

⸻

### System Overview
* **Core buses (state + pub/sub):**
  * **system-redis** (container port 6379, host-mapped 127.0.0.1:6379)
  * **market-redis** (container port 6379, host-mapped 127.0.0.1:6380)
* **Bootstrap (one-shot):** seeds truth.json into both buses and exits.
* **Application services:** rss_agg, massive, mesh, vexy_ai, etc. Each loads configuration from the **truth** and publishes a **heartbeat**.
* **Healer (monitor):** subscribes to all configured heartbeat channels; publishes **alerts**.
* **Sentinel (watchdog for Healer):** monitors healer:heartbeat and alerts if the monitor goes dark.
* **Single shared network:** marketswarm-bus (external). All containers join it to guarantee name-based resolution and internal reachability.
⠀
### Key Decisions
1. **Single shared network** for zero-conf service discovery (system-redis, market-redis, etc.).
2. **Source of truth** is a Redis key (by default truth:doc) loaded by Bootstrap; no file coupling at runtime.
3. **Heartbeat as a primitive**: cheap pub/sub messages, easy to verify, easy to extend.
4. **Healer warmup window** avoids false negatives on restarts.
5. **Sentinel** provides independent coverage for Healer itself.

⠀
⸻

### Runtime Topology
```mermaid
flowchart LR
  subgraph Internal Network: marketswarm-bus
    A((system-redis:6379))
    B((market-redis:6379))
    BS([bootstrap (one-shot)])
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
  class A,B bus
```


⸻

### Startup & Dependency Model
1. **Bring up buses** (compose ensures healthchecks are green):
   * system-redis healthy on 6379.
   * market-redis healthy on 6379 (host-mapped to 6380).
2. **Bootstrap** waits for both, loads truth.json into truth:doc on both Redis instances, validates, exits **0**.
3. **Services** start only **after** Bootstrap completed successfully.

⠀
Compose encodes this with:
* depends_on: {system-redis: condition: service_healthy, market-redis: condition: service_healthy} for bootstrap.
* depends_on: {bootstrap: condition: service_completed_successfully} for services.

⠀
⸻

### Truth Document (shape)

**Key**: truth:doc (JSON) on both buses.

Essential fields per service (example for rss_agg):
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


**Healer** section defines subscriptions and alert endpoint:
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

> **Contract**: Services publish to their own svc:heartbeat. Healer publishes alerts to healer:alerts. Sentinel watches healer:heartbeat.

⸻

### Heartbeats & Alerts
* **Heartbeat payload** (typical): { "svc": "rss_agg", "i": N, "ts": epoch }
* **Alert events** on healer:alerts:
  * {"type":"heartbeat_miss","svc":"<name>","late_sec":X,"timeout_sec":T,"ts":...}
  * {"type":"heartbeat_ok","svc":"<name>","age_sec":Y,"ts":...}
  * Sentinel adds: {"type":"healer_miss"...} / {"type":"healer_ok"...}
* **Warmup (Healer)**: on healer start, each service has a grace period:

⠀warmup = min(timeout, max(2×interval, 0.75×timeout))
Alerts only begin after warmup if no beat has been seen yet.
* **State KV for dashboards**: Healer writes health:<svc> to Redis with the latest alert/ok object.

⠀
⸻

### Bootstrap Service
* **Image**: redis:7-alpine (uses redis-cli).
* **Behavior**:
  1. Wait for both buses to respond to PING.
  2. SET truth:doc <truth.json> on each.
  3. Verify EXISTS truth:doc == 1 on each; exit 0.
* **Idempotent** and re-runnable.

⠀
⸻

### Networking
* **Network**: marketswarm-bus (external, bridge). All services attach.
* **Service discovery**: container DNS names (system-redis, market-redis).
* **Internet access**: services that need egress DNS/HTTPS (e.g., massive, rss_agg, mesh) optionally set explicit dns: [8.8.8.8, 8.8.4.4].

⠀
⸻

### Service Responsibilities

### rss_agg
* Loads truth, reads endpoints.
* Heartbeat to rss_agg:heartbeat at configured interval.
* (Future) Publishes aggregated RSS items to a stream/queue referenced by truth.

### massive
* Connectivity probes (DNS/TCP/HTTPS) and Polygon probes (configurable).
* Publishes heartbeat to its configured channel.

### mesh
* Coordinator; publishes heartbeat.

### vexy_ai
* Consumer/worker; publishes heartbeat.

### healer (monitor)
* Subscribes to all heartbeat channels defined in truth.
* Warmup logic prevents startup false alarms.
* Emits heartbeat_miss and heartbeat_ok to healer:alerts.
* Writes health:<svc> KV snapshots.
* Optional outbound notifications (webhook/email) via notifier.py.

### sentinel (healer watchdog)
* Subscribes to healer:heartbeat.
* Publishes healer_miss after timeout; healer_ok on recovery.

⠀
⸻

### Failure Modes & Recovery

| **Failure** | **Symptom** | **Detection** | **Recovery** |
|:-:|:-:|:-:|:-:|
| Service crash/hang | Channel stops receiving beats | Healer emits heartbeat_miss | Compose restart: unless-stopped; manual restart if needed |
| Healer crash | No alerts, no subscriptions | Sentinel emits healer_miss | Compose restarts healer; on return, healer_ok |
| Network name res failure | Services can’t resolve system-redis | Startup logs show DNS error | All on same network; ensure marketswarm-bus exists |
| Truth missing | Services exit or default | Logs show missing truth:doc | Re-run Bootstrap |


⸻

### Observability & Ops

### Quick Status
* Subscribers per heartbeat channel:
```bash
docker compose exec system-redis redis-cli PUBSUB NUMSUB \
  rss_agg:heartbeat massive:heartbeat mesh:heartbeat vexy_ai:heartbeat
```

* Tail alerts:
```bash
redis-cli -h 127.0.0.1 -p 6379 SUBSCRIBE healer:alerts
```

* Latest health KV:
```bash
redis-cli -h 127.0.0.1 -p 6379 KEYS health:* | xargs -n1 -I{} redis-cli -h 127.0.0.1 -p 6379 GET {}
```
⠀

### Runbooks
* **Fresh init**:
```bash
docker compose down
docker network create marketswarm-bus || true
docker compose up --build bootstrap
docker compose up -d rss_agg massive mesh vexy_ai healer sentinel
```
⠀
* **Force reseed truth**:
```bash
docker compose up --build --force-recreate bootstrap
```
⠀
* **Simulate failure**:
```bash
docker compose stop rss_agg   # expect heartbeat_miss ~30s later
docker compose start rss_agg  # expect heartbeat_ok shortly after first beat
```
⠀

⸻

### Configuration (env knobs)

Common:
* REDIS_URL, TRUTH_REDIS_URL, TRUTH_REDIS_KEY (default truth:doc).
* LOG_LEVEL (INFO/DEBUG).

Healer:
* DEFAULT_TIMEOUT_SEC (fallback when truth lacks heartbeat_cadence).
* ALERT_CHANNEL (fallback; truth usually sets this to healer:alerts).
* HB_INTERVAL_SEC, HEALER_HEARTBEAT_CHANNEL (for healer’s own beat).
* WEBHOOK_URL (Slack/Discord), SMTP_* (email), RATE_LIMIT_SEC (miss spam control).

Sentinel:
* SENTINEL_TIMEOUT_SEC (default ~3× healer interval).

Massive / egressing services:
* NET_* toggles/timeouts; Polygon keys for probes.

⠀
⸻

### Security & Data
* Redis volumes are **named volumes**: system_redis_data, market_redis_data.
* Truth is loaded to both buses for resilience; services generally read system-redis.
* No credentials in truth; API keys supplied as environment variables to the specific services that need them.

⠀
⸻

### Extend the System (add a new service)
1. Add the service to the repo (Dockerfile or bind-mount during dev).
2. Extend truth.json with:
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

3. Re-seed with Bootstrap.
4. In compose, set depends_on: bootstrap: service_completed_successfully, attach to marketswarm-bus.
5. Verify heartbeat count (PUBSUB NUMSUB) ≥ 1 (healer subscribed).

⠀
⸻

### Appendix A – Message Contracts
* **Heartbeat**
```json
{ "svc": "<service-id>", "i": <int>, "ts": <epoch-seconds> }
```

* **Alerts** (healer:alerts)
```json
{ "type": "heartbeat_miss", "svc": "<service-id>", "late_sec": 31.2, "timeout_sec": 30.0, "ts": 1762433458 }
{ "type": "heartbeat_ok",   "svc": "<service-id>", "age_sec":  2.7, "ts": 1762433561 }
{ "type": "healer_miss",    "svc": "healer",       "late_sec": 35.0, "timeout_sec": 30.0, "ts": 1762434000 }
{ "type": "healer_ok",      "svc": "healer",       "ts": 1762434100 }
```

⸻

### Appendix B – Ports & Names
* **system-redis**: container 6379, host 127.0.0.1:6379.
* **market-redis**: container 6379, host 127.0.0.1:6380.
* **DNS** inside network: system-redis, market-redis.

⠀
⸻

### Appendix C – Known Good Checks
* `docker compose config` (validates interpolation & structure)
* `docker compose ps` (all services Up)
* `docker compose logs --tail=100 healer` (should show listening ... and monitoring ...)
* `redis-cli SUBSCRIBE healer:alerts` (should show events when you stop/start services)

⠀
⸻

*This document is the high-level architecture and operational guide. For implementation details, see each service folder and the current* *docker-compose.yml**.*