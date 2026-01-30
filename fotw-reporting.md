# FOTW Trade Log — Reporting & Analytics

## Role of Reporting  
**Role:** Outcome evidence and post-action truth.

The reporting side of the Trade Log answers one question only:

> *“Given the trades I declared under these starting assumptions, what actually happened?”*

It does **not**:
- explain results
- recommend changes
- judge decisions
- optimize behavior

It exists to show reality clearly so reflection can occur elsewhere.

---

## 1. Equity Curve (Primary Output)

### What It Shows
- Account equity over time
- Based on **declared starting capital**
- Updated only by **closed trades**

This is the primary visual representation of outcomes.

### Design Constraints
- No smoothing
- No projections
- No hypothetical paths
- No “what-if” scenarios

**Why this matters in FOTW:**  
Equity is the only outcome that compounds. Everything else is secondary.

---

## 2. Drawdown Chart (Second Axis of Truth)

Displayed directly below the equity curve:

- Percentage drawdown from equity peak
- Same timeline and resolution as equity

### Why This Is Critical
- Drawdown is where process breaks
- Drawdown is where philosophy is tested
- Traders experience drawdown before they understand returns

In FOTW, drawdown is **co-equal** with equity, not a footnote.

---

## 3. Summary Statistics Panel (Derived, Read-Only)

Statistics provide structural context, not evaluation.

All statistics are:
- derived automatically
- read-only
- scoped to the selected trade log

No manual overrides or exclusions.

---

### 3.1 Time & Scale

- Span in days
- Total trades
- Trades per unit time (optional)

**Purpose:**  
Contextualizes how results were produced.

---

### 3.2 Capital & Returns

- Starting capital
- Ending balance
- Net profit
- Total return (%)

**Purpose:**  
Reports factual outcomes without interpretation.

---

### 3.3 Win / Loss Distribution

- Winners
- Losers
- Win rate
- Average winning trade
- Average losing trade
- Ratio of average win / loss

**Purpose:**  
Reveals edge structure, not success or failure.

---

### 3.4 Risk & Asymmetry

- Average risk per trade
- Largest winner
- Largest loser
- Winner as % of gross profit
- Loser as % of gross loss

**Purpose:**  
Shows whether convexity and risk asymmetry are present.

---

### 3.5 System Health Metrics

- Profit factor
- Maximum drawdown
- Average R-multiple (or R2R)
- Sharpe ratio (optional but acceptable here)

**Purpose:**  
Answers one question:

> *“Was this survivable?”*

Not:
> *“Was this optimal?”*

---

## 4. Absolute Rules

- All metrics are derived from logged trades
- No editable statistics
- No “adjusted” views
- No hidden filters

If a trader wants a different story, they must create a different log.

---

## 5. Log-Scoped Reporting (Critical Constraint)

All reporting is:
- scoped to a single trade log
- interpreted relative to that log’s starting parameters
- isolated from other logs by default

There is no global equity curve unless explicitly requested.

**Why this matters:**  
Different logs represent different games. Combining them by default lies.

---

## 6. Reporting Is Intentional, Not Default

Reporting views:
- are entered deliberately
- feel like review mode
- never auto-open after trades

The center of gravity in FOTW remains:
- discovery
- analysis
- risk awareness

Reporting supports:
- weekly review
- campaign post-mortems
- playbook extraction

Not dopamine loops.

---

## 7. Relationship to Journal & Playbooks

Reporting does not create insight.  
It **triggers reflection**.

Correct flow:

> Equity / Drawdown → Journal Reflection → Playbook Distillation

Never:

> Statistics → Recommendation → Rule

This preserves learning integrity.

---

## One-Sentence Essence

**The reporting side of the FOTW Trade Log is a clean mirror of outcomes — equity, drawdown, and statistics — shown without commentary, optimization, or narrative, so reflection can do its work.**