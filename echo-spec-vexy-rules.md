# Process-Level Echo  
## Design Specification & Vexy Narrative Language Rules

---

## 1. Purpose

**Process-Level Echo** is a lightweight narrative reflection mechanism that creates continuity between the **Routine phase** and the **Process phase** of the Fly on the Wall (FOTW) system.

It allows Vexy to:
- Reference signals surfaced during Routine
- Observe what actually changed during the trading session
- Reflect those changes back to the user **without judgment, enforcement, or interruption**

This is **not** an alert system, **not** analytics, and **not** journaling.

It is narrative coherence.

---

## 2. Core Principle

> **Observe → Compare → Echo (gently)**

Process-Level Echo never:
- Blocks actions
- Interrupts workflow
- Requires configuration
- Persists new state

It only connects what the user already saw with what actually happened.

---

## 3. Scope (Strict)

### Included
- Read-only analysis
- Narrative output only
- Uses existing Routine context
- Runs when Process mode is entered or synthesized

### Explicitly Excluded
- No new database tables
- No new scheduled jobs
- No alerts
- No UI badges or warnings
- No journal writes

---

## 4. Architectural Overview

### Existing Infrastructure Used
- `get_routine_context(user_id)`
- Current log state (via existing log queries)
- Process narrative synthesis pipeline (Vexy)

### No New Services Required

---

## 5. Data Flow

### Step 1 — Routine Context Capture (Already Exists)

During Routine mode, Vexy surfaces signals such as:
- Inactive logs
- Archived logs
- ML inclusion status
- Pending alerts
- Structural notes

Returned via:
GET /api/vexy/routine-context
---

### Step 2 — Process Mode Entry

When **Process mode** initializes its narrative:

1. Call `get_routine_context(user_id)`
2. Fetch current log state
3. Perform a lightweight state diff

---

## 6. Delta Detection Logic

### Comparison Axes

| Axis | Example |
|-----|--------|
| Lifecycle | inactive → active |
| Archive state | archived → active |
| ML inclusion | excluded → included |
| Activity | no trades → traded |
| Alerts | pending → cleared |

---

### Meaningful Delta Criteria

A delta is meaningful if:
- It represents **user action**
- It changes operational posture
- It matters for retrospective reflection

Not meaningful:
- Timestamp changes
- Incremental trade counts
- Background imports with no behavior change

---

## 7. Echo Emission Rules

### When to Emit
- At least one meaningful delta exists
- Maximum **1–2 echoes per Process session**
- Suppressed if no deltas

### When Not to Emit
- Routine was not opened
- Process session is very brief
- Delta already echoed earlier in session

---

## 8. Example Echo Types

### Activation Echo
> “This morning you noted this log was inactive. Today’s trade reactivated it.”

### Confirmation Echo
> “You traded exactly within the log you set up during Routine.”

### Hygiene Echo
> “The alerts you flagged this morning were cleared before the session ended.”

### Stability Echo
> “Nothing materially changed from your morning setup — steady execution.”

---

## 9. Output Format (Internal)

Narrative fragment only (not an alert):

```json
{
  "type": "process_echo",
  "category": "continuity",
  "message": "This morning you noted Log X was inactive. Today’s trade reactivated it.",
  "source": ["routine_context", "current_log_state"],
  "confidence": "high"
}
```

⸻

10. Vexy Narrative Language Rules

Process-Level Echo Edition

⸻

10.1 Tone Rules

Vexy must sound:
	•	Observational
	•	Calm
	•	Neutral
	•	Non-directive

Vexy must not sound:
	•	Evaluative
	•	Corrective
	•	Instructive
	•	Emotional

⸻

10.2 Language Constraints

Allowed
	•	“you noted”
	•	“you flagged”
	•	“this morning”
	•	“today”
	•	“remained”
	•	“changed”
	•	“reactivated”
	•	“carried through”

Forbidden
	•	“should”
	•	“missed”
	•	“failed”
	•	“good / bad”
	•	“mistake”
	•	“warning”
	•	“risk”

⸻

10.3 Sentence Structure

Preferred pattern:

Reference → Observation → Outcome

Example:

“This morning you flagged Log A as inactive. Today’s trade reactivated it.”

Avoid:

“You reactivated an inactive log.”

⸻

10.4 No Advice Rule

Process-Level Echo never includes:
	•	Suggestions
	•	Recommendations
	•	“Next time” language
	•	Optimization hints

Those belong to alerts, retrospectives, or ML insights.

⸻

10.5 Frequency Control
	•	One echo is better than many
	•	Silence is preferable to redundancy
	•	If uncertain, do not echo

⸻

11. Relationship to Future Systems

Process-Level Echo is the foundational pattern for:
	•	Retrospective auto-seeding
	•	Alert hygiene feedback
	•	ML-driven behavioral insights

Those systems may persist data or prompt users.
Process-Level Echo never will.

⸻

12. Success Criteria

Success:
	•	“That felt accurate.”
	•	“That made the day feel connected.”
	•	“I didn’t feel interrupted.”

Failure:
	•	“Why is it telling me this?”
	•	“That felt like an alert.”
	•	“That felt judgmental.”

⸻

13. Summary

Process-Level Echo is:
	•	Small
	•	Quiet
	•	Precise
	•	Process-first

It turns Routine into something that matters later, without turning Process into a lecture.