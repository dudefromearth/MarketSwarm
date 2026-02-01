# Fly on the Wall (FOTW) — Playbook UI Flow & Integration Specification

## 1. Role of the Playbook in the App

The Playbook is the **capstone layer** of FOTW.

It sits *above*:
- Trade Log (what happened)
- Journal (what was experienced)
- Retrospectives (what patterns emerged)

The Playbook exists to:
- distill durable lessons
- encode earned constraints
- preserve hard-won filters
- reduce repeated mistakes

It does **not**:
- drive execution
- enforce rules
- block behavior
- replace thinking

---

## 2. Playbook as a Surface (Where It Lives)

### Playbook Access
The Playbook is accessed as an **overlay**, not a primary workspace.

- Opened intentionally
- Closed quickly
- Never replaces discovery or analysis views

This preserves the gravity of:
> Discovery → Analysis → Action → Reflection

Playbook is for **consultation**, not residence.

---

## 3. High-Level UI Flow (Mental Model)

The Playbook has **three primary flows**:

1. **Distill** (create entries from reflection)
2. **Browse** (review accumulated wisdom)
3. **Consult** (reference during analysis or reflection)

There is no “start with a blank Playbook” flow.

---

## 4. Entry Point 1 — Distillation Flow (Primary)

### Where Distillation Begins
Playbook entries are created only from:
- Journal Entries
- Weekly Retrospectives
- Monthly Retrospectives

There is **no global “New Playbook Entry” button**.

---

### UI Flow: Distill into Playbook

1. Trader is viewing a Journal entry or Retro
2. Entry is flagged as **“Potential Playbook Material”**
3. During review, trader selects one or more flagged entries
4. Trader chooses **“Distill into Playbook Entry”**

This opens the **Playbook Editor overlay**.

---

### Playbook Editor UI (Minimal)

The editor contains:

- **Title** (freeform)
- **Type selector**:
  - Pattern
  - Rule
  - Warning
  - Filter
  - Constraint
- **Body text** (freeform, markdown)
- **Source References** (auto-attached, read-only)

Key constraints:
- No auto-summarization
- No AI suggestions
- No validation
- No “best practice” hints

The trader writes in hindsight, not emotion.

---

## 5. Entry Point 2 — Playbook Browser (Review Mode)

### Purpose
The browser exists for:
- periodic review
- memory reinforcement
- pattern recall

Not for enforcement.

---

### Playbook Browser Layout

Each Playbook Entry is displayed as a **card or row** showing:
- Title
- Type
- Status (Draft / Active / Retired)
- Last updated date
- Source count

---

### Filtering & Navigation

Supported filters:
- Entry Type
- Status
- Text search

Explicitly excluded:
- ranking
- scoring
- “most used”
- “best rules”

Wisdom is not sortable by performance.

---

## 6. Entry Point 3 — Consultation Flow (Read-Only)

### From Analyzer
While viewing strategies in the Analyzer:
- Trader may optionally open Playbook overlay
- Relevant entries (by tag or manual selection) may be shown

No enforcement.  
No warnings.  
No blocking.

This is *memory recall*, not guidance.

---

### From Trade Log or Journal
- Trader may reference Playbook entries while journaling
- Links are manual and optional
- Journal entries never auto-suggest Playbook rules

This prevents hindsight bias.

---

## 7. Playbook Entry Lifecycle

### States
Each entry has a visible status:
- **Draft** — newly distilled, still forming
- **Active** — trusted and in use
- **Retired** — no longer applicable

---

### Retirement UI
Retiring an entry:
- is explicit
- does not delete history
- preserves lineage

Retired entries display as:
> “This was once true for me.”

This prevents dogma ossification.

---

## 8. Lineage & Traceability (Critical)

Each Playbook Entry displays:
- linked Journal Entries
- linked Retrospectives
- optional linked Trades

Lineage is:
- visible
- immutable
- read-only

Journal entries never reference Playbooks forward.

This preserves historical honesty.

---

## 9. Relationship to Trade Log

The Playbook does **not**:
- evaluate trades
- score adherence
- flag violations

Optional affordance:
- While reviewing a trade, trader may view Playbook entries side-by-side

The system never says:
> “You violated your Playbook.”

Responsibility stays human.

---

## 10. What the UI Must Avoid (Hard Constraints)

The Playbook UI must never:
- auto-generate rules
- auto-suggest changes
- enforce constraints
- block execution
- surface “compliance”
- rank entries
- gamify wisdom

Any of the above collapses trust.

---

## 11. Implementation Notes (Conceptual)

- Playbook is a **derived layer**
- Creation requires upstream artifacts
- All flows are:
  - manual
  - intentional
  - reversible
- Overlay pattern keeps Playbook consultative

---

## One-Sentence Essence

**The FOTW Playbook UI turns reflection into durable memory — by distilling lived experience into consultable wisdom, without ever enforcing behavior or replacing judgment.**