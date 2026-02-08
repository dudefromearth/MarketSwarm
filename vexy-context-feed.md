Vexy Context Feed — Routine Level

Daily Log Health Analyzer & Context Ingestion Spec

This document defines how Trade Log lifecycle intelligence is surfaced into Vexy at the Routine level, enabling pre-market orientation, gentle coaching, and process reinforcement without interrupting execution.

⸻

1. Purpose

The Routine context feed exists to:
	•	Give traders situational awareness before the trading day begins
	•	Surface log hygiene, ML participation, and process drift
	•	Reinforce good habits (archiving, consolidation, reflection)
	•	Allow Vexy to act as a coach, not a blocker

This feed is advisory only and is never used to block actions.

⸻

2. Scheduled Job — log_health_analyzer

Job Overview

Property	Value
Job Name	log_health_analyzer
Schedule	Daily — 05:00 ET
Scope	Per user
Output	Vexy Routine Context


⸻

Inputs

For each user, the job queries:
	•	Trade logs (active + archived)
	•	Positions
	•	Alerts
	•	ML inclusion flags
	•	Imports
	•	Trade activity timestamps

⸻

Metrics Computed (Per Log)

{
  "log_id": "uuid",
  "log_name": "string",
  "lifecycle_state": "active | archived | retiring",
  "days_since_last_trade": 21,
  "days_since_last_import": 45,
  "total_trades": 842,
  "open_positions": 0,
  "pending_alerts": 0,
  "ml_included": false,
  "created_at": "2025-11-01",
  "last_trade_at": "2026-02-01"
}


⸻

3. Signal Derivation Rules

Signals are derived, not raw metrics.
Only meaningful insights are forwarded to Vexy.

Example Signal Types

Signal Type	Trigger
log_inactive	No trades ≥ 14 days
log_stale_imports	No imports ≥ 30 days
ml_excluded_active_log	Active log with ML disabled
log_ready_for_archive	No positions + no alerts
approaching_active_log_cap	≥ 4 active logs
retirement_pending	Log retiring within 3 days


⸻

Signal Object Schema

{
  "type": "log_inactive",
  "severity": "low | medium | high",
  "value": 21,
  "message": "Log has been inactive for 21 days"
}


⸻

4. Vexy Context Ingestion API

Endpoint

POST /api/vexy/context/log-health


⸻

Payload Schema

{
  "user_id": 123,
  "routine_date": "2026-03-03",
  "logs": [
    {
      "log_id": "uuid",
      "log_name": "0DTE Feb Experiments",
      "signals": [
        {
          "type": "log_inactive",
          "severity": "low",
          "value": 21,
          "message": "No activity in 3 weeks"
        },
        {
          "type": "ml_excluded_active_log",
          "severity": "medium",
          "message": "Trades here are not contributing to learning"
        }
      ]
    }
  ]
}


⸻

Guarantees
	•	Context is append-only
	•	No destructive updates
	•	Idempotent per (user_id, routine_date)

⸻

5. Vexy Behavior — Routine Level

Where This Appears
	•	Routine Drawer
	•	Pre-Market Briefing
	•	Vexy Narrative Panel
	•	Optional Daily Digest

⸻

Tone & Style
	•	Calm
	•	Observational
	•	Non-judgmental
	•	Coach-like
	•	Never urgent

⸻

Example Vexy Messages

Inactive Log
“You have a log that hasn’t been used in three weeks.
If it’s no longer part of your process, this might be a good time to archive it.”

ML Exclusion
“Some of your active trades aren’t feeding the learning system.
Including them helps refine future strategies.”

Archive Opportunity
“One of your logs has no open positions or alerts.
Archiving it could simplify your workspace.”

Cap Awareness
“You’re approaching your active log limit.
Consolidation now prevents friction later.”

⸻

6. Relationship to Other Systems

What This Feed Does
	•	Informs Vexy’s Routine narrative
	•	Seeds Process-level reflections
	•	Improves import recommendations
	•	Shapes coaching prompts

What It Does NOT Do
	•	Does not emit alerts
	•	Does not block actions
	•	Does not modify logs
	•	Does not affect execution

⸻

7. Lifecycle Interaction Summary

Log State	Included in Routine Context
Active	✅ Yes
Archived	✅ Yes (low priority)
Retiring	✅ Yes (highlighted)
Retired	❌ No


⸻

8. Failure & Fallback Behavior
	•	If job fails → no Routine insights for that day
	•	If endpoint fails → Vexy proceeds without log context
	•	No retries during market hours

⸻

9. Implementation Checklist
	•	Implement log_health_analyzer cron job
	•	Add signal derivation layer
	•	Create /api/vexy/context/log-health endpoint
	•	Store Routine context per day
	•	Render insights in Routine Drawer
	•	Add Vexy narrative templates

⸻

10. Design Principle

Routine is where behavior is shaped, not enforced.
Vexy’s role is to gently align today’s actions with long-term mastery.

