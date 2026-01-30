# FOTW Trade Log API Reference

**Version:** v2
**Base URL:** `http://localhost:3002`
**Content-Type:** `application/json`

## Overview

The FOTW Trade Log API provides a comprehensive trading journal system based on the Fly on the Wall (FOTW) doctrine. Key features include:

- **Multiple Trade Logs** - Named containers with immutable starting parameters
- **OPEN as First-Class State** - Trades explicitly tracked as open until closed
- **Lifecycle Events** - Audit trail of open, adjust, close events
- **Log-Scoped Analytics** - Performance metrics isolated per log
- **Symbol Registry** - Configurable contract multipliers
- **Settings Management** - Global and per-log configuration

---

## Response Format

All responses follow this structure:

```json
{
  "success": true,
  "data": { ... },
  "count": 10
}
```

Error responses:

```json
{
  "success": false,
  "error": "Error message"
}
```

### Price Handling

- **Internal Storage:** All prices are stored in **cents** (integer)
- **API Input:** Accepts both dollars (float) and cents (integer > 1000)
- **API Output:** Returns both cents and dollars (`entry_price` and `entry_price_dollars`)

---

## Health Check

### GET /health

Check service health status.

**Response:**
```json
{
  "success": true,
  "service": "journal",
  "version": "v2",
  "status": "healthy",
  "ts": "2026-01-30T13:11:00.697101"
}
```

---

## Trade Logs

Trade logs are containers for trades with immutable starting parameters (frozen at creation).

### GET /api/logs

List all trade logs with summary statistics.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `include_inactive` | boolean | false | Include archived logs |

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": "5f449637-939a-4826-a7a1-6a9b01788c61",
      "name": "0DTE Income",
      "starting_capital": 2500000,
      "starting_capital_dollars": 25000.0,
      "risk_per_trade": 50000,
      "risk_per_trade_dollars": 500.0,
      "max_position_size": null,
      "intent": "Daily 0DTE butterfly and vertical income trades",
      "constraints": null,
      "regime_assumptions": null,
      "notes": null,
      "is_active": 1,
      "created_at": "2026-01-30T08:32:28.511745",
      "updated_at": "2026-01-30T08:32:28.511750",
      "total_trades": 462,
      "open_trades": 0,
      "closed_trades": 462,
      "total_pnl": 3370400,
      "total_pnl_dollars": 33704.0
    }
  ],
  "count": 1
}
```

---

### GET /api/logs/:id

Get a single trade log with summary statistics.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | string | Trade log UUID |

**Response:** Same as single item from list response.

---

### POST /api/logs

Create a new trade log.

**Request Body:**
```json
{
  "name": "0DTE Income",
  "starting_capital": 25000,
  "risk_per_trade": 500,
  "max_position_size": null,
  "intent": "Daily 0DTE butterfly and vertical income trades",
  "constraints": { "max_contracts": 10 },
  "regime_assumptions": "Low VIX environment",
  "notes": "Starting fresh Q1 2026"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Log display name |
| `starting_capital` | number | Yes | Initial capital (dollars or cents) |
| `risk_per_trade` | number | No | Default risk per trade |
| `max_position_size` | integer | No | Maximum position size constraint |
| `intent` | string | No | Why this log exists |
| `constraints` | object | No | JSON constraints (position limits, etc.) |
| `regime_assumptions` | string | No | Market context assumptions |
| `notes` | string | No | Additional notes |

**Note:** `starting_capital`, `risk_per_trade`, and `max_position_size` are **immutable** after creation.

**Response:** `201 Created`
```json
{
  "success": true,
  "data": {
    "id": "new-uuid-here",
    "name": "0DTE Income",
    ...
  }
}
```

---

### PUT /api/logs/:id

Update trade log metadata. **Cannot update immutable starting parameters.**

**Request Body:**
```json
{
  "name": "Updated Name",
  "intent": "Updated intent",
  "notes": "Updated notes"
}
```

**Immutable Fields (ignored if provided):**
- `starting_capital`
- `risk_per_trade`
- `max_position_size`
- `id`
- `created_at`

---

### DELETE /api/logs/:id

Soft delete (archive) a trade log. Sets `is_active = 0`.

**Response:**
```json
{
  "success": true,
  "message": "Trade log archived"
}
```

---

## Trades

Trades belong to a specific log and track positions with lifecycle events.

### GET /api/logs/:logId/trades

List trades in a specific log.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `logId` | string | Trade log UUID |

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `status` | string | all | Filter: `open`, `closed`, or `all` |
| `symbol` | string | - | Filter by symbol (e.g., `SPX`) |
| `strategy` | string | - | Filter by strategy type |
| `from` | string | - | Start date (ISO 8601) |
| `to` | string | - | End date (ISO 8601) |
| `limit` | integer | 100 | Max results |
| `offset` | integer | 0 | Pagination offset |

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": "trade-uuid",
      "log_id": "log-uuid",
      "symbol": "SPX",
      "underlying": "I:SPX",
      "strategy": "butterfly",
      "side": "call",
      "strike": 6050.0,
      "width": 10,
      "dte": 0,
      "quantity": 1,
      "entry_time": "2026-01-30T10:30:00",
      "entry_price": 150,
      "entry_price_dollars": 1.50,
      "entry_spot": 6045.25,
      "entry_iv": 0.15,
      "exit_time": "2026-01-30T14:30:00",
      "exit_price": 450,
      "exit_price_dollars": 4.50,
      "exit_spot": 6052.00,
      "planned_risk": 15000,
      "planned_risk_dollars": 150.0,
      "max_profit": 90000,
      "max_profit_dollars": 900.0,
      "max_loss": 15000,
      "max_loss_dollars": 150.0,
      "pnl": 30000,
      "pnl_dollars": 300.0,
      "r_multiple": 2.0,
      "status": "closed",
      "notes": "Filled at open",
      "tags": ["0DTE", "Scalp"],
      "source": "heatmap",
      "playbook_id": null,
      "created_at": "2026-01-30T10:30:00",
      "updated_at": "2026-01-30T14:30:00"
    }
  ],
  "count": 1
}
```

---

### POST /api/logs/:logId/trades

Create a new trade. Automatically creates an OPEN event.

**Request Body:**
```json
{
  "symbol": "SPX",
  "underlying": "I:SPX",
  "strategy": "butterfly",
  "side": "call",
  "strike": 6050,
  "width": 10,
  "dte": 0,
  "quantity": 1,
  "entry_price": 1.50,
  "entry_spot": 6045.25,
  "entry_iv": 0.15,
  "entry_time": "2026-01-30T10:30:00",
  "planned_risk": 150,
  "max_profit": 900,
  "max_loss": 150,
  "notes": "Filled at open",
  "tags": ["0DTE", "Scalp"],
  "source": "heatmap",
  "playbook_id": null
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `strategy` | string | Yes | `single`, `vertical`, `butterfly`, `iron_condor` |
| `side` | string | Yes | `call`, `put`, or `both` |
| `strike` | number | Yes | Strike price |
| `symbol` | string | No | Symbol (default: `SPX`) |
| `underlying` | string | No | Underlying ticker (default: `I:SPX`) |
| `width` | integer | No | Spread width (for spreads) |
| `dte` | integer | No | Days to expiration |
| `quantity` | integer | No | Number of contracts (default: 1) |
| `entry_price` | number | Yes | Entry price (dollars or cents) |
| `entry_spot` | number | No | Underlying price at entry |
| `entry_iv` | number | No | Implied volatility at entry |
| `entry_time` | string | No | Entry timestamp (default: now) |
| `planned_risk` | number | No | Planned risk amount |
| `max_profit` | number | No | Maximum profit potential |
| `max_loss` | number | No | Maximum loss potential |
| `notes` | string | No | Trade notes |
| `tags` | array | No | Array of tag strings |
| `source` | string | No | `manual`, `heatmap`, `risk_graph` |
| `playbook_id` | string | No | Associated playbook ID |

**Response:** `201 Created`

---

### GET /api/trades/:id

Get a single trade with all lifecycle events.

**Response:**
```json
{
  "success": true,
  "data": {
    "id": "trade-uuid",
    "log_id": "log-uuid",
    "symbol": "SPX",
    "strategy": "butterfly",
    ...
    "events": [
      {
        "id": "event-uuid",
        "trade_id": "trade-uuid",
        "event_type": "open",
        "event_time": "2026-01-30T10:30:00",
        "price": 150,
        "price_dollars": 1.50,
        "spot": 6045.25,
        "quantity_change": null,
        "notes": null,
        "created_at": "2026-01-30T10:30:00"
      },
      {
        "id": "event-uuid-2",
        "trade_id": "trade-uuid",
        "event_type": "close",
        "event_time": "2026-01-30T14:30:00",
        "price": 450,
        "price_dollars": 4.50,
        "spot": 6052.00,
        "quantity_change": null,
        "notes": null,
        "created_at": "2026-01-30T14:30:00"
      }
    ]
  }
}
```

---

### PUT /api/trades/:id

Update trade metadata.

**Request Body:**
```json
{
  "notes": "Updated notes",
  "tags": ["0DTE", "Scalp", "Winner"]
}
```

**Protected Fields (cannot be updated):**
- `id`
- `log_id`
- `created_at`

---

### POST /api/trades/:id/adjust

Add an adjustment event to an open trade.

**Request Body:**
```json
{
  "price": 1.25,
  "quantity_change": 1,
  "spot": 6048.50,
  "notes": "Added contract on pullback",
  "event_time": "2026-01-30T11:30:00"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `price` | number | Yes | Price at adjustment |
| `quantity_change` | integer | Yes | Quantity change (+/-) |
| `spot` | number | No | Underlying price |
| `notes` | string | No | Adjustment notes |
| `event_time` | string | No | Timestamp (default: now) |

**Note:** Only works on trades with `status = "open"`.

---

### POST /api/trades/:id/close

Close a trade and calculate P&L.

**Request Body:**
```json
{
  "exit_price": 4.50,
  "exit_spot": 6052.00,
  "exit_time": "2026-01-30T14:30:00",
  "notes": "Took profit at target"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `exit_price` | number | Yes | Exit price (dollars or cents) |
| `exit_spot` | number | No | Underlying price at exit |
| `exit_time` | string | No | Exit timestamp (default: now) |
| `notes` | string | No | Close notes |

**P&L Calculation:**
```
P&L = (exit_price - entry_price) × multiplier × quantity
```

Where `multiplier` is looked up from the symbol registry.

---

### DELETE /api/trades/:id

Permanently delete a trade and all its events.

---

## Analytics

All analytics are log-scoped, following FOTW doctrine.

### GET /api/logs/:logId/analytics

Get full performance analytics for a log.

**Response:**
```json
{
  "success": true,
  "data": {
    "log_id": "uuid",
    "log_name": "0DTE Income",

    "span_days": 567,
    "total_trades": 462,
    "trades_per_week": 5.7,

    "starting_capital": 2500000,
    "starting_capital_dollars": 25000.0,
    "current_equity": 5870400,
    "current_equity_dollars": 58704.0,
    "net_profit": 3370400,
    "net_profit_dollars": 33704.0,
    "total_return_percent": 134.816,

    "open_trades": 0,
    "closed_trades": 462,
    "winners": 224,
    "losers": 234,
    "breakeven": 4,
    "win_rate": 48.48,
    "avg_win": 33301,
    "avg_win_dollars": 333.01,
    "avg_loss": -17475,
    "avg_loss_dollars": -174.75,
    "win_loss_ratio": 1.91,

    "avg_risk": 0,
    "avg_risk_dollars": 0.0,
    "largest_win": 235500,
    "largest_win_dollars": 2355.0,
    "largest_loss": -94000,
    "largest_loss_dollars": -940.0,
    "largest_win_pct_gross": 3.16,
    "largest_loss_pct_gross": 2.30,

    "gross_profit": 7459600,
    "gross_profit_dollars": 74596.0,
    "gross_loss": 4089200,
    "gross_loss_dollars": 40892.0,
    "avg_net_profit": 7295,
    "avg_net_profit_dollars": 72.95,

    "profit_factor": 1.82,
    "max_drawdown_pct": 4.83,
    "avg_r_multiple": 0.0,
    "avg_r2r": 8.45,
    "sharpe_ratio": 4.0
  }
}
```

### Analytics Categories (FOTW Reporting)

| Category | Metrics |
|----------|---------|
| **Time & Scale** | `span_days`, `total_trades`, `trades_per_week` |
| **Capital & Returns** | `starting_capital`, `current_equity`, `net_profit`, `total_return_percent` |
| **Win/Loss Distribution** | `winners`, `losers`, `breakeven`, `win_rate`, `avg_win`, `avg_loss`, `win_loss_ratio` |
| **Risk & Asymmetry** | `avg_risk`, `largest_win`, `largest_loss`, `largest_win_pct_gross`, `largest_loss_pct_gross` |
| **System Health** | `profit_factor`, `max_drawdown_pct`, `avg_r_multiple`, `avg_r2r`, `sharpe_ratio` |

---

### GET /api/logs/:logId/equity

Get equity curve data points.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `from` | string | Start date (ISO 8601) |
| `to` | string | End date (ISO 8601) |

**Response:**
```json
{
  "success": true,
  "data": {
    "equity": [
      {
        "time": "2022-06-21T11:15:00",
        "value": 0,
        "trade_id": null
      },
      {
        "time": "2022-06-21T11:15:00",
        "value": 12500,
        "trade_id": "trade-uuid"
      }
    ]
  }
}
```

**Note:** `value` is cumulative P&L in cents (relative to starting capital).

---

### GET /api/logs/:logId/drawdown

Get drawdown curve data points.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `from` | string | Start date (ISO 8601) |
| `to` | string | End date (ISO 8601) |

**Response:**
```json
{
  "success": true,
  "data": {
    "drawdown": [
      {
        "time": "2022-06-21T11:15:00",
        "drawdown_pct": 0.0,
        "peak": 2500000,
        "current": 2500000
      },
      {
        "time": "2022-06-22T12:00:00",
        "drawdown_pct": 2.5,
        "peak": 2600000,
        "current": 2535000
      }
    ]
  }
}
```

---

### GET /api/logs/:logId/distribution

Get return distribution histogram.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `bin_size` | integer | 50 | Bin size in dollars |

**Response:**
```json
{
  "success": true,
  "data": {
    "distribution": [
      {
        "bin_start": -50000,
        "bin_start_dollars": -500.0,
        "bin_end": -45000,
        "bin_end_dollars": -450.0,
        "count": 5,
        "is_zero": false
      },
      {
        "bin_start": -5000,
        "bin_start_dollars": -50.0,
        "bin_end": 0,
        "bin_end_dollars": 0.0,
        "count": 15,
        "is_zero": true
      }
    ],
    "bin_size_dollars": 50
  }
}
```

---

## Export/Import

### GET /api/logs/:logId/export

Export trades as CSV or Excel.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `format` | string | csv | `csv` or `xlsx` |

**Response:** File download with appropriate Content-Type.

**Export Columns:**
```
entry_time, symbol, underlying, strategy, side, strike, width,
dte, quantity, entry_price, entry_spot, exit_time, exit_price,
exit_spot, pnl, r_multiple, status, planned_risk, max_profit,
max_loss, notes, tags, source
```

---

### POST /api/logs/:logId/import

Import trades from CSV or Excel file.

**Request:** `multipart/form-data` with file upload.

**Response:**
```json
{
  "success": true,
  "imported": 45,
  "errors": ["Row 12: Invalid strategy"],
  "total_errors": 1
}
```

**Import Format:** Same columns as export. Accepts:
- CSV files (UTF-8 or Latin-1 encoding)
- Excel files (.xlsx, .xls)

---

## Symbols

Symbol registry with contract multipliers.

### GET /api/symbols

List all symbols.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `include_disabled` | boolean | Include disabled symbols |
| `asset_type` | string | Filter by type: `index_option`, `etf_option`, `future`, `stock` |

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "symbol": "SPX",
      "name": "S&P 500 Index",
      "asset_type": "index_option",
      "multiplier": 100,
      "enabled": true,
      "is_default": true,
      "created_at": "2026-01-30T10:05:55"
    },
    {
      "symbol": "ES",
      "name": "E-mini S&P 500",
      "asset_type": "future",
      "multiplier": 50,
      "enabled": true,
      "is_default": true,
      "created_at": "2026-01-30T10:05:55"
    }
  ],
  "count": 26
}
```

### Default Symbols

| Symbol | Name | Type | Multiplier |
|--------|------|------|------------|
| SPX | S&P 500 Index | index_option | 100 |
| NDX | Nasdaq 100 Index | index_option | 100 |
| RUT | Russell 2000 Index | index_option | 100 |
| XSP | Mini-SPX | index_option | 100 |
| VIX | CBOE Volatility Index | index_option | 100 |
| SPY | SPDR S&P 500 ETF | etf_option | 100 |
| QQQ | Invesco QQQ Trust | etf_option | 100 |
| IWM | iShares Russell 2000 | etf_option | 100 |
| ES | E-mini S&P 500 | future | 50 |
| MES | Micro E-mini S&P 500 | future | 5 |
| NQ | E-mini Nasdaq 100 | future | 20 |
| MNQ | Micro E-mini Nasdaq | future | 2 |
| CL | Crude Oil | future | 1000 |
| GC | Gold | future | 100 |

---

### GET /api/symbols/:symbol

Get a single symbol.

---

### POST /api/symbols

Add a new custom symbol.

**Request Body:**
```json
{
  "symbol": "TSLA",
  "name": "Tesla Inc",
  "asset_type": "stock",
  "multiplier": 100,
  "enabled": true
}
```

---

### PUT /api/symbols/:symbol

Update a symbol. Can update `name`, `multiplier`, `enabled`.

---

### DELETE /api/symbols/:symbol

Delete a custom symbol. **Cannot delete default symbols.**

---

## Settings

Global and per-log configuration settings.

### GET /api/settings

Get all settings.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `scope` | string | global | `global` or specific log ID |
| `category` | string | - | Filter by category |

**Response:**
```json
{
  "success": true,
  "data": {
    "trading": {
      "default_risk_per_trade": 500,
      "default_symbol": "SPX"
    },
    "display": {
      "theme": "dark"
    }
  },
  "scope": "global"
}
```

---

### GET /api/settings/:key

Get a single setting.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `scope` | string | Scope (`global` or log ID) |
| `log_id` | string | If provided, returns effective setting with per-log override |

---

### PUT /api/settings/:key

Set a setting value.

**Request Body:**
```json
{
  "value": 500,
  "category": "trading",
  "scope": "global",
  "description": "Default risk per trade in dollars"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `value` | any | Yes | Setting value (any JSON type) |
| `category` | string | Yes | Category: `trading`, `display`, `ai`, etc. |
| `scope` | string | No | `global` or specific log ID |
| `description` | string | No | Human-readable description |

---

### DELETE /api/settings/:key

Delete a setting.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `scope` | string | global | Scope to delete from |

---

## Legacy Endpoints

For backwards compatibility with v1 clients.

| Endpoint | Behavior |
|----------|----------|
| `GET /api/trades` | Lists trades from first active log |
| `POST /api/trades` | Creates trade in first active log (auto-creates default log if needed) |
| `GET /api/analytics` | Analytics from first active log |
| `GET /api/analytics/equity` | Equity curve from first active log |

---

## Error Codes

| Status | Description |
|--------|-------------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request (missing/invalid parameters) |
| 403 | Forbidden (e.g., deleting default symbol) |
| 404 | Not Found |
| 409 | Conflict (e.g., duplicate symbol) |
| 500 | Internal Server Error |

---

## Examples

### Create a Trade Log and Add a Trade

```bash
# Create log
curl -X POST http://localhost:3002/api/logs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Paper Trading",
    "starting_capital": 10000,
    "risk_per_trade": 200,
    "intent": "Testing new butterfly strategy"
  }'

# Response: {"success": true, "data": {"id": "abc123", ...}}

# Add trade to log
curl -X POST http://localhost:3002/api/logs/abc123/trades \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "SPX",
    "strategy": "butterfly",
    "side": "call",
    "strike": 6050,
    "width": 10,
    "entry_price": 1.50,
    "max_profit": 900
  }'
```

### Close a Trade

```bash
curl -X POST http://localhost:3002/api/trades/trade-uuid/close \
  -H "Content-Type: application/json" \
  -d '{
    "exit_price": 4.50,
    "notes": "Hit profit target"
  }'
```

### Get Analytics

```bash
curl http://localhost:3002/api/logs/abc123/analytics
```

### Export Trades

```bash
# CSV
curl -o trades.csv "http://localhost:3002/api/logs/abc123/export?format=csv"

# Excel
curl -o trades.xlsx "http://localhost:3002/api/logs/abc123/export?format=xlsx"
```
