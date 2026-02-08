Journal Daily Synopsis & Vexy Voice Rules

Design Specification (Pre-Retrospective)

This document defines:
	•	The exact shape and behavior of the Daily Synopsis in the Journal
	•	The rules governing Vexy’s voice inside the Journal surface
	•	How both reinforce presence, reflection, and antifragile learning without obligation

This spec explicitly avoids checklist psychology, completion bias, and performance judgment.

⸻

1. Purpose & Doctrine Alignment

Core Doctrine

The Journal is not a place to perform work.
It is a place to notice what occurred.

The Daily Synopsis exists to:
	•	Reduce activation energy
	•	Provide an object for reflection
	•	Allow exit without authorship
	•	Train awareness before articulation

The Journal trains:

“See first. Speak only if something wants to be named.”

⸻

2. The Daily Synopsis (Exact Shape)

2.1 Placement & Hierarchy

Location
	•	Appears above the editor
	•	Below the calendar/date header
	•	Above tags and trade list

Visual Weight
	•	Smaller than the editor
	•	Muted contrast
	•	Read-only
	•	Calm typography (no borders, no cards)

The Synopsis should feel like:

a weather report
not a scorecard

⸻

2.2 Synopsis Structure

The Daily Synopsis is composed of four optional sections, rendered only when data exists.

No section is mandatory.

Daily Snapshot
──────────────
• Activity
• Rhythm
• Risk & Exposure
• Context (optional)

Each section is descriptive only.

⸻

2.3 Section Definitions

A. Activity
Purpose: Anchor the day in observable facts.

Allowed examples:
	•	“5 trades placed”
	•	“2 trades remain open”
	•	“First trade at 9:42, last at 11:18”
	•	“All activity occurred in the morning session”

Forbidden:
	•	Win rate labels
	•	P&L judgment language
	•	“Good / bad day”

⸻

B. Rhythm
Purpose: Surface pacing without interpretation.

Allowed examples:
	•	“Most activity clustered within a 40-minute window”
	•	“Long gaps between trades after 10:30”
	•	“Single-entry day”

Derived from:
	•	Trade timestamps
	•	Gaps between actions

No conclusions. No advice.

⸻

C. Risk & Exposure
Purpose: Reflect exposure shape, not outcome.

Allowed examples:
	•	“Maximum defined risk: $X”
	•	“Peak exposure occurred mid-morning”
	•	“Multiple concurrent positions present”

Forbidden:
	•	“Overexposed”
	•	“Too risky”
	•	“Well managed”

This is a mirror, not a judge.

⸻

D. Context (Optional)
Rendered only when applicable.

Examples:
	•	“CPI released pre-market”
	•	“Friday session”
	•	“Low-liquidity holiday session”
	•	“Weekend — no market activity”

This section is situational awareness, not narrative.

⸻

2.4 Behavior Rules
	•	The Synopsis always appears first
	•	It is visible even if the editor is untouched
	•	It does not imply response is required
	•	It does not disappear when writing begins

⸻

2.5 Empty Day Behavior

If no trades occurred:

No market activity recorded today.

Nothing else.

No prompts. No encouragement. No suggestion.

Silence is correct.

⸻

3. The Editor (Post-Synopsis)

3.1 Editor De-Emphasis Rules
	•	The editor is visually secondary
	•	Cursor is not auto-focused
	•	No placeholder text like “Write here…”

Optional micro-copy (very low contrast, bottom-aligned):

“Nothing needs to be captured today.”

This sentence is critical.
It explicitly grants permission to leave.

⸻

4. Lenses (Formerly Templates)

4.1 Renaming & Framing

Do not call them Templates.

They are Lenses:
	•	Ways of noticing
	•	Not starting points
	•	Not structures to complete

⸻

4.2 Lens Behavior
	•	Lenses are optional
	•	Collapsible
	•	Never auto-applied
	•	Never required to proceed

Selecting a Lens may:
	•	Highlight relevant trades
	•	Insert a faint, italic scaffold (optional)
	•	Or simply adjust emphasis in the Synopsis

No Lens:
	•	Places the cursor
	•	Adds questions by default
	•	Implies obligation

⸻

4.3 Example Lenses
	•	Market Structure
	•	Execution Timing
	•	Risk Shape
	•	Internal State
	•	Presence & Attention

Each Lens is descriptive, not interrogative.

⸻

5. Vexy in the Journal — Speak vs Silence Rules

5.1 Default State: Silence

Vexy is silent by default in the Journal.

Presence is assumed.
Speech is earned.

⸻

5.2 When Vexy May Speak

Vexy may surface at most one reflection when all conditions are met:
	1.	A meaningful pattern exists
	2.	The pattern is non-obvious from the Synopsis alone
	3.	The language can remain purely reflective
	4.	The trader has not already written

Even then:
	•	The reflection is optional
	•	Dismissible
	•	Never persistent

⸻

5.3 Allowed Vexy Language (Journal)
	•	“Noticing…”
	•	“This day shows…”
	•	“A pattern appears…”

Example:

“Most activity occurred within a short window early in the session.”

No advice. No implication. No trajectory.

⸻

5.4 Forbidden Vexy Language (Journal)
	•	“You should…”
	•	“Consider…”
	•	“Improve…”
	•	“Next time…”
	•	“Good / bad”
	•	“Success / failure”

No coaching. No optimization.

⸻

5.5 When Vexy Must Stay Silent

Vexy must not speak when:
	•	No trades occurred
	•	The Synopsis fully explains the day
	•	The trader has already written
	•	The signal is weak or ambiguous
	•	The pattern would require advice to explain

Silence is not a failure state.
Silence is correct.

⸻

6. Journal → Retrospective Boundary

The Journal:
	•	Captures moments
	•	Allows fragments
	•	Encourages presence

The Retrospective:
	•	Connects patterns
	•	Integrates time
	•	Extracts learning

No retrospective language belongs in the Journal.

No:
	•	“This week…”
	•	“Overall…”
	•	“Trend…”

That boundary must remain clean.

⸻

7. System Intent Summary

This design teaches the trader that:
	•	Reflection begins with seeing
	•	Writing is optional
	•	Presence is the practice
	•	Meaning emerges over time, not per day

The system does not reward completion.

It rewards attention.

⸻

If you want, next we can:
	•	Design the Retrospective UI layout so it feels fundamentally different from Journal
	•	Define Retro → Playbook extraction rules (how insight becomes doctrine)
	•	Specify how ML annotations feed retros without narrating them

Just tell me where you want to go next.