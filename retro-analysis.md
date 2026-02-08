# Retrospective Analysis Framework  
## Path-Aligned Specification (v1.0)

**Surface:** Process Drawer  
**Owner:** Vexy (Antifragile Decision Support OS)  
**Cadence:** Periodic (default weekly)  
**Doctrine:** Object → Reflection → Action → Loop

---

## 1. Purpose

The Retrospective is not a report, a scorecard, or a coaching session.

It is a **structured reflection space** where:
- Experience is named
- Patterns are surfaced
- Tension is observed without judgment
- Intentions arise naturally

The Retrospective exists to **convert experience into wisdom**, not to improve metrics directly.

---

## 2. Position in The Path

The Retrospective sits at the far right of the Fly on the Wall flow:

Routine → Analysis → Selection → Action → Process → **Retrospective**

It is:
- Backward-looking
- Integrative
- Non-urgent
- Optional, but encouraged

No actions are required to “complete” a retrospective.

Silence is acceptable.

---

## 3. Retrospective Structure (Canonical)

Defined in `retro_framework.py`.

The Retrospective is composed of **seven phases**, always presented in this order.

| Phase       | Purpose                         | Example Prompts |
|------------|----------------------------------|-----------------|
| Grounding  | Establish presence               | “What’s the first word that comes to mind about this period?” |
| Review     | Anchor to what happened          | “Your win rate was X%. Does that match how the week felt?” |
| Patterns   | Surface recurring themes         | “When did you feel most aligned with your process?” |
| Tensions   | Observe friction without blame   | “Where did you feel resistance or override your process?” |
| Wins       | Reinforce what worked            | “Which trade best reflected your intentions?” |
| Lessons    | Extract insight                  | “What did you learn about yourself?” |
| Intentions | Set direction (not goals)        | “What feels worth paying attention to next?” |

### Ordering is mandatory  
Phases must not be skipped or reordered.

---

## 4. Period Selection

At the start of a Retrospective, Vexy proposes a **default period** and asks for consent.

### Supported Periods

- Last week (default)
- Last two weeks
- Custom date range
- “Since [date]”
- Partial period (“this week so far”)

### Opening Language (Required Pattern)

> “By default, we’ll look at the past week — approximately 5 trading days and 12 trades.  
> Does this period feel right, or would you like to adjust it?”

No assumption of correctness.  
No pressure to proceed.

---

## 5. Data Inputs (Read-Only)

The Retrospective may reference:

- Trade counts
- Win/loss statistics
- Strategy usage
- Overrides
- Alerts triggered
- ML findings (if enabled)

### Rules

- Data is **reflective**, never evaluative
- Numbers are anchors, not conclusions
- No optimization language (“improve”, “increase”, “fix”)

Example allowed phrasing:
> “You placed fewer trades this week than last. How does that land?”

---

## 6. Vexy Voice Rules (Retrospective Mode)

Retrospective uses **PROCESS_BASE** posture with additional constraints.

### Must Do

- Name observations neutrally
- Invite reflection, not action
- Allow pauses and silence
- Use past-tense continuity language

### Must Never Do

- Give advice
- Prescribe behavior
- Optimize strategies
- Praise or criticize performance

Forbidden language includes:
- “You should”
- “Next time”
- “Better / worse”
- “Mistake”
- “Fix this”

---

## 7. Tier Interaction

### Observer
- Guided prompts only
- No synthesis across weeks
- No pattern generalization

### Activator
- Light pattern surfacing
- Single-period focus

### Navigator
- Cross-period themes
- Identity-level reflections
- Playbook references allowed (by name only)

### Admin
- Full introspection
- System and habit analysis

Tier affects **depth**, not tone.

---

## 8. Output & Persistence

### Retrospective Session

Each Retrospective produces:
- Timestamp
- Period reviewed
- Phase responses (free text)
- Optional tags (user-applied)
- Optional linked trades/logs

### Storage

- Persisted as a Retrospective artifact
- Immutable once closed
- Re-readable but not editable

No scoring.  
No grading.  
No completion badge.

---

## 9. UI Integration Rules

- Lives in the Process drawer
- Visually distinct from Daily Process
- No progress indicators
- No “Complete” or “Finish” CTA
- Exit at any time without warning

Transitions should include:
- Soft fade-in
- Gentle spacing
- No accordion behavior

---

## 10. Relationship to Playbooks

Retrospectives **feed Playbooks**, but do not teach them.

- Insights may be tagged for later Playbook creation
- Patterns may suggest Playbook relevance
- No automatic Playbook updates

The Retrospective is the **tip of the spear** for wisdom creation.

---

## 11. Success Criteria

This framework is successful when:

- Users linger without rushing
- Silence feels allowed
- Insights emerge without prompting
- No one feels judged
- Retrospectives feel lighter than trading days

If users say:
> “I understand myself better”

…it’s working.

---

## 12. Non-Goals (Explicit)

The Retrospective is NOT:
- A performance review
- A coaching session
- A habit tracker
- A productivity tool
- A place to plan trades

It is a mirror.

---

## Closing Doctrine

Reflection cannot occur without an object.  
The object is experience.  
The mirror is Vexy.  
The loop is life.

This framework must protect that loop.