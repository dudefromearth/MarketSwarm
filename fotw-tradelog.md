# FOTW Trade Log — Feature Set & Purpose

## Core Role of the Trade Log  
**Role:** Accountability surface for trades the trader claims as real.

The Trade Log is where a trader says:  
> “This position exists, and I’m responsible for it.”

It is not a decision engine, not a broker mirror, and not a performance judge.

---

## 1. Multiple Trade Logs (Context Separation)

- Traders can create **one or more trade logs**
- Logs are **named** (e.g., “0DTE Income,” “Fat Tail Probes,” “Learning Sandbox”)
- Each log has **attached metadata**:
  - intent
  - constraints
  - regime assumptions
  - optional notes

**Why this matters in FOTW:**  
Truth is contextual. Logs define *which game* was being played.

---

## 2. Declared Starting Parameters (Frozen Context)

Each log stores:
- starting capital (declared)
- optional risk constraints
- optional position sizing assumptions

These parameters are:
- saved with the log
- immutable for historical interpretation

**Why this matters:**  
Performance is always interpreted relative to declared intent — not hindsight.

---

## 3. Easy Trade Entry (Low Friction, High Honesty)

Trades can be added:
- manually
- from the Analyzer
- from the Analyzer Strategy List

Trade entry supports:
- open trades (no exit yet)
- partial information
- later completion

**Why this matters:**  
Disconnected logs must prioritize *truthful declaration* over procedural neatness.

---

## 4. Open Trade State (Explicit, First-Class)

Trades can exist in an **OPEN** state:
- entry declared
- no exit price yet
- clearly marked as unresolved

Open is a **state**, not a missing field.

**Why this matters:**  
Real trades are open before they are closed. The log should reflect reality.

---

## 5. Strategy-Referenced Trades

Every trade:
- references exactly one Strategy
- inherits its geometry and expiration
- does not redefine structure

**Why this matters:**  
Trades instantiate strategies — they do not invent them.

---

## 6. Position Grouping & Lifecycle Tracking

Trades support:
- multiple legs (grouped)
- lifecycle events:
  - open
  - adjust (optional)
  - close

Adjustments are events, not rewrites.

**Why this matters:**  
History matters. Trades tell what happened, not what was intended later.

---

## 7. Bidirectional Analyzer Integration

Any trade in the log can be:
- selected
- sent back to the Analyzer
- viewed alone or alongside other strategies
- re-analyzed as conditions change

**Why this matters:**  
Risk management is ongoing analysis, not memory.

---

## 8. Log-Level Analytics (Derived Only)

Each log can generate:
- equity curve
- drawdown profile
- basic statistics

All stats are:
- derived
- read-only
- relative to starting parameters

No manual edits.

**Why this matters:**  
The system reports outcomes — it does not grade decisions.

---

## 9. Shareable Log Views (Context Preserved)

Logs can be:
- viewed
- shared
- exported

Shared views include:
- log metadata
- starting parameters
- trade history
- performance outputs

**Why this matters:**  
Sharing becomes a bounded claim, not performance theater.

---

## 10. Journal Integration (Referential, Not Required)

Trades can be:
- referenced from Journal entries
- reviewed alongside reflections

But:
- trades do not require journal entries
- journals do not require trades

**Why this matters:**  
Reflection is optional, but available — never forced.

---

## 11. No Transactional Enforcement (By Design)

The Trade Log does **not**:
- sync to a broker
- verify fills
- enforce timestamps
- reconcile executions

**Why this matters:**  
Responsibility stays with the trader, not the system.

---

## 12. No Decision Authority (Explicit Non-Features)

The Trade Log does **not**:
- suggest actions
- flag “mistakes”
- optimize exits
- score performance
- gamify results

**Why this matters:**  
Accountability without authority preserves sovereignty.

---

## 13. Clean Exit Declaration

Closing a trade:
- is explicit
- records exit price
- finalizes P&L

No retroactive changes.

**Why this matters:**  
Closure is a conscious act, not an automatic consequence.

---

## One-Sentence Essence

**The FOTW Trade Log is a self-declared ledger of responsibility — easy to enter, honest in what it records, and always subordinate to risk truth and reflection.**