# # Massive Chain Analytics Guide  
**Canonical Observability Contract for Options Chain Ingestion**

---

## Purpose

The **Massive Chain Analytics** subsystem exists to establish **ground truth, operational authority, and auditability** over options chain ingestion.

It answers four non-negotiable questions:

1. **Is the system fetching chains reliably?**
2. **How fast is the provider responding?**
3. **How complete and fresh is the data?**
4. **Is the chain structurally usable for downstream models?**

These analytics are **not derived estimates**.  
They are **first-order facts**, written at ingestion time by the ChainWorker itself.

---

## Redis Contract Overview

All analytics live under a single canonical base key:
massive:chain:analytics

This key is supported by a set of **time-series ZSETs** and **structured HASHes**.

No analytics are inferred downstream.  
If a value exists here, it was **measured at snapshot time**.

---

## 1. Core Aggregate Metrics (HASH)

### Key
massive:chain:analytics

### Fields

| Field | Type | Meaning |
|-----|-----|--------|
| `total_snapshots` | integer | Total number of chain snapshots successfully published |
| `total_contracts` | integer | Total contracts ingested across all snapshots |
| `total_fetch_latency_ms` | float | Sum of fetch latencies (ms) |
| `last_snapshot_ts` | float (epoch) | Timestamp of most recent snapshot |
| `publish_success` | integer | Count of successfully published snapshots |
| `publish_failures` | integer | Count of failed publish attempts |
| `sla_violations` | integer | Count of snapshots exceeding freshness SLA |

### Interpretation

- **Average latency** = `total_fetch_latency_ms / total_snapshots`
- **Average contracts per snapshot** = `total_contracts / total_snapshots`
- `sla_violations > 0` indicates structural data risk

This hash represents **global system health** over time.

---

## 2. Latency Distribution (ZSET)

### Key
massive:chain:analytics:fetch_latency

### Structure
- **Score**: snapshot timestamp
- **Value**: fetch latency in milliseconds

### Interpretation

- Use for **min / max / percentile** latency analysis
- Detect provider degradation
- Identify congestion or throttling behavior

This is your **provider performance truth source**.

---

## 3. Snapshot Freshness / Staleness (ZSET)

### Key
massive:chain:analytics:staleness

### Structure
- **Score**: snapshot timestamp
- **Value**: staleness in seconds  
  (`now_epoch - avg_contract_timestamp`)

### Interpretation

- `≈ 0s` → contracts are live and coherent
- Increasing values → stale quotes, delayed feeds
- Used to enforce **freshness SLA**

This measures **temporal integrity**, not speed.

---

## 4. Strike Coverage Range (ZSET)

### Key
massive:chain:analytics:strike_range

### Structure
- **Score**: snapshot timestamp
- **Value**: max_strike − min_strike

### Interpretation

- Larger ranges indicate broader surface coverage
- Sudden drops may indicate:
  - missing strikes
  - provider truncation
  - upstream filtering errors

This reflects **structural completeness** of the chain.

---

## 5. Contract Count Distribution (ZSET)

### Key
massive:chain:analytics:contract_count

### Structure
- **Score**: snapshot timestamp
- **Value**: number of contracts in snapshot

### Interpretation

- Tracks **snapshot density**
- Useful for detecting:
  - partial chains
  - silent API failures
  - holiday / expiry edge cases

A sharp fall here is almost always actionable.

---

## 6. Contract Density (ZSET)

### Key
massive:chain:analytics:contract_density

### Definition
contract_density = contract_count / strike_range

### Interpretation

- Normalizes size by coverage
- Enables comparison across underlyings (SPX vs NDX)
- Detects **thin or fragmented chains**

This is a **quality-normalized signal**, not a raw size metric.

---

## 7. Symbol Coverage (HASH)

### Key
massive:chain:analytics:symbol_coverage

### Structure
- Field: underlying symbol (e.g. `SPX`, `NDX`)
- Value: number of snapshots captured

### Interpretation

- Confirms ingestion parity across symbols
- Detects silent symbol dropouts
- Enables fairness and completeness audits

If a symbol stops incrementing, ingestion is broken.

---

## 8. Fetch Health Classification (HASH)

### Key
massive:chain:analytics:fetch_health

### Fields

| Field | Meaning |
|-----|--------|
| `ok` | Healthy snapshots |
| `partial` | Snapshot with abnormally low contract count |
| `slow` | Fetch exceeded acceptable latency |
| `empty` | No contracts returned |

### Interpretation

This is a **categorical health ledger**, not a metric.

It allows:
- alerting
- dashboards
- post-mortem classification

Without inspecting raw logs.

---

## 9. How to Use These Metrics

### Operational Monitoring
- Track latency and staleness continuously
- Alert on rising `sla_violations`
- Alert on `empty` or `partial` fetches

### Model Trust Gating
- Downstream models can:
  - reject stale snapshots
  - down-weight thin chains
  - require minimum density thresholds

### Provider Accountability
- Latency distributions establish provider behavior
- Enables evidence-based escalation

### Research & Calibration
- Strike range and density explain model instability
- Snapshot size variance explains regime shifts

---

## Design Principles (Why This Works)

- **Measured, not inferred**
- **Written once, read everywhere**
- **Redis-native**
- **Time-indexed**
- **Composable**

These analytics are the **authority layer** of the Massive system.  
Everything else is interpretation.

---

## Final Note

If chain analytics stop updating:

> **Assume the system is blind.**

Chain analytics are not optional telemetry.  
They are the **foundation of trust** for every downstream model.

---
