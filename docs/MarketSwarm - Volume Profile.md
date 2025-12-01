# 📘 MarketSwarm Volume Profile

### Architecture & Design Document

### 1. Scope

This document covers the **Volume Profile (VP)** subsystem of the MarketSwarm / Massive service:
* How the VP model is **built** (backfill).
* How it is **stored** (System Redis).
* How it is **published** (Market Redis → SSE).
* How it is **kept current** (live updater worker).
* How other components (React UI, GEX, convexity pipelines) are expected to consume it.

⠀
It **does not** cover chainfeed, convexity, or SSE gateway details beyond what’s needed for VP integration.

⸻

### 2. High-Level Overview

The Volume Profile subsystem provides a **5-year SPY→SPX (and optionally QQQ→NDX)** volume distribution model that serves as **structural context** for:
* GEX charts
* Gamma Door / Convexity Hunter views
* 0DTE/Convexity setups (LVNs/HVNs, VPOC, etc.)

⠀
Key properties:
* Built **once** via a manual backfill process.
* Stored as a **canonical model** in System Redis.
* Updated **incrementally** once per minute during market hours.
* Published as a **small JSON snapshot** via Market Redis → sse:volume-profile.
* React UIs subscribe to SSE and render the latest model.

⠀
⸻

### 3. Components

### 3.1 Backfill CLI: vp-backfill.sh

**File:** vp-backfill.sh
**Role:** Operator tool to build or rebuild the long-horizon Volume Profile model.

Responsibilities:
* Ask the operator for:
  * Ticker: SPY → SPX or QQQ → NDX
  * Publish mode: raw, tv, or both
  * Backfill mode:
    * Last 5 years
    * Full Polygon history (max)
    * Custom date range
    * Wipe + full rebuild
    * Summary only
* Call build_volume_profile.py with the correct args.
* Activate local virtualenv if available.

⠀
This script is **manual, operator-driven** and must be used **before Massive starts**, when volume profile is enabled.

⸻

### 3.2 Model Builder: build_volume_profile.py

**File:** services/massive/utils/build_volume_profile.py
**Role:** Build the 5-year (or requested range) Volume Profile model from historical SPY/QQQ data.

Workflow:
1. **Download historical minute bars** via Polygon:
   * Uses /v2/aggs/ticker/{ticker}/range/1/minute/{start}/{end}
   * Handles pagination with fixed API key propagation.
2. **Convert ETF → synthetic index:**
   * SPY → SPX (×10)
   * QQQ → NDX (×4)
3. **Accumulate two VP variants:**
   * buckets_raw: volume at close price per minute.
   * buckets_tv: volume distributed between low→high using microbins (TradingView-style).
4. **Compute price bounds:** min_price, max_price in synthetic (SPX/NDX) space.
5. **Construct the model object:**

```json
{
  "symbol": "SPY",
  "synthetic_symbol": "SPX",
  "spy_multiplier": 10,
  "bin_size": 1,
  "min_price": ...,
  "max_price": ...,
  "last_updated": "...",
  "ohlc": [...],
  "buckets_raw": { "5820": 1234.5, ... },
  "buckets_tv":  { "5820": 567.8, ... }
}
```


6. **Persist model:**
   * Save full schema to System Redis key: massive:volume_profile.
   * Publish one-time snapshot to Market Redis channel: sse:volume-profile (depending on publish_mode).

⠀
The backfill process is the **only “heavy” operation**. After this, all updates are incremental.

⸻

### 3.3 Canonical Storage: System Redis

**Key:** massive:volume_profile (default; configurable via truth component workflow.volume_profile.system_key if needed).

This key holds the **authoritative Volume Profile model**, including:
* Complete bucket maps (raw + tv).
* Synthetic symbol (SPX/NDX).
* Bounds and metadata (min_price, max_price, last_updated).
* Optional derived metrics (vpoc, hvn, lvn), when updated by the live worker.

⠀
All live updates operate **against this stored model**.

⸻

### 3.4 Publishing Bus: Market Redis → SSE

**Channel:** sse:volume-profile
* **Publisher:** VP live worker (vp_live_worker.py), and optionally initial backfill.
* **Consumer:** SSE gateway → React clients.

⠀
Payload format (recommended):
```json
{
  "symbol": "SPX",
  "volume_profile": {
    "symbol": "SPY",
    "synthetic_symbol": "SPX",
    "spy_multiplier": 10,
    "bin_size": 1,
    "min_price": 5800,
    "max_price": 6100,
    "last_updated": "2025-12-01T15:32:00Z",
    "buckets_raw": { "5850": 123456.0, "5851": 78910.0 },
    "buckets_tv":  { "5850": 23456.0, "5851": 8910.0 },
    "vpoc": 5850,
    "hvn":  [5850, 5860],
    "lvn":  [5830, 5885]
  }
}
```

React UIs subscribe to the SSE stream for this channel and **always receive full snapshots**, not deltas.

⸻

### 3.5 Live Updater Worker: vp_live_worker.py

**File:** `services/massive/workers/vp_live_worker.py`
**Entry:** `run_once(config, log)`
**Called by:** `orchestrator.py`, based on the `volume_profile` schedule.

Responsibilities:
1. Load the current model from System Redis (massive:volume_profile).
2. Fetch the **latest SPY (or QQQ) 1-minute bar** from Polygon:
   * Using the `/v2/aggs/ticker/{SPY}/range/1/minute/latest` endpoint.
3. Convert to synthetic index space:
   * `spx_bin = round(close_price * SCALE) (e.g., 10×)`.
4. **Incrementally update** volume bins:
   * RAW:
⠀
buckets_raw[str(spx_bin)] += volume

	* TV (micro-distributed between low→high):

```python
for i in range(MICROBINS):
    price_micro = low + i*step
    spx_micro   = round(price_micro * SCALE)
    buckets_tv[str(spx_micro)] += vol_per
```

5. Recompute **VP metrics** (cheap):
   * VPOC: price with max volume.
   * HVN: nodes with volume ≥ 1.5× average.
   * LVN: nodes with volume ≤ 0.5× average.
6. Update the model:

```python
model["buckets_raw"]  = buckets_raw
model["buckets_tv"]   = buckets_tv
model["vpoc"]         = vpoc
model["hvn"]          = hvn
model["lvn"]          = lvn
model["last_updated"] = now_iso
```

7. Save the updated model back to System Redis (`massive:volume_profile`).
8. Publish a **unified snapshot** to `sse:volume-profile`.

⠀
The worker is **stateless between calls** and only performs one atomic update per invocation. All timing is controlled by the orchestrator.

⸻

### 3.6 Orchestrator Integration

**File:** `intel/orchestrator.py` (as provided)

Relevant snippet (after modification):
```python
from .vp_live_worker import run_once as vp_live_once
```

Inside the main loop:

```python
# ------------------ VOLUME PROFILE WORKER --------------------
# Updated: call new vp_live_worker
if enable_volume_profile and (now - last_volume >= sec_volume_profile):
    try:
        log("volume", "📊", "Running vp_live_once()…")
        vp_live_once(config, log)
        last_volume = now
    except Exception as e:
        log("volume", "❌", f"Error: {e}")
        traceback.print_exc()
```

The schedule and toggle come from Massive’s truth via setup.py:
* schedules["volume_profile"] → seconds between updates (default 60).
* schedules["enable_volume_profile"] → feature toggle.

⠀
⸻

### 3.7 Startup Guard: setup.py

**File:** `setup.py`

On service startup, setup_environment():
* Loads `truth` and the massive component definition.
* Extracts schedules (including enable_volume_profile).
* **If enable_volume_profile is true**, it asserts that the base model exists in System Redis.

⠀
Key logic:
```python
vp_enabled = schedules.get("enable_volume_profile", False)
if vp_enabled:
    wf = (comp.get("workflow") or {})
    vp_cfg = (wf.get("volume_profile") or {})
    vp_system_key = vp_cfg.get("system_key", "massive:volume_profile")

    vp_raw = r_system.get(vp_system_key)
    if not vp_raw:
        raise RuntimeError(
            f"Volume Profile model missing in system-redis key '{vp_system_key}'. "
            f"Massive is configured with volume_profile enabled, so startup is blocked.\n"
            f"→ Run the VP backfill step (e.g. vp-backfill.sh / build_volume_profile.py) "
            f"to create the 5-year SPY→SPX Volume Profile model, then restart Massive."
        )
```

This guarantees:
* Massive **won’t start** with VP enabled if the model is missing.
* Operator gets a clear explanation and remediation steps.

⠀
⸻

### 3.8 Massive Truth Configuration (truth.json)

Within the "massive" component:

```json
"access_points": {
  "publish_to": [
    { "bus": "market-redis", "key": "sse:chain-full" },
    { "bus": "market-redis", "key": "sse:chain-feed" },
    { "bus": "market-redis", "key": "sse:volume-profile" },
    { "bus": "market-redis", "key": "sse:timeseries" },
    { "bus": "market-redis", "key": "sse:convexity-feed" },
    { "bus": "system-redis", "key": "massive:heartbeat" }
  ],
  "subscribe_to": []
},
"workflow": {
  "symbol": "SPX",
  "spy_symbol": "SPY",
  "api_key_env": "POLYGON_API_KEY",
  "volume_profile": {
    "enabled": true,
    "spy_to_spx_scale": 10.0,
    "bin_size_spy": 0.01,
    "window_days": 365,
    "dynamic_price_span": true
  },
  "publish_chainfeed": true,
  "publish_volume_profile": true,
  "publish_timeseries": true,
  "publish_convexity": false
},
"schedules": {
  "volume_profile": 60,
  "enable_volume_profile": true
}
```

This defines:
* VP is enabled.
* Scale from SPY to SPX.
* Market Redis publish channel: `sse:volume-profile`.
* The orchestrator cadence for VP updates.

⠀
⸻

### 4. Data Model Summary

### 4.1 System Redis: massive:volume_profile
* **Type:** String (JSON)
* **Contains:**
  * `symbol: "SPY" / "QQQ"`
  * `synthetic_symbol: "SPX" / "NDX"`
  * `spy_multiplier: 10 / 4`
  * `bin_size: 1`
  * `min_price, max_price`
  * `last_updated: ISO timestamp`
  * `buckets_raw: { str(int_price): float_volume }`
  * `buckets_tv: { str(int_price): float_volume }`
  * `vpoc: int price (synthetic)`
  * `hvn: [int_price, ...]`
  * `lvn: [int_price, ...]`

⠀
### 4.2 Market Redis: sse:volume-profile
* **Type:** Pub/Sub channel
* **Payload:** full snapshot, as shown in §3.4.

⠀
⸻

### 5. Integration with GEX / Convexity

While GEX / Convexity aren’t fully detailed here, the Volume Profile is designed to:
* Provide **LVN edges** and **HVN ranges** for:
  * Gamma Door detection.
  * Convexity Stack placement.
  * 0DTE butterfly targeting.
* Serve as a **background, structural layer** for GEX charts in the UI.

⠀
The VP model is **not** microsecond-accurate; it’s a **minute-resolution structure**. It is used as context, not a trade signal by itself.

⸻

# 📎 Addendum: Operational Guide

This is a practical runbook for operating the Volume Profile subsystem.

### A. Prerequisites
* Working Redis:
  * System Redis (`SYSTEM_REDIS_URL`).
  * Market Redis (`MARKET_REDIS_URL`).
* Valid Polygon API key (`POLYGON_API_KEY`).
* Massive service installed with:
  * `vp-backfill.sh`
  * `build_volume_profile.py`
  * `vp_live_worker.py`
  * `Updated setup.py, main.py, and orchestrator.py.`

⠀
⸻

### B. First-Time Setup (Cold Start)
1. **Ensure Redis is running.**
2. **Run VP Backfill (5 years for SPX):**

⠀From repo root:
`./vp-backfill.sh`

	* Choose ticker: 1) SPY → SPX
	* Choose publish mode: 1) raw or 3) both
	* Choose action: 1) Backfill last 5 years

⠀Watch for output:
	* “Downloading SPY …”
	* “Saved full schema to `system-redis →` `massive:volume_profile`”
	* Optional: “Published RAW to `market-redis →` `sse:volume-profile`”

⠀
3. **Verify the model exists in System Redis:**
⠀
`redis-cli -u redis://127.0.0.1:6379 GET massive:volume_profile | jq .`

You should see the JSON structure with buckets_raw / buckets_tv.

4. **Start Massive:**

`python3 main.py`

On success, you should see:
	* A log from setup not complaining about the VP model.
	* Orchestrator starting.
	* Periodic `vp_live_once()` logs: `VP updated + published (bin=..., vol=...).`

⸻

### C. Restart Behavior
* **If VP is enabled** (enable_volume_profile: true in truth):
  * On restart, setup_environment() will check for massive:volume_profile.
  * If missing → Massive will **refuse to start**, with a message:

⠀Volume Profile model missing in system-redis key ‘massive:volume_profile’. Massive is configured with volume_profile enabled, so startup is blocked. → Run the VP backfill step …
* **If VP is disabled** (enable_volume_profile: false):
  * Massive starts without checking for the VP model.
  * VP live updates will not run.

**Best practice:**
* Do **not** restart Massive during market hours on a cold system without VP.
* If you must restart:
  * Ensure `massive:volume_profile` exists first (via backfill or persisted state).

⸻

### D. Manual Health Checks

### 1. Check that the VP model exists

`redis-cli -u "$SYSTEM_REDIS_URL" GET massive:volume_profile | jq .`

* If null → it doesn’t exist.
* If valid JSON with buckets_raw → model is present.

⠀
### 2. Check that it’s updating

Look at last_updated field:

`redis-cli -u "$SYSTEM_REDIS_URL" GET massive:volume_profile | jq .last_updated`

* It should advance roughly every volume_profile seconds (e.g., ~60s) during market hours.

⠀
### 3. Check SSE stream (debug)

Use a simple SSE or pub/sub subscriber:

`redis-cli -u "$MARKET_REDIS_URL" SUBSCRIBE sse:volume-profile`

You should see JSON messages containing volume_profile.

⸻

### E. Rebuilding the Model

You may want to rebuild the entire model when:
* Polygon data changes / corrections applied.
* You extend the time window (e.g., 5 years → full history).
* You change multipliers or binning logic.

⠀
Steps:
1. **Stop Massive** (if running).
2. **Run VP backfill with wipe:**

`./vp-backfill.sh`

Option: 4) Delete + FULL rebuild (max history)

3. Confirm massive:volume_profile is present and valid.
4. **Restart Massive.**

⠀
⸻

### F. Common Failure Modes & Remedies

### 1. Massive fails to start with VP enabled

**Symptom:**
* main.py logs:
> ⠀Setup failed — Volume Profile model missing in system-redis key ‘massive:volume_profile’ …

**Fix:**
1. Run `./vp-backfill.sh`.
2. Confirm model exists in Redis.
3. Restart Massive.

⠀
⸻

### 2. VP model stops updating

**Symptom:**
* last_updated timestamp stops advancing.
* Logs show repeated VP worker errors.

⠀
**Possible causes:**
* Polygon API key invalid / rate-limited.
* Network issue.
* Redis error.

⠀
**Fix:**
1. Check logs around vp_live_once.
2. Validate `POLYGON_API_KEY`.
3. Check the network and Redis.
4. Restart Massive once the underlying issues are resolved.

⠀
⸻

### 3. UI shows flat or missing VP

**Symptom:**
* The React GEX / VP view has no or an outdated volume profile.

⠀
**Checklist:**
1. Is Massive running?
2. Does massive:volume_profile exist and have recent last_updated?
3. Is the SSE gateway connected to sse:volume-profile?
4. Is the React client subscribed to the correct SSE URL?

