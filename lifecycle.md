**Lifecycle SSE · Import Preview Integration · Vexy Meta-Analysis** 

This document defines the exact behaviors, events, APIs, and data contracts required to complete the next phase of Trade Log lifecycle integration across Fly on the Wall.

---

## **1. SSE EVENTS — LOG LIFECYCLE SYNC**

### **Purpose**

Ensure **all open surfaces update immediately** when a log changes lifecycle state (archive, reactivate, retire, cancel retire, ML inclusion change).

### **SSE Channel**

```
GET /sse/logs
```

User-scoped (authenticated), persistent connection.

---

### **Event Envelope (Standard)**

```
{
  "type": "log.lifecycle.updated",
  "timestamp": "2026-03-02T14:22:11Z",
  "payload": { ... }
}
```

---

### **Lifecycle Event Types**

#### **1.1 Log Archived**

```
{
  "type": "log.lifecycle.archived",
  "payload": {
    "log_id": "uuid",
    "lifecycle_state": "archived",
    "archived_at": "2026-03-02T14:22:11Z",
    "ml_included": false
  }
}
```

#### **1.2 Log Reactivated**

```
{
  "type": "log.lifecycle.reactivated",
  "payload": {
    "log_id": "uuid",
    "lifecycle_state": "active",
    "reactivated_at": "2026-03-02T14:25:44Z",
    "active_log_count": 6,
    "cap_state": "soft_warning" 
  }
}
```

#### **1.3 Retirement Scheduled**

```
{
  "type": "log.lifecycle.retire_scheduled",
  "payload": {
    "log_id": "uuid",
    "retire_scheduled_at": "2026-03-09T00:00:00Z",
    "grace_days_remaining": 7
  }
}
```

#### **1.4 Retirement Cancelled**

```
{
  "type": "log.lifecycle.retire_cancelled",
  "payload": {
    "log_id": "uuid",
    "lifecycle_state": "archived"
  }
}
```

#### **1.5 Log Retired (Final)**

```
{
  "type": "log.lifecycle.retired",
  "payload": {
    "log_id": "uuid",
    "retired_at": "2026-03-09T00:00:01Z"
  }
}
```

---

### **UI Responsibilities on SSE**

* Update **LogSelector**
* Update **Import Preview**
* Update **ML inclusion indicators**
* Update **Process drawer badges**
* Notify Vexy context engine (internal)
---

## **2. IMPORT PREVIEW INTEGRATION — LOG-AWARE IMPORTS**

### **Purpose**

Guide users toward **correct log selection** during imports while preventing destructive mistakes.

---

### **Import Preview Flow**

#### **Step 1 — Parse Import**

* Broker formats: ToS, IB, Tasty
* AI formats: CSV, Excel, Numbers, text
* Extract:

  * Date range
  * Symbols
  * Trade count
  * Position overlap
---

#### **Step 2 — Fetch Candidate Logs**

```
GET /api/logs?include=archived
```

Each log includes:

```
{
  "id": "uuid",
  "name": "string",
  "lifecycle_state": "active | archived | retiring",
  "open_positions": 0,
  "ml_included": true,
  "last_trade_at": "2026-02-01",
  "created_at": "2025-11-01"
}
```

---

### **Recommendation Logic**

A **recommendation banner** is shown when any rule matches:

|  **Condition**  |  **Recommendation**  | 
|---|---|
|  Import data > 7 days old  |  Suggest archived log  |
|  No overlap with active log trades  |  Suggest archived or new log  |
|  Import > 100 trades  |  Suggest dedicated log  |
|  ML excluded log selected  |  Warning shown  |
---

### **Example Banner**

> ⚠️ *This import appears historical (Dec 2025).* 

> **Recommendation:** Import into an archived log or create a new one.

---

### **User Control**

* User may override recommendations
* Override reason is logged:

```
{
  "event": "import.override",
  "reason": "intentional backfill"
}
```

---

## **3. VEXY INTEGRATION — META-LOG AWARENESS**

### **Purpose**

Vexy acts as the **meta-alert and coaching layer**, synthesizing log health, activity, ML participation, and behavior.

---

## **3.1 Scheduled Analysis Job**

### **Job**

```
cron: daily @ 05:00 ET
```

### **Job Name**

```
log_health_analyzer
```

---

### **Metrics Computed Per Log**

```
{
  "log_id": "uuid",
  "days_inactive": 21,
  "total_trades": 842,
  "ml_included": false,
  "open_positions": 0,
  "alerts_pending": 0,
  "last_import_at": "2025-12-01"
}
```

---

## **3.2 Vexy Context Feed**

### **Ingest Endpoint**

```
POST /api/vexy/context/log-health
```

Payload:

```
{
  "log_id": "uuid",
  "signals": [
    {
      "type": "log_inactive",
      "value": 21,
      "severity": "low"
    }
  ]
}
```

---

## **3.3 Vexy Suggestions (Examples)**

|  **Scenario**  |  **Vexy Prompt**  | 
|---|---|
|  Inactive 21 days  |  “This log hasn’t been used in 3 weeks. Archive it?”  |
|  ML excluded  |  “Trades here aren’t improving the system.”  |
|  Retiring soon  |  “This log retires in 2 days. Reactivate?”  |
|  Soft cap reached  |  “You have 5 active logs — consider consolidating.”  |
---

### **Delivery Surfaces**

* Routine Drawer (gentle)
* Process Drawer (reflective)
* Import Preview (actionable)
* Log Manager Modal (inline)
---

## **4. SYSTEM-LEVEL GUARANTEES**

* **No silent state changes**
* **All lifecycle transitions are reversible** (until final retire)
* **ML training only uses active, ML-included logs**
* **Vexy never blocks — only advises**
* **User intent always wins (with friction + audit)**
---

## **5. IMPLEMENTATION CHECKLIST**

* Emit SSE events from all lifecycle mutations
* Wire SSE to LogSelector + Import Preview
* Add daily log_health_analyzer job
* Feed log context into Vexy
* Surface Vexy suggestions contextually
---

