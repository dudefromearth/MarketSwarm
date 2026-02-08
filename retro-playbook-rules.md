Retro → Playbook Extraction Specification

Fly on the Wall / The Path

Purpose
Define how retrospective reflection becomes Playbook material without instruction, coercion, or prescription.
Playbooks are discovered, not authored.
The system’s role is to notice, name, and preserve — never to optimize or teach.

⸻

1. Core Doctrine

1.1 Foundational Loop

All extraction follows The Path:

Object → Reflection → Action → Reflection → …

	•	Object: A lived trading experience (trade, decision, behavior, tension)
	•	Reflection: Retrospective articulation (journal, retro phases, silence)
	•	Action: Optional future behavior (not enforced, not suggested)
	•	Loop: Meaning compounds over time

Playbooks exist inside the loop, not at the end of it.

⸻

1.2 What a Playbook Is (and Is Not)

A Playbook IS:
	•	A named pattern the trader has experienced repeatedly
	•	A container for personal meaning
	•	A memory artifact that can be recalled later
	•	A reflection aid, not a rule set

A Playbook IS NOT:
	•	A strategy walkthrough
	•	A checklist
	•	A prescription
	•	A best practice
	•	Something the system invents

If the system explains how to trade, extraction has failed.

⸻

2. Preconditions for Extraction

Playbook extraction is never automatic.
It is offered, not performed.

Extraction may only be suggested when all of the following are true:
	1.	A Retrospective Artifact exists
	2.	At least one of the following phases contains meaningful content:
	•	Patterns
	•	Tensions
	•	Wins
	•	Lessons
	3.	Language indicates recurrence, contrast, or identity-level noticing

2.1 Language Signals (Non-Exhaustive)

Extraction eligibility is raised when the trader uses phrases like:
	•	“This keeps happening…”
	•	“I notice I tend to…”
	•	“Whenever X, I seem to…”
	•	“This felt familiar”
	•	“I wasn’t surprised this time”
	•	“This is different than last week”

Negative signals (do NOT trigger extraction):
	•	“I should…”
	•	“I need to improve…”
	•	“Next time I will…”
	•	“The right thing is…”

⸻

3. Extraction Triggers

Extraction can be proposed via three pathways.

3.1 Manual Marking (Explicit)
	•	User marks a journal entry, retro response, or note as:
	•	“Playbook material”
	•	“Worth keeping”
	•	This immediately opens an Extraction Preview (see Section 6)

3.2 Retrospective Emergence (Implicit)
	•	During a Retrospective session, Vexy may surface a quiet observation:

“This theme appeared in more than one place today.”

No naming. No suggestion. No CTA.

3.3 ML-Supported Confirmation (Deferred)
	•	ML never initiates extraction on its own
	•	ML may reinforce an already-noticed pattern:
	•	“This pattern has appeared in 4 of the last 6 retrospectives.”
	•	ML cannot name Playbooks
	•	ML cannot suggest actions

⸻

4. Playbook Candidate Shape (Minimal)

A Playbook Candidate is a draft artifact, not yet a Playbook.

4.1 Required Fields

{
  "source_type": "retrospective | journal",
  "source_ids": ["uuid"],
  "candidate_title": "string (tentative, editable)",
  "pattern_summary": "string",
  "supporting_quotes": ["string"],
  "linked_trades": ["trade_id"],
  "confidence": "low | emerging | clear",
  "created_at": "timestamp"
}

4.2 Language Rules
	•	Use trader’s own words wherever possible
	•	No imperative verbs
	•	No advice
	•	No optimization framing
	•	No “next time” language

⸻

5. Vexy’s Role (Critical)

Vexy never authors Playbooks.

Vexy may:
	•	Reflect
	•	Name gently
	•	Ask permission
	•	Remain silent

5.1 Allowed Vexy Language

Examples:
	•	“This feels like something you’ve noticed before.”
	•	“There’s a consistency here.”
	•	“This may be something worth keeping.”
	•	“No need to decide now.”

5.2 Forbidden Vexy Language
	•	“You should turn this into a Playbook.”
	•	“This is a strategy.”
	•	“This will improve your results.”
	•	“Next time, do X.”

If uncertain, Vexy must stay silent.

⸻

6. Extraction Preview (User-Facing)

When extraction is proposed, the user is shown a Preview, not a form.

6.1 Preview Characteristics
	•	Read-only by default
	•	Soft edges, low contrast
	•	No buttons labeled “Create”, “Save”, or “Finish”

6.2 Available Actions
	•	Name it (optional)
	•	Leave it unnamed
	•	Dismiss
	•	Save quietly

Dismissal leaves no trace.

⸻

7. From Candidate → Playbook

A Candidate becomes a Playbook only when the user explicitly preserves it.

7.1 Promotion Rules
	•	No minimum length
	•	No required structure beyond:
	•	Name (optional)
	•	One reflective statement
	•	Playbooks can be revised, merged, or archived later

7.2 First-Class Incompleteness

An empty Playbook is valid.

Silence is valid.

A title without content is valid.

⸻

8. Persistence Model

8.1 Playbook Artifact

{
  "playbook_id": "uuid",
  "title": "string | null",
  "origin": "retro | journal",
  "created_from": ["candidate_id"],
  "entries": [
    {
      "timestamp": "...",
      "content": "string",
      "linked_trades": []
    }
  ],
  "ml_observed": true | false,
  "archived": false
}

8.2 Immutability
	•	Original extraction context is immutable
	•	Additions are append-only
	•	No overwriting history

⸻

9. What This Enables (Intentionally)

This system trains traders to:
	•	Notice patterns without rushing to fix them
	•	Preserve meaning without formalizing it too early
	•	Develop identity-level awareness
	•	Build Playbooks as personal memory, not doctrine

⸻

10. What This Explicitly Avoids
	•	Teaching strategies
	•	Enforcing discipline
	•	Optimizing performance
	•	Gamifying reflection
	•	Turning wisdom into templates

⸻

11. Success Criteria

You’ll know this worked when:
	•	Traders say “I didn’t realize I had a Playbook until I did”
	•	Playbooks differ wildly between users
	•	Some Playbooks are one sentence long
	•	Silence is common — and accepted

⸻

Final Doctrine Check
If the system makes traders feel smarter, faster, or better — it failed.
If it helps them notice more clearly — it succeeded.

⸻

