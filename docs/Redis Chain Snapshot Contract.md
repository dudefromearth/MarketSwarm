# # MarketSwarm Redis Chain Snapshot Contract  
**Version:** v1.0  
**Status:** Canonical  
**Scope:** `massive → downstream consumers (mmaker, UI, replay tools)`

---

## 1. Purpose

The **chain snapshot** represents a **stateful, point-in-time options surface** for a given:

- **Underlying**
- **Expiration (DTE)**
- **Strike range (≈ ±2σ)**

**It is:**

- **Not a stream**
- **Not incremental**
- **Authoritative state**

**Used to:**

- Bootstrap models
- Anchor heatmaps
- Render off-hours UI
- Support replay / historical modes
- Serve as the static backdrop for WebSocket-driven deltas

---

## 2. Naming Conventions (LOCKED)

### 2.1 Snapshot Payload Key

```text
massive:chain:snapshot:{UNDERLYING}:{EXPIRY}:{TS_MS}
```

**Example**
`massive:chain:snapshot:SPX:2026-01-02:1766762051149`

**Properties** 

* Immutable
* JSON blob
* TTL applied (default: 60s)
* Multiple snapshots may exist concurrently

---

### **2.2 Latest Pointer Key (CANONICAL ENTRY POINT)**
`massive:chain:latest:{UNDERLYING}:{EXPIRY}`

**Value**
`→ snapshot key (string)`

**Example**
`massive:chain:latest:SPX:2026-01-02`
  `= "massive:chain:snapshot:SPX:2026-01-02:1766762051149"`

**Properties** 

* Always points to the most recent snapshot
* TTL mirrors snapshot TTL
* **All consumers resolve snapshots through this key**

> **Consumers MUST NOT scan snapshot keys directly.** 

---

## **3. Snapshot JSON Schema (STABLE)**
```json
{
  "ts": 1766762051.149389,
  "underlying": "SPX",
  "expiration": "2026-01-02",
  "atm": 6930,
  "range_points": 124,
  "contracts": [ ... ]
}
```

### **Field Semantics**
| `**Field**`    | `**Type**`              | `**Description**`          |
|----------------|-------------------------|----------------------------|
| `ts`           | `float (epoch seconds)` | `Snapshot creation time`   |
| `underlying`   | `string`                | `Symbol (SPX, NDX, etc.)`  |
| `expiration`   | `string (YYYY-MM-DD)`   | `Option expiration`        |
| `atm`          | `int`                   | `ATM strike at snapshot`   |
| `range_points` | `int`                   | `Strike distance from ATM` |
| `contracts`    | `array`                 | `Full option chain slice`  |

---

## **4. Contract Scope & Guarantees**

### **4.1 What a Snapshot Guarantees**

* Full call + put surface
* Consistent strike grid
* Deterministic tile generation
* Safe UI rendering **without WebSocket**
* Replayable state

---

### **4.2 What a Snapshot Does NOT Do**

* Does **not** stream
* Does **not** update incrementally
* Does **not** imply the market is open
* Does **not** include WS-driven Greeks deltas

---

## **5. Expiration (DTE) Selection Rule**

**Canonical Rule** 

> Massive publishes snapshots for the **next N tradable expirations**,

> not calendar DTEs.

### **Configuration**

* N = MASSIVE_CHAIN_NUM_EXPIRATIONS (default: 5–6)
* Expirations determined by Massive option-chain availability
* Weekends and holidays handled implicitly by the API

**Result** 

* Stable DTE depth
* Deterministic heatmap depth
* No custom calendar math required

---

## **6. Relationship to WebSocket Stream**
| **Component**         | **Role**             |
|-----------------------|----------------------|
| massive:chain:        | Static state         |
| massive:ws:stream     | Incremental deltas   |
| mmaker:chain:staging  | Merged working state |
| massive:model:heatmap | Renderable model     |

**Mental Model**
```pcode
Snapshot = backdrop
WS stream = brush strokes
mmaker = compositor
UI = renderer
```
---

## **7. Consumer Responsibilities**

### **Consumers MUST**

* Resolve snapshots via massive:chain:latest:*
* Treat snapshots as **replaceable state**
* Detect staleness via ts
* Support off-hours rendering

### **Consumers MUST NOT**

* Assume snapshots arrive continuously
* Depend on WebSocket availability
* Scan raw snapshot keys

---

## **8. Replay & Mock Compatibility (DESIGNED IN)**

* mock_massive publishes **identically**
* Replay services reuse the same contract
* Historical namespaces may be layered later:

`massive:replay:chain:snapshot:...`

No consumer logic changes required.

---

## **9. Operational Signals (Future)**

Snapshots enable higher-order monitoring:

* Snapshot age > threshold → warning
* Missing DTE depth → partial degradation
* WS active + snapshot stale → degraded state

These signals belong in:

* Heartbeat enrichment
* Healer intelligence
* vexy_ai diagnostics

---

## **10. Final Principle**

> **Snapshots are state, not events.** 

Streams move time forward.

Snapshots define **where we are**.