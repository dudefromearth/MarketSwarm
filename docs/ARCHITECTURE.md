# MarketSwarm Architecture

This document describes the core architecture patterns that ALL MarketSwarm services MUST follow. These patterns are non-negotiable.

---

## 1. The Truth System

MarketSwarm uses a centralized configuration system called "Truth". All service configuration flows through this system.

### Component JSONs

Each service has a component definition file at:
```
MarketSwarm/truth/components/<service-name>.json
```

A component JSON contains:

```json
{
  "id": "service-name",
  "meta": {
    "name": "Human Readable Name",
    "description": "What this service does"
  },
  "access_points": {
    "subscribe_to": [
      { "bus": "market-redis", "key": "namespace:key", "description": "What this subscription is for" }
    ],
    "publish_to": [
      { "bus": "system-redis", "key": "namespace:key", "description": "What this publishes" }
    ]
  },
  "heartbeat": {
    "interval_sec": 5,
    "ttl_sec": 15
  },
  "dependencies": ["other-service"],
  "env": {
    "SERVICE_PORT": "8080",
    "SERVICE_SETTING": "value"
  },
  "feature_config": {
    "setting1": "value1",
    "nested": {
      "setting2": "value2"
    }
  }
}
```

### Key Sections

| Section | Purpose |
|---------|---------|
| `id` | Unique service identifier |
| `meta` | Human-readable name and description |
| `access_points` | Declares ALL Redis communications (subscribe_to, publish_to) |
| `heartbeat` | Heartbeat configuration |
| `dependencies` | Services this one depends on |
| `env` | Environment variables injected into config |
| Feature configs | Service-specific configuration blocks |

### Access Points Are Sacred

**ALL Redis communications MUST be declared in `access_points`.**

- `subscribe_to`: Keys/channels this service reads from
- `publish_to`: Keys/channels this service writes to

This enables:
- Validation of inter-service communication
- Documentation of data flow
- Sanctioned communications between services

### Redis Buses

MarketSwarm uses multiple Redis instances for different purposes:

| Bus | Port | Purpose |
|-----|------|---------|
| `system-redis` | 6379 | Heartbeats, Truth, system coordination |
| `market-redis` | 6380 | Market data, model outputs |
| `intel-redis` | 6381 | Analytics, intelligence data |

---

## 2. Build → Load → Restart Cycle

Configuration changes follow a strict cycle:

### Step 1: Edit Component JSON
```bash
# Edit the component definition
vim truth/components/copilot.json
```

### Step 2: Build truth.json
```bash
# Validates and assembles all component JSONs into truth.json
./scripts/ms-build.sh
```

This script:
- Validates each component JSON against schema
- Validates access points
- Assembles into a single `truth.json`

### Step 3: Load into Redis
```bash
# Clears Redis buses and loads truth.json
./scripts/ms-truth.sh
```

This script:
- Clears all Redis buses (FLUSHALL)
- Loads truth.json into system-redis

### Step 4: Restart Services
```bash
# Restart affected services
./scripts/ms-<service>.sh fg
```

Services read their configuration from truth.json on startup.

**IMPORTANT**: You cannot just edit code and restart. If configuration changes are needed, they MUST go through the component JSON → build → load → restart cycle.

---

## 3. Service Startup Flow

Every service follows the exact same startup pattern:

```
main.py
   │
   ├── Start heartbeat
   ├── Initialize logger (LogUtil)
   │
   └── SetupBase.load()
          │
          ├── Connect to system-redis
          ├── Read truth.json
          ├── Extract this service's component definition
          ├── Inject env vars into config object
          ├── Load structural config blocks
          │
          └── Return config object
                 │
                 └── main.py passes config + logger to orchestrator
                            │
                            └── orchestrator.run(config, logger)
                                      │
                                      ├── Initialize Redis connections from config.buses
                                      ├── Initialize subsystems using config
                                      └── Run service loop
```

### main.py Pattern

```python
async def main():
    # 1. Bootstrap logger
    logger = LogUtil(SERVICE_NAME)

    # 2. Load configuration from Truth
    setup = SetupBase(SERVICE_NAME, logger)
    config = await setup.load()

    # 3. Configure logger from config
    logger.configure_from_config(config)

    # 4. Start heartbeat
    hb_stop = start_heartbeat(SERVICE_NAME, config, logger)

    # 5. Delegate to orchestrator
    await orchestrator_run(config, logger)
```

### The Config Object

The `config` object returned by `SetupBase.load()` contains:

```python
config = {
    # Env vars from component JSON
    "SERVICE_PORT": "8080",
    "SERVICE_SETTING": "value",
    "API_KEY": "secret-from-truth",

    # Redis bus definitions
    "buses": {
        "system-redis": {"url": "redis://127.0.0.1:6379"},
        "market-redis": {"url": "redis://127.0.0.1:6380"},
        "intel-redis": {"url": "redis://127.0.0.1:6381"}
    },

    # Structural config blocks (feature configs)
    "alerts": {
        "provider": "openai",
        "keys": {
            "events": "copilot:alerts:events",
            "analytics": "copilot:alerts:analytics"
        }
    }
}
```

---

## 4. Configuration Rules (Non-Negotiable)

### Rule 1: No Hardcoded Configuration

**WRONG:**
```python
ANALYTICS_KEY = "copilot:alerts:analytics"
API_URL = "http://localhost:3002"
```

**RIGHT:**
```python
analytics_key = self._config.analytics_key  # From config
api_url = self.config.get("JOURNAL_API_URL")  # From config
```

### Rule 2: No os.environ

**WRONG:**
```python
import os
api_key = os.environ.get("OPENAI_API_KEY")
```

**RIGHT:**
```python
api_key = self.config.get("OPENAI_API_KEY")
```

All environment variables are injected into the config object by SetupBase. Access them through config, not os.environ.

### Rule 3: No Undeclared Redis Access

**WRONG:**
```python
# Publishing to a key not declared in access_points
await redis.publish("random:channel", data)
```

**RIGHT:**
```python
# First declare in component JSON:
# "publish_to": [{"bus": "market-redis", "key": "copilot:alerts:events", ...}]

# Then use the key from config:
await redis.publish(self._config.publish_channel, data)
```

### Rule 4: Redis Keys Come From Config

**WRONG:**
```python
await redis.hset("copilot:alerts:analytics", field, value)
```

**RIGHT:**
```python
await redis.hset(self._config.analytics_key, field, value)
```

---

## 5. Adding New Configuration

When you need to add new configuration:

### Step 1: Add to Component JSON

```json
{
  "env": {
    "NEW_SETTING": "default_value"
  },
  "feature_block": {
    "keys": {
      "new_key": "namespace:new:key"
    }
  }
}
```

### Step 2: Add to Access Points (if Redis)

```json
{
  "access_points": {
    "publish_to": [
      { "bus": "intel-redis", "key": "namespace:new:key", "description": "What it's for" }
    ]
  }
}
```

### Step 3: Add to Config Dataclass (if applicable)

```python
@dataclass
class FeatureConfig:
    new_key: str = "namespace:new:key"
```

### Step 4: Pass From Orchestrator

```python
feature_config = FeatureConfig(
    new_key=keys_config.get("new_key", "namespace:new:key"),
)
```

### Step 5: Build → Load → Restart

```bash
./scripts/ms-build.sh
./scripts/ms-truth.sh  # Select option 4 for full update
./scripts/ms-<service>.sh fg
```

---

## 6. Service Startup Scripts

Each service has a startup script at `scripts/ms-<service>.sh`.

### Required Options

Every startup script MUST support:

| Option | Description |
|--------|-------------|
| `fg` | Run in foreground (see all output) |
| `bg` | Run in background (log to file) |
| Menu option `f` | Run in foreground from interactive menu |

This is required for development and debugging.

### Example Usage

```bash
# Interactive menu
./scripts/ms-copilot.sh

# Direct foreground (skip menu)
./scripts/ms-copilot.sh fg

# Background with logging
./scripts/ms-copilot.sh bg
```

---

## 7. Inter-Service Communication

Services communicate through Redis pub/sub and keys. All communication paths must be declared.

### Publisher (e.g., Journal publishes alert sync)

In `journal.json`:
```json
{
  "access_points": {
    "publish_to": [
      { "bus": "system-redis", "key": "alerts:sync", "description": "Alert sync notifications" }
    ]
  }
}
```

### Subscriber (e.g., Copilot subscribes to alert sync)

In `copilot.json`:
```json
{
  "access_points": {
    "subscribe_to": [
      { "bus": "system-redis", "key": "alerts:sync", "description": "Alert sync from Journal" }
    ]
  }
}
```

### In Code

Publisher:
```python
# Key comes from config, not hardcoded
await self._redis.publish("alerts:sync", json.dumps({"action": "create", ...}))
```

Subscriber:
```python
# Channel comes from config
await pubsub.subscribe(self._config.sync_channel)
```

---

## 8. Summary

1. **Truth is the single source of configuration** - Component JSONs define everything
2. **Build → Load → Restart** - Changes require this cycle
3. **Config object is the only source** - No hardcoding, no os.environ
4. **Access points declare all Redis I/O** - Sanctioned communications only
5. **Startup scripts support foreground mode** - Required for debugging
6. **main.py → SetupBase → orchestrator** - Every service follows this pattern

---

## Quick Reference

| Task | Command |
|------|---------|
| Edit config | `vim truth/components/<service>.json` |
| Build truth | `./scripts/ms-build.sh` |
| Load truth | `./scripts/ms-truth.sh` (option 4) |
| Run foreground | `./scripts/ms-<service>.sh fg` |
| Check Redis | `redis-cli -p <port> GET truth` |

| Bus | Port | Purpose |
|-----|------|---------|
| system-redis | 6379 | System coordination |
| market-redis | 6380 | Market data |
| intel-redis | 6381 | Analytics/intelligence |
