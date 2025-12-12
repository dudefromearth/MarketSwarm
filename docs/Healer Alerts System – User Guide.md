# Healer Alerts System – User Guide

This guide shows you how to run, observe, and operate the **Healer** monitoring stack (Healer + Sentinel) in MarketSwarm.

⸻

### What it does
* **Healer** subscribes to each service’s heartbeat channel and emits alerts to `healer:alerts` when a service stops beating, and recovery notices when it resumes.
* **Sentinel** watches **Healer’s own heartbeat** and emits `healer_miss` / `healer_ok` so the monitor itself is covered.
* Both read wiring from `truth:doc` and publish to Redis.

⠀
⸻

### Prerequisites
* Single shared Docker network marketswarm-bus exists and all services are attached.
* `bootstrap` has seeded `truth.json` to both buses (key `truth:doc`).
* Redis containers are healthy (`system-redis`, `market-redis`).

⠀
⸻

### Quick start
1. **Seed truth (idempotent):**
```bash
docker compose up --build --force-recreate bootstrap
```
⠀
2. **Start/refresh monitor services:**
```bash
docker compose up -d --no-deps --force-recreate healer sentinel
```
⠀
3. **Watch alerts:**
```bash
redis-cli -h 127.0.0.1 -p 6379 SUBSCRIBE healer:alerts
```
⠀

⸻

### Where configuration lives
* **truth.json → services.healer**
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
      "threshold": {"heartbeat_cadence": 30},
      "heartbeat": {"channel":"healer:heartbeat","interval_sec":10}
    }
  }
}
```


* **Environment overrides (compose)**
  * `REDIS_URL/TRUTH_REDIS_URL, TRUTH_REDIS_KEY`
  * `DEFAULT_TIMEOUT_SEC` (fallback if truth has no cadence)
  * `ALERT_CHANNEL` (fallback; normally set by truth)
  * `HB_INTERVAL_SEC` and `HEALER_HEARTBEAT_CHANNEL`
  * `WEBHOOK_URL` / `SMTP_*` (optional notifications)

⠀
⸻

### Expected behavior
* **Heartbeats:** services publish `{"svc":"<name>","i":N,"ts":<epoch>}` to `<svc>:heartbeat`.
* **Warmup:** on Healer start, each service has a **grace window** before a miss can be emitted:
⠀`warmup = min(timeout, max(2×interval, 0.75×timeout))`
* **Miss:** if no beat for timeout seconds → heartbeat_miss on healer:alerts and `health:<svc>` is updated.
* **Recovery:** first beat after a `miss → heartbeat_ok on healer:alerts` and `health:<svc>` updated.
* **Healer coverage:** Sentinel emits `healer_miss when healer:heartbeat is late`, and `healer_ok` on recovery.

⠀
⸻

### Alert message contracts
* **Service miss:**
```json
{"type":"heartbeat_miss","svc":"rss_agg","late_sec":31.2,"timeout_sec":30.0,"ts":1762433458}
```
⠀
* **Service recovery:**
```json
{"type":"heartbeat_ok","svc":"rss_agg","age_sec":2.7,"ts":1762433561}
```
⠀
* **Healer miss / ok (from Sentinel):**
```json
{"type":"healer_miss","svc":"healer","late_sec":35.0,"timeout_sec":30.0,"ts":1762434000}
{"type":"healer_ok","svc":"healer","ts":1762434100}
```
⠀

⸻

### Operating the system

### Check subscribers
```bash
# Healer should be subscribed (≥1) to each heartbeat channel
docker compose exec system-redis redis-cli PUBSUB NUMSUB \
  rss_agg:heartbeat massive:heartbeat mesh:heartbeat vexy_ai:heartbeat
```
> Note: `NUMSUB` does **not** count pattern subscribers (`PSUBSCRIBE`). Healer uses exact `SUBSCRIBE`.

### Tail alerts
```bash
redis-cli -h 127.0.0.1 -p 6379 SUBSCRIBE healer:alerts
```

### Inspect latest health state
```bash
redis-cli -h 127.0.0.1 -p 6379 KEYS health:* | xargs -n1 -I{} \
  redis-cli -h 127.0.0.1 -p 6379 GET {}
```

### Simulate failure & recovery
```bash
# trigger a miss
docker compose stop rss_agg
# ~30s later expect a heartbeat_miss
# trigger recovery
docker compose start rss_agg
# expect heartbeat_ok shortly after first beat
```

### Restart monitor services
```bash
docker compose up -d --no-deps --force-recreate healer sentinel
```


⸻

### Notifications (optional)

Healer supports outgoing notifications via notifier.py.
* **Slack/Discord webhook:**
```yaml
environment:
  WEBHOOK_URL: "https://hooks.slack.com/services/XXX/YYY/ZZZ"
  RATE_LIMIT_SEC: "60"  # throttle repeated miss alerts per service
```

* **Email (SMTP):**
```yaml
environment:
  SMTP_HOST: "smtp.example.com"
  SMTP_PORT: "587"
  SMTP_USER: "apikey"
  SMTP_PASS: "secret"
  SMTP_FROM: "healer@example.com"
  SMTP_TO: "you@example.com,team@example.com"
```


⸻

### Tuning & best practices
* **Cadence vs timeout:** A common rule is timeout ≈ 3× heartbeat interval (e.g., 10s beat → 30s timeout).
* **Warmup avoids false alarms** on Healer restarts. Keep it enabled.
* **Keep channels in truth** so wiring changes don’t require code edits.
* **Use named volumes** for Redis so truth survives container recreates.

⠀
⸻

### Troubleshooting
* **No alerts while Healer was down:** expected. Sentinel covers this with healer_miss.
* **Immediate huge late_sec after Healer restart:** ensure the warmup build is running (monitor has a grace window before first miss).
* **NUMSUB shows 0:** Healer isn’t subscribed. Check `docker compose logs --tail=120 healer` for connection errors.
* **Truth not found:** reseed via Bootstrap.
* **Webhook/email not firing:** verify env vars and outbound egress from container.

⠀
⸻

### Adding a new service
1. In code: publish heartbeat to `<svc>:heartbeat` at your interval.
2. In `truth.json`: add services.`<svc>.heartbeat` (channel, interval, url).
3. In `truth.json`: ensure Healer’s subscribe_to includes `<svc>:heartbeat`.
4. Reseed truth (Bootstrap) and restart Healer.
5. Verify with `PUBSUB NUMSUB ≥ 1` on the new channel.

⠀
⸻

### Runbook (copy/paste)
```bash
# reseed truth safely
docker compose up --build --force-recreate bootstrap

# restart monitors
docker compose up -d --no-deps --force-recreate healer sentinel

# watch alerts
redis-cli -h 127.0.0.1 -p 6379 SUBSCRIBE healer:alerts

# check subs
docker compose exec system-redis redis-cli PUBSUB NUMSUB \
  rss_agg:heartbeat massive:heartbeat mesh:heartbeat vexy_ai:heartbeat

# simulate outage / recovery
docker compose stop rss_agg; sleep 35; docker compose start rss_agg
```


⸻

*Questions or gaps? Ping the Architecture & Design doc for deeper context and contracts.*