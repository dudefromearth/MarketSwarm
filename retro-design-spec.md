Retrospective UI — Contrast Design Specification

1. Core Contrast Principle

Journal
	•	Immediate
	•	Open-ended
	•	Spatial
	•	Optional
	•	Silent by default

Retrospective
	•	Deliberate
	•	Time-bounded
	•	Guided
	•	Intentional
	•	Structured reflection

The trader should feel that they have stepped into a different mental room.

⸻

2. Entry Contrast: How You Arrive Matters

2.1 Journal → Retrospective Transition

When the user clicks ✨ Retrospective:
	•	The calendar fades away
	•	The editor surface disappears
	•	The background subtly darkens or warms
	•	A short pause (300–500ms) occurs before content appears

This is not a navigation event — it is a transition of posture.

⸻

2.2 Opening State

The first thing shown is not content.

It is orientation.

Example:

We’re going to look back at the past week.
This includes 5 trading days and 12 trades.

Does this period feel right?

Two choices only:
	•	Yes — continue
	•	Change period

No default “Start” button.
No urgency.

⸻

3. Spatial Layout Differences

3.1 Journal Layout (Reference)
	•	Wide
	•	Freeform
	•	Scrollable
	•	Mixed media
	•	You move around inside it

3.2 Retrospective Layout
	•	Narrower column
	•	Centered
	•	Vertical progression
	•	One phase visible at a time
	•	You move through it

Think:

Essay → Walkthrough → Ceremony

⸻

4. Phase-Based Progression (Without Completion Pressure)

4.1 Phase Presentation

Each phase is presented as a lens, not a task.

Example header:

Grounding
How does this period feel, before we talk about numbers?

	•	No checkboxes
	•	No progress bar
	•	No “Next” label

Navigation is:
	•	“Continue”
	•	“Pause”
	•	“Return later”

⸻

4.2 One Phase at a Time

Only the current phase is visible.

Past phases:
	•	Collapsed
	•	Read-only
	•	Quietly accessible

Future phases:
	•	Invisible

This prevents scanning ahead and “answering to get through it”.

⸻

5. Visual Language Contrast

5.1 Color & Tone

Journal:
	•	Neutral
	•	Utility-focused
	•	Editor-first

Retrospective:
	•	Warmer accent (amber / violet)
	•	Softer contrast
	•	Less chrome
	•	Fewer icons

No green/red.
No success/failure colors.

⸻

5.2 Typography
	•	Slightly larger line height
	•	More generous spacing
	•	Fewer controls per screen
	•	Questions feel like text, not UI

⸻

6. Data Presentation: Anchors, Not Metrics

6.1 How Data Appears

Data is:
	•	Inline
	•	Secondary
	•	Contextual

Example:

During this period, you placed 12 trades across 5 sessions.
Your win rate was 58%.

That’s it.

No charts unless explicitly expanded.
No leaderboards.
No comparison.

⸻

6.2 No Editable Data

Unlike the Journal:
	•	You cannot “fix” numbers
	•	You cannot tweak stats
	•	Data is immutable

This reinforces:

“We are looking, not adjusting.”

⸻

7. Vexy’s Role in Retrospective (Contrast to Journal)

7.1 Vexy Is the Guide, Not the Companion

Journal:
	•	Trader initiates
	•	Vexy responds

Retrospective:
	•	Vexy leads the flow
	•	Trader responds

But still:
	•	No advice
	•	No evaluation
	•	No “should”

⸻

7.2 Vexy Voice Shift

Retrospective voice is:
	•	Slower
	•	More spacious
	•	More integrative
	•	Less conversational

Example:

“Before we talk about outcomes, let’s stay with how this period felt.”

⸻

8. Interaction Rules (Critical)

8.1 Writing Is Optional but Expected

Unlike the Journal:
	•	Silence is allowed
	•	But reflection is the point

If the user skips:
	•	No warning
	•	No penalty
	•	Just a quiet acknowledgment

⸻

8.2 Exit Is Always Available

At any time:
	•	“Leave Retrospective”
	•	No save prompt anxiety
	•	Partial reflections are valid

⸻

9. Ending Contrast: No Closure Theater

9.1 No “Complete”

At the end:

This reflection is now part of your record.

Optional:
	•	“Mark excerpts as Playbook material”
	•	“Return to Process”
	•	“Close”

No:
	•	Celebration
	•	Score
	•	Summary judgment

⸻

10. Summary: The Felt Difference

The trader should experience:
	•	Journal → I notice
	•	Retrospective → I understand

Not because the system told them —
but because the structure slowed them down enough to see.

⸻

11. Design North Star

If a user says:

“This didn’t feel like filling out a form.
It felt like taking a step back.”

Then it’s correct.

⸻

