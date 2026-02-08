# Trade Log Lifecycle & Import Targeting Specification  
## Fly on the Wall (FOTW)

---

## Purpose

Define a flexible, safe, and process-aligned model for managing **trade logs** and **imports** within Fly on the Wall.

This specification ensures that:
- Traders are never painted into a corner
- Historical data can be explored without contaminating live practice
- Machine learning and alerts maintain clean data boundaries
- Logs support evolution, reflection, and reversal

This is a **simulator- and practice-first system**, with optional applicability to live trading.

---

## Core Concepts

- Trade Logs represent **practice narratives / campaigns**, not rigid ledgers
- Logs are **never hard-deleted**
- Imports are **explicitly targeted** and **fully reversible**
- Only a limited number of logs participate in the **live workflow**

---

## Trade Log States

| State        | Description |
|-------------|-------------|
| **Active**   | Participates in daily workflow, alerts, ML, and live analysis |
| **Archived** | Read-only; excluded from alerts and ML by default |
| **Retired**  | Frozen + hidden; preserved in cold storage |

---

## 1. Active Log Limits

### Specification

- **Unlimited total trade logs**
- **Soft cap on active trade logs**
  - Recommended default: **5 active logs**
  - Absolute hard maximum: **10 active logs**

The limit applies **only** to logs in the `active` state.

### Behavior at Limit

- If the user attempts to activate a log beyond the hard limit:
  - Activation is blocked
  - User is prompted to archive another active log
- No automatic archiving occurs without explicit user action

### Rationale

- Prevents cognitive overload
- Encourages focused campaigns
- Avoids irreversible early mistakes
- Preserves long-term flexibility

---

## 2. Archiving Behavior

### Archive Trigger

- Users may **manually archive a log at any time**
- Archiving is **never automatic**
- The system may recommend archiving but cannot enforce it

### Archive Preconditions

A log can be archived only if:
- It has **no open positions**
- It has **no pending alerts requiring live evaluation**

If blocked, the UI must:
- Explain why
- Offer actions (close positions, pause alerts)

### Archive Effects

When archived, a log becomes:
- Read-only
- Excluded from:
  - Live alerts
  - ML training (default)
  - Daily workflow surfaces

Still included in:
- Retrospectives
- Historical analysis
- Optional ML research scopes

---

## 3. Imports into Archived Logs

### Specification

- **Imports into archived logs are allowed**
- This is a supported and intentional use case

### UX Requirements

When importing into an archived log, show a **non-blocking warning**:

> “This log is archived. Imported trades will not affect live alerts or learning unless the log is reactivated.”

User may proceed without friction.

### Rationale

Supports:
- Historical backfills
- Research datasets
- Strategy autopsies
- Clean separation from live practice

---

## 4. Retire Permanently (Deletion Semantics)

### Specification

- **Hard deletes are not allowed**
- “Retire permanently” means **Frozen + Hidden**

### Retired Log Characteristics

A retired log:
- Is removed from all UI views
- Is excluded from:
  - Alerts
  - ML
  - Imports
  - Workflow
- Is preserved in cold storage for audit/recovery

### Required Friction

To retire a log permanently:
1. Log must already be archived
2. User must:
   - Type the log name to confirm
   - Acknowledge irreversibility
3. Optional but recommended:
   - 7-day grace period before final retirement

### Rationale

- Prevents emotional deletion
- Preserves learning lineage
- Reinforces reflective discipline

---

## 5. Import Targeting Rules

### Default Behavior

- Imports must be explicitly directed to a trade log
- If **only one active log exists**, auto-select it (no prompt)

### Multiple Active Logs

If more than one active log exists:
- User must select the target log
- Display:
  - Log name
  - Description/purpose
  - Active position count
  - ML participation status

---

## 6. Import Recommendation Logic

The system may **suggest**, but never force, creating a new archived log.

### Recommendation Triggers

Recommend creating an archived log when **any** of the following apply:

1. Import date range is entirely historical  
   - Default threshold: > 7 days before today
2. Import date range does not overlap with trades in the selected active log
3. User selects “Historical / Backfill” import mode
4. Import confidence is below threshold (AI-assisted parsing)

### UX Behavior

In the import preview:
- User’s selected target remains unchanged
- Recommendation appears as a suggestion:

> “This import looks historical. Would you like to place it in a separate archived log?”

### User Preferences

Users may configure:
- Always recommend archived logs for historical imports
- Never recommend (manual control)

---

## Summary Table

| Topic | Decision |
|------|---------|
| Total trade logs | Unlimited |
| Active log cap | Soft cap 5, hard cap 10 |
| Archiving | Manual, reversible |
| Import into archived logs | Allowed with warning |
| Deletion | Not allowed |
| Retirement | Frozen + hidden, irreversible |
| Import targeting | Explicit unless single log |
| Recommendations | Suggestive only |

---

## Design Intent

This design ensures:
- Traders can evolve safely
- History is preserved
- ML data hygiene is maintained
- Alerts remain meaningful
- Practice remains intentional

Trade logs are **chapters**, not trash bins.

---

## Instruction for Implementation

This specification is sufficient to proceed with:
- Schema changes
- API design
- Import preview logic
- UI flows
- ML inclusion rules
- Alert scoping

No further clarification is required before implementation.

---