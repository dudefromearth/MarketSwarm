# Heatmap & GEX Model Builder Design Document

## Abstract

The Heatmap and GEX models are the final, calculated products of the Massive pipeline. They are published as JSON to Redis endpoints that the React dashboard consumes directly. The Heatmap model represents a strategy-specific grid of tiles (strikes × widths for Butterfly/Vertical, strikes only for Single), with each tile containing the debit/credit value for that position. The GEX model provides gamma exposure aggregated by strike and expiration. Both models are designed to be immediately usable by the React UI for rendering the convexity heatmap, GEX bar chart, and interactive tile popups.

## Executive Summary

The HeatmapModelBuilder (and GexModelBuilder) run in the **Calculate Strategy** stage. They read the current epoch's hydrated contracts, compute strategy-specific values, and publish complete JSON models to Redis. The UI reads these models via SSE and renders:
- A central convexity heatmap grid (strategy selectable).
- A left-side GEX bar chart.
- Clickable tiles with detailed popups (trade legs, ToS script, metrics).

The models are structured for direct React consumption: nested objects keyed by strike/width/DTE, with pre-calculated values and metadata.

## Table of Contents

1. Model Build Process  
2. Inputs to Builders  
3. Calculations Performed  
4. Published Model Structure (Redis Endpoints)  
5. How the React UI Consumes the Models  
6. Current State & Recommended Updates  

## 1. Model Build Process

Model builders run every ~1 second (configurable).

- **Trigger**: Builder loop (or dirty epoch flag in future incremental version).
- **Read**: All contracts from current epoch (`epoch:{id}:contract:*`).
- **Compute**: Strategy-specific tile values (Butterfly, Vertical, Single) and GEX aggregates.
- **Publish**: JSON models to Redis keys.
- **Clean**: Mark epoch clean (signals completion).

## 2. Inputs to Builders

- **Epoch Contracts** (from normalizers + hydrator):
  - Strike, expiration, type (call/put).
  - Mid, bid, ask (live from WS).
  - Gamma, open interest, multiplier (from chain).
- **Config**:
  - Widths for Butterfly/Vertical (e.g., 20,25,30,35,40,45,50).
  - Strategy selection (currently all three).

## 3. Calculations Performed

### Heatmap (Strategy Tiles)
- **Butterfly**:
  - Tile at (center_strike, width) = debit = low_mid + high_mid - 2 × center_mid
  - low = center - width, high = center + width
- **Vertical**:
  - Tile at (low_strike, width) = debit = high_mid - low_mid
  - high = low + width
- **Single**:
  - Tile at strike = mid price (call or put)

### GEX
- Per strike/expiration: gamma × open_interest × multiplier (100).
- Separate for calls and puts.
- Published as nested dict (expiration → strike → gex).

## 4. Published Model Structure (Redis Endpoints)

**Heatmap Models** (three separate keys):
```
massive:heatmap:model:{symbol}:butterfly
massive:heatmap:model:{symbol}:vertical
massive:heatmap:model:{symbol}:single
```

**Example JSON Structure** (Butterfly):
```json
{
  "ts": 1700000000.123,
  "symbol": "SPX",
  "epoch": "SPX:1700000000:abc",
  "tiles": {
    "6865": {
      "20": 1.10,
      "25": 1.80,
      "30": 2.65,
      "35": 3.75,
      "40": 5.10,
      "45": 6.80,
      "50": 8.70
    },
    "6870": {
      "20": 1.15,
      "25": 1.85,
      "...": "..."
    }
    // ... all strikes with available legs
  }
}
```

**GEX Model**:
```
massive:gex:model:{symbol}:calls
massive:gex:model:{symbol}:puts
```

**Example (calls)**:
```json
{
  "ts": 1700000000.123,
  "symbol": "SPX",
  "expirations": {
    "2025-12-31": {
      "6865": 12345678.9,
      "6870": 9876543.2,
      "...": "..."
    }
  }
}
```

All models have short-medium TTL (30-60s) and are refreshed every builder cycle.

## 5. How the React UI Consumes the Models

The current React page (as shown in your screenshot):
- **Left panel**: Renders GEX bar chart from calls/puts models (strike on y-axis, gamma exposure on x-axis, green positive, red negative).
- **Right panel**: Renders convexity heatmap grid.
  - Rows = strikes (descending).
  - Columns = widths (20 to 50+).
  - Cell value = debit/credit from selected strategy model.
  - Cell color = convexity gradient (red = fast debit drop OTM, blue = slower — from separate coloring tool).
  - DTE tabs = switch expiration buckets (0DTE shown).
- **Tile click**: Popup with detailed trade info, metrics (RR, IV, Vega, score), and "Copy Trade" ToS script.

The UI subscribes to SSE for these model keys and updates the grid/chart on diffs.

## 6. Current State & Recommended Updates

**Current HeatmapModelBuilder**:
- Only builds geometry ZSET and raw snapshot.
- **Missing**: Tile calculations and publication of `massive:heatmap:model:*` keys.
- **Result**: UI likely renders from snapshot or geometry manually (heavy client work).

**Recommended Update**:
- Extend builder to compute and publish the three strategy models as shown in section 4.
- Add tile metadata (legs, ToS script) for popup readiness.
- Keep snapshot for backward compatibility/diagnostics.

This brings the backend in line with the UI you showed — full, calculated, strategy-specific tile grids ready for direct rendering.

**Reflection Prompt:** Where might bias toward raw snapshot reliance be creeping in from legacy UI? What’s the smallest optional action to add butterfly tile calc to builder today?