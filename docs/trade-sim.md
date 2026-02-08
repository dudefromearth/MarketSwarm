# Big Ass Fly# 📐 FOTW Trade Simulation & Risk Graph Spec  
**Purpose-Aligned Specification**

---

## 0. Design Doctrine (Non-Negotiable)

FOTW is a **decision-support mirror**, not a prediction engine.

Therefore:
- **What-If = exploration**
- **Live = time-anchored truth capture**
- **Trades evolve; history does not**
- **Positions, not narratives, are the object**

This spec enforces that doctrine at the UI, data, and behavior layers.

---

## 1. Mode System (Global)

### 1.1 Mode Toggle (Risk Graph Header)

**Toggle Labels**
- `LIVE`
- `WHAT-IF`

**Behavior**
- Toggle is global to the Risk Graph context
- Mode state is always visible
- Switching modes is explicit and intentional (no auto-switching)

---

### 1.2 Mode Semantics

#### 🧪 WHAT-IF MODE
**Purpose:**  
Theoretical exploration of payoff shapes, convexity, and stress scenarios.

**Characteristics**
- Fully editable parameters:
  - Strikes
  - Widths
  - Expiry
  - Spot
  - Volatility
  - Structure type
- No time anchoring
- No trade persistence
- No positions created
- No orders generated

**Mental Model**
> “What *could* this look like?”

---

#### 🔴 LIVE MODE
**Purpose:**  
Simulated real-time trading that mirrors actual decision conditions.

**Characteristics**
- Time-anchored to market hours
- Structure becomes immutable once a trade is placed
- Actions append; history persists
- Trades appear in Monitor
- Risk Graph reflects current position state

**Mental Model**
> “What did I *actually* do, given what I knew then?”

---

### 1.3 Control Gating

When in **LIVE** mode:
- All WHAT-IF controls are **disabled / darkened**
- Tooltip copy (example):
  > “What-If controls are disabled in Live mode to preserve trade integrity.”

This visually reinforces the mirror boundary.

---

## 2. Monitor System (New)

### 2.1 Monitor Entry Point

**UI Element**
- 📊 **Monitor icon** in Risk Graph toolbar

**Interaction**
- Click → opens Monitor panel (modal, drawer, or floating window)
- Non-blocking (Risk Graph remains visible)

---

### 2.2 Monitor Purpose

The Monitor is the **position truth layer**.

It answers one question only:
> “What positions and orders do I currently have?”

No analytics, no narratives, no optimization.

---

### 2.3 Monitor Contents

#### A. Pending Orders
Orders waiting to fill (e.g., limit orders)

Fields:
- Strategy type
- Direction (Long / Short)
- Debit / Credit
- Status: `PENDING`
- Associated trade-log
- Timestamp (created)

---

#### B. Trades Table

Shows trades with status:
- `OPEN`
- `CLOSED`
- `CANCELED`

Each row displays:
- Strategy form (Butterfly / Vertical / Single / etc.)
- Direction (Long / Short)
- Debit / Credit
- Trade-log name
- Status
- Entry timestamp
- Exit timestamp (if closed)

This is **state**, not evaluation.

---

### 2.4 Trade Interaction Rules (Live Mode)

From Monitor, users may:
- Close trades
- Add management actions (scale, hedge, partial close)
- View trade details (read-only core)

Users may **not**:
- Edit entry parameters
- Change structure
- Rewrite timestamps
- Convert Live trades into What-If trades

---

## 3. Trade-Log Integration

### 3.1 Trade-Log Selector (Entry Point)

**Where**
- TradeEntryModal
- Strategy-specific entry windows

**Behavior**
- Trade-log selection is **required** before placing a Live trade
- Default log may be pre-selected, but user must confirm

**Purpose**
- Forces intentional classification
- Prevents orphan trades
- Preserves journaling integrity

---

### 3.2 Trade-Log Role

Trade-logs are:
- Containers for reflection and review
- Not execution tools
- Not editable from the Monitor

Each trade belongs to **exactly one log**.

---

## 4. Risk Graph Behavior (Live Mode)

### 4.1 Risk Graph = Position Mirror

When a Live trade exists:
- Risk Graph reflects **current composite exposure**
- Updates dynamically as:
  - Orders fill
  - Adjustments occur
  - Positions are closed

The Risk Graph:
- Never shows hypothetical shapes for Live trades
- Never allows parameter edits
- Only visualizes resulting structure

---

### 4.2 Risk Graph in What-If Mode

- Entirely detached from Monitor
- No persistence
- No linkage to trade-logs
- No side effects

---

## 5. Separation Summary (Enforced)

| Layer | What-If | Live |
|-----|--------|------|
| Purpose | Explore possibilities | Capture decisions |
| Time-anchored | ❌ | ✅ |
| Editable | Fully | Append-only |
| Creates trades | ❌ | ✅ |
| Appears in Monitor | ❌ | ✅ |
| Alters history | ❌ | ❌ |
| Supports learning | Indirect | Direct |

---

## 6. Why This Supports FOTW

This spec:
- Preserves **mirror integrity**
- Prevents **hindsight laundering**
- Separates **imagination from exposure**
- Allows **convexity learning under tension**
- Avoids gamification drift

> FOTW remains a structure-revealing system, not a narrative-editing system.

---

## 7. Product Truth (One Sentence)

**What-If shows what *could* happen.  
Live shows what *did* happen.  
The Monitor makes sure you can’t confuse the two.**