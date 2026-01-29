# # **Heatmap Topology & Tile Placement Contract**

**Status:** 🔒 Frozen

**Applies to:** mmaker Heatmap Pipeline

**Stages:** STAGING, CALC, MODEL

---

## **1. Core Principle**

A **Tile cannot exist independently**.

A Tile’s meaning, geometry, and validity are **entirely defined by the heatmap topology** it belongs to.

> **The heatmap defines the Tile — never the reverse.** 

---

## **2. Heatmap Is a 3-Dimensional Structure**

Every heatmap is defined over **exactly three orthogonal dimensions**:

|  **Axis**  |  **Dimension**  |  **Meaning**  |  **Authority**  | 
|---|---|---|---|
|  **X**  |  Strike  |  Center strike rows  |  Massive chain snapshot  | 
|  **Y**  |  Width  |  Strategy geometry  |  Truth config  | 
|  **Z**  |  Time  |  Expiry / DTE planes  |  Massive + Truth  | 
There are **no other dimensions** inside mmaker.

---

## **3. Dimension Definitions**

### **3.1 Z-Axis — Expiry / DTE Planes**

Each heatmap consists of **discrete expiry planes**, one per DTE.

Example:

```
DTE 0 → 2025-12-29
DTE 1 → 2025-12-30
DTE 2 → 2025-12-31
DTE 3 → 2026-01-02
DTE 4 → 2026-01-05
```

**Rules** 

* Number of planes = heatmap.dte_depth
* Expiries are discovered from Massive
* Missing calendar days (e.g. Jan 1) are expected
* Planes are immutable after creation
* Plane order is strictly DTE-ordered

---

### **3.2 X-Axis — Strike Rows**

Strikes define the horizontal geometry of the heatmap.

Example:

```
6815, 6830, 6845, …, 7045
```

**Rules** 

* Strike set is authoritative from Massive
* Strike step is inferred, not assumed
* Strike spacing may vary
* No synthetic strikes are ever created
* Strike rows are immutable per snapshot

---

### **3.3 Y-Axis — Width Columns**

Widths define **strategy geometry**, not market geometry.

Example Truth configuration:

```
"widths": {
  "SPX": [15, 20, 25, 30, 35, 40, 45, 50],
  "NDX": [25, 50, 75, 100, 125, 150, 175, 200]
}
```

**Rules** 

* Widths are symbol-specific
* Widths are static at runtime
* Widths are not inferred or modified
* Widths apply uniformly across all strikes in a plane

---

## **4. Tile Placement (Deterministic)**

A **Tile exists only at the intersection** of all three dimensions:

```
Tile = (Expiry Plane, Center Strike, Width)
```

Conceptually:

```
Z (Expiry / DTE)
│
│   ┌──────── Width 15
│   │   ┌──── Width 20
│   │   │   ┌ Width 25
│   ▼   ▼   ▼
┌────────────────────────────
│ Strike 6815  [Tile][Tile]
│ Strike 6830  [Tile][Tile]
│ Strike 6845  [Tile][Tile]
│ Strike 6860  [Tile][Tile]
└────────────────────────────
```

---

## **5. Tile Geometry (Derived, Not Stored)**

A Tile’s option geometry is **fully determined** by its coordinates.

Example:

```
"geometry": {
  "symbol": "SPX",
  "expiry": "2025-12-29",
  "dte": 0,
  "center_strike": 6930,
  "width": 50,
  "required_strikes": {
    "lower": 6880,
    "center": 6930,
    "upper": 6980
  }
}
```

**Rules** 

* required_strikes are deterministic
* Geometry never mutates
* If any required strike is missing, the Tile is ineligible for calculation
* Ineligible Tiles are excluded from MODEL publication

---

## **6. Tile Contract (Frozen)**

Every Tile adheres to the following **minimum contract**:

```
{
  "type": "butterfly | vertical | single",
  "width": 50,

  "call": {
    "min": { /* WS schema */ },
    "max": { /* chain snapshot schema */ }
  },

  "put": {
    "min": { /* WS schema */ },
    "max": { /* chain snapshot schema */ }
  },

  "pricing": {
    "debit": null,
    "credit": null
  },

  "state": {
    "dirty": true
  }
}
```

**Notes** 

* min = minimum viable WS contract data
* max = full chain snapshot contract
* Pricing is written only in CALC
* Color and rendering metadata are external concerns

---

## **7. Heatmap Structural Model**

A heatmap is structured as:

```
Heatmap
└── Symbol
    └── Expiry Plane
        └── Strike Row
            └── Width Column
                └── Tile
```

Or concretely:

```
{
  "symbol": "SPX",
  "planes": {
    "2025-12-29": {
      "dte": 0,
      "tiles": [ /* Tile objects */ ]
    }
  }
}
```

---

## **8. Pipeline Implications**

Because of this topology:

1. **STAGING**

   * Accepts chain snapshots and WS diffs
   * Mutates Tiles
   * Flips dirty flags only

2. **CALC**

   * Operates on a frozen copy
   * Performs topological calculations
   * Ignores missing-geometry Tiles

3. **MODEL**

   * Read-only projection
   * Contains only fully computed Tiles
   * Safe for UI and downstream systems

⠀
---

## **9. Final Law**

> **A Tile does not define the heatmap.**

> **The heatmap defines the Tile.** 

This guarantees deterministic geometry, antifragile updates, and pluggable strategy computation.

---

