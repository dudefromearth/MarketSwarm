# Canonical Tile contract**.

This is written as doctrine + schema, intended to be dropped directly into your sources repo and treated as **non-breaking infrastructure**.

---

# **Heatmap Tile Contract (Frozen)**

**Status:** 🔒 Frozen

**Version:** v1.0

**Scope:** mmaker heatmap pipeline (STAGING → CALC → MODEL)
**Applies to:** SPX, NDX, and future index / ETF / futures symbols

---

## **1. Purpose**

A **Tile** represents the smallest atomic unit of computation in the heatmap system.

It is:

* The convergence point of **contracts**, **geometry**, and **strategy**
* The unit of **dirtiness**
* The unit of **calculation**
* The unit of **promotion**

All higher-level constructs (rows, planes, models) are aggregates of Tiles.

---

## **2. Invariants (Non-Negotiable)**

These rules **must never be violated**:

1. A Tile’s **geometry** is immutable
2. (center strike, width, plane position)
3. A Tile’s **inputs** may change
4. (contracts, quotes, OI, volume)
5. A Tile’s **outputs** are derived
6. (debit, credit, metrics)
7. A Tile is:

   * dirty = true **only** when inputs change
   * dirty = false **only** after successful calculation

8. STAGING may mutate inputs
9. CALC may mutate outputs and state
10. MODEL is read-only

⠀
---

## **3. Tile Geometry (Immutable)**

```
"geometry": {
  "center_strike": 6930,
  "width": 50,
  "expiry": "2025-12-29",
  "dte": 0,
  "symbol": "SPX"
}
```

**Notes** 

* Geometry defines *where* the Tile lives
* Geometry never changes after creation
* Geometry determines required strikes:

  * center - width
  * center
  * center + width

---

## **4. Tile Strategy (Pluggable)**

```
"strategy": {
  "type": "butterfly", 
  "legs": 3,
  "symmetric": true
}
```

**Allowed types (future-safe):** 

* butterfly
* vertical
* single

> All strategies **share the same Tile schema** 

---

## **5. Tile Inputs (Mutable, STAGING-owned)**

### **5.1 Contracts**

```
"contracts": {
  "call": {
    "lower": { /* option contract */ },
    "center": { /* option contract */ },
    "upper": { /* option contract */ }
  },
  "put": {
    "lower": { /* option contract */ },
    "center": { /* option contract */ },
    "upper": { /* option contract */ }
  }
}
```

**Rules** 

* Minimum data: WebSocket schema
* Maximum data: Chain snapshot schema
* Missing legs are allowed (temporarily)

---

### **5.2 Spot Reference**

```
"spot": {
  "price": 6929.94,
  "ts": 1766879693
}
```

Used only for:

* Above/below ATM classification
* UI grouping
* Diagnostics

---

## **6. Tile Outputs (CALC-owned)**

```
"results": {
  "call": {
    "debit": 1.25,
    "credit": -0.85
  },
  "put": {
    "debit": 1.10,
    "credit": -0.75
  },
  "total": {
    "debit": 2.35,
    "credit": -1.60
  }
}
```

**Rules** 

* Outputs must be **fully overwritten** on each calc
* Partial writes are forbidden
* Missing inputs → no outputs written

---

## **7. Tile State (Critical Control Surface)**

```
"state": {
  "dirty": true,
  "eligible": true,
  "reasons": [],
  "last_update_ts": 1766879693013,
  "last_calc_ts": null,
  "last_promoted_ts": null
}
```

### **7.1 Dirty Flag (Canonical)**

* Set to true by:

  * Chain snapshot ingestion
  * WebSocket updates

* Set to false by:

  * Successful CALC only

---

### **7.2 Eligibility**

eligible = false if:

* Any required leg is missing
* Strike outside chain bounds
* Strategy constraints violated

Reasons are **append-only strings**, e.g.:

```
"reasons": [
  "missing_upper_call",
  "missing_lower_put"
]
```

---

## **8. Presentation (External Ownership)**

```
"presentation": {
  "color": null,
  "intensity": null,
  "ui_flags": []
}
```

* Never set by mmaker core
* Owned by UI / analytics layers

---

## **9. Full Tile Skeleton (Reference)**

```
{
  "geometry": { ... },
  "strategy": { ... },
  "contracts": { ... },
  "spot": { ... },
  "results": { ... },
  "state": { ... },
  "presentation": { ... }
}
```

---

## **10. Contract Stability Rules**

* This schema is **append-only**
* No field may be removed
* No semantic meaning may change
* Breaking changes require a new version (Tile v2)

---

## **11. Final Principle**

> **The Tile is sovereign.**

> **Pipelines orbit Tiles.**

> **Models are just frozen Tile graphs.** 

Freeze this.

Everything else becomes easier.