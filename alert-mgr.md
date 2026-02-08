# Alert Manager — Unified Workflow Awareness System
**Design Spec + Implementation Plan (v1)**  
Fly on the Wall (FOTW) • Left-to-Right Process Integration • Vexy as Meta-Alert

---

## 0) Executive Summary

The Alert Manager is **not** a “price alerts” feature. It is the **awareness layer** that spans the entire FOTW workflow, left-to-right:

**Routine → Structure → Selection → Analysis → Action → Process**

Alerts are created **prompt-first** (natural language as the universal entry point), then compiled into evaluators (threshold, rules, AI, workflow triggers). Alerts can be tied to: market state, position state, user actions, and process steps.

**Vexy is the meta-alert system**: she does not replace alerts; she synthesizes them into *coherent narrative*, detects alert fatigue, detects clusters/contradictions, and provides “what matters right now” context.

---

## 1) Goals and Non-Goals

### Goals
- Provide a **single alert system** that supports:
  - market thresholds (price, levels, time)
  - position/risk thresholds (PnL, Greeks, risk graph events)
  - discipline rules (daily loss, max trades, edge guardrails)
  - workflow triggers (journal after close, routine checklist)
  - AI alerts (“this resembles a prior failure pattern”)
- Make alert creation **prompt-first** and deterministic in execution.
- Integrate alerts across the **left-to-right UI** and **service-layer apps**.
- Provide real-time updates via SSE.
- Enable Vexy meta synthesis: **summaries, clustering, drift, fatigue control**.

### Non-Goals (v1)
- Fully autonomous trade execution.
- Complex multi-step automation chains (“if A then B then C”) beyond basic triggers.
- Heavy ML-driven alert personalization (can be added later).

---

## 2) Core Concepts

### 2.1 Alert Definition vs Alert Evaluation (Hard Separation)
**Alert Definition** is a persistent, declarative object:
- The *prompt* (canonical)
- scope (position/symbol/portfolio/workflow)
- severity ladder
- schedule rules
- owner (user / playbook / system)

**Alert Evaluation** is a runtime interpretation:
- fast checks (price, time, PnL)
- slow checks (AI / pattern / semantic)
- event checks (trade closed, routine incomplete)

This separation is required for:
- replay and retrospectives
- versioned prompt parsing
- deterministic behavior

---

## 3) Alert Types and Scope Model

### 3.1 Scope
| Scope | Description | Examples |
|------:|-------------|----------|
| `position` | Tied to a specific position | “Alert if this butterfly hits +3R” |
| `symbol` | Tied to market symbol | “Alert when SPX breaks 6000” |
| `portfolio` | Aggregate posture | “Warn if delta > +50” |
| `workflow` | Process triggers | “Remind me to journal after closing a trade” |
| `behavioral` | User behavior patterns | “Notice if I revenge trade after loss” |

### 3.2 Severity Ladder
| Severity | Meaning | UI Behavior |
|---------:|---------|-------------|
| `inform` | passive awareness | badge / subtle toast |
| `notify` | important signal | toast + log |
| `warn` | risk increasing | persistent banner + acknowledgement |
| `block` | policy violation | prevent action + override w/ reason |

**Rule**: “block” never executes trades; it blocks UI actions unless explicitly overridden.

---

## 4) System Architecture (Service-Level)

### 4.1 Services
- **Alert Manager Service** (new, service-level app)
  - stores alert definitions
  - compiles prompts into evaluators
  - runs evaluation loops
  - emits events
  - persists alert history
- **SSE Gateway** (existing)
  - delivery-only streaming to clients
- **Vexy AI Service** (existing/adjacent)
  - generates narratives, clustering, summaries
  - does *not* evaluate real-time conditions (unless asked)
- **Integrating Apps**
  - Risk Graph service
  - TradeLog-Journal service
  - Dealer Gravity service
  - Trade Selector / Heatmap services

### 4.2 Data Boundaries
- **DB**: canonical source for definitions + history + state
- **Redis**: delivery-only pub/sub for SSE events (and optional short-lived caches)
- **Disk**: pipeline artifacts remain in their respective services (Dealer Gravity etc.)

---

## 5) Data Model (v1)

### 5.1 Tables (conceptual)
**alerts**
- `id`, `user_id`
- `title` (optional)
- `prompt` (canonical)
- `scope` enum
- `severity` enum (default)
- `status` enum: active/paused/archived
- `target_ref` JSON (position_id, symbol, portfolio, workflow keys)
- `schedule` JSON (active hours, DND, cooldown)
- `created_at`, `updated_at`

**alert_interpretations** (versioned prompt parsing)
- `id`, `alert_id`
- `parser_version`, `interpreted_type` (threshold/rule/workflow/ai/custom)
- `evaluator_spec` JSON (compiled config)
- `created_at`

**alert_events** (history)
- `id`, `user_id`, `alert_id`
- `event_type` (triggered/acknowledged/dismissed/blocked/overridden)
- `severity_at_event`
- `payload` JSON (condition values, context snapshot)
- `created_at`

**alert_overrides** (for block overrides)
- `id`, `user_id`, `alert_id`
- `reason` text
- `created_at`

---

## 6) API + SSE Contracts (v1)

### 6.1 REST Endpoints (Alert Manager Service)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/alerts` | list alerts |
| POST | `/api/alerts` | create (prompt-first) |
| GET | `/api/alerts/:id` | get alert |
| PATCH | `/api/alerts/:id` | update alert |
| DELETE | `/api/alerts/:id` | archive/delete |
| POST | `/api/alerts/:id/pause` | pause |
| POST | `/api/alerts/:id/resume` | resume |
| GET | `/api/alerts/:id/history` | event history |
| POST | `/api/alerts/:id/ack` | acknowledge |
| POST | `/api/alerts/:id/dismiss` | dismiss |
| POST | `/api/alerts/:id/override` | override block (requires reason) |

### 6.2 SSE Channel
`GET /sse/alerts`

**Event types**
- `alert_created`
- `alert_updated`
- `alert_paused`
- `alert_triggered`
- `alert_acknowledged`
- `alert_dismissed`
- `alert_blocked`
- `alert_override_logged`
- `alert_digest` (from Vexy meta synthesis; optional v1)

---

## 7) Evaluation Engine (How Alerts Actually Fire)

### 7.1 Evaluator Classes
**Fast evaluators** (poll or event-driven)
- price threshold / level proximity
- time-based (“at 9:15 remind me…”)
- position PnL / Greeks thresholds
- portfolio aggregate thresholds

**Event-driven evaluators**
- trade closed → workflow triggers
- position created → attach position-scoped alerts
- risk graph scenario saved → rules applied
- routine drawer opened → routine prompts

**Slow evaluators (AI)**
- “behaving differently than entry”
- “resembles last week’s failure”
- “this violates my playbook intent”
- “alert fatigue / cluster detection”

### 7.2 Cooldowns and Spam Control
Each alert has:
- `cooldown_seconds` (default by severity)
- optional `max_triggers_per_session`
- optional `quiet_hours`

---

## 8) Left-to-Right Integration Spec (UI + Service Touchpoints)

This section answers: **how the alert system integrates across Routine → Structure → Selection → Analysis → Action → Process**.

### 8.1 Persistent Process Bar Integration
- When any alert triggers, the process bar can show a subtle indicator:
  - small dot/halo on the current phase label
- Phase is **not** changed by alerts; alerts are awareness, not navigation.

---

### 8.2 Routine Drawer (Left)
**Primary integration: workflow + readiness alerts**
- Routine alerts appear as:
  - “Open Loops” items (missing journaling, open positions, unresolved overrides)
  - scheduled reminders (check VIX regime, check calendar)
- Entry event:
  - When routine drawer opens, UI calls Vexy for a Routine briefing (separate endpoint)
  - Alert Manager can also emit workflow alerts if routine steps are incomplete

**Routine-specific surfaces**
- `Routine Alerts` list (compact)
- quick actions: acknowledge / snooze

---

### 8.3 Dealer Gravity (Structure)
**Primary integration: structural awareness alerts**
- Alerts can reference Dealer Gravity artifacts:
  - “Notify if spot approaches a Crevasse”
  - “Warn if structure shifts from memory to instability”
  - “Tell me when this structural line becomes active”
- Dealer Gravity emits artifact updates; Alert Manager subscribes (or is called) to re-evaluate relevant alerts.

**Key requirement**
- If Dealer Gravity structural analysis changes, alerts dependent on those levels must re-evaluate and new alert triggers may occur.

---

### 8.4 Trade Selector / Heatmap (Selection)
**Primary integration: guardrails + edge validation**
- Alerts can be attached to selection context:
  - “Warn if I’m selecting outside my volatility regime width rules”
  - “Inform if this idea conflicts with my intent”
- Alert Manager can provide “soft constraints” without blocking selection.

---

### 8.5 Risk Graph (Analysis)
**Primary integration: scenario-based risk awareness**
- Risk Graph should be able to:
  - create alerts from analysis state (“Alert if breakeven threatened”)
  - bind alerts to a position candidate or to an executed position
  - receive alert triggers as subtle UI events (no clutter)

**Backdrop integration (separate requirement)**
- Risk Graph displays Dealer Gravity backdrops (VP / GEX / structural lines) as selectable background.
- Alerts that reference structural lines should align with risk graph scale and show only via subtle markers (not overlays that dominate).

---

### 8.6 Trade Execution / Simulator (Action)
**Primary integration: actionable risk thresholds + discipline**
- Alerts here are allowed to be stronger:
  - warn / block (daily loss, max trades, position constraints)
- When user attempts a blocked action:
  - show block dialog
  - allow override with reason
  - log override event

---

### 8.7 TradeLog / Journal / Retrospective (Process) (Right)
**Primary integration: reflection triggers + learning loop**
- Workflow alerts:
  - “Journal after closing”
  - “Complete a retrospective after large swing”
- Alerts become structured prompts in the journal:
  - auto-insert “why this alert existed” (optional)
  - link to alert history context

---

## 9) Vexy as Meta-Alert System

### 9.1 Vexy’s Role
Vexy does not replace alerts; she:
- summarizes what triggered
- clusters multiple alerts into one narrative
- detects contradictions (“two alerts imply opposing posture”)
- detects fatigue (too many alerts)
- gives the operator a calm “what matters now” briefing

### 9.2 Vexy Inputs
- recent `alert_events` (last N minutes)
- current phase (Routine/Structure/…)
- user intent (if set)
- open positions count (optional)
- “critical” alerts active (warn/block)

### 9.3 Vexy Outputs
- `alert_digest` narrative: 3–6 short paragraphs
- optional: “top 3 attention points”
- optional: “one suggested question” (reflection prompt, not action)

### 9.4 Vexy Guardrails
- never recommends trades
- never escalates urgency
- calm tone increases as conditions get chaotic
- does not spam; digests are rate-limited

### 9.5 Vexy Endpoints (Recommended)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/vexy/routine-briefing` | pre-market orientation while Routine open |
| POST | `/api/vexy/alert-digest` | meta synthesis of recent alert activity |
| POST | `/api/vexy/process-digest` | end-of-day reflective summary (future) |

---

## 10) UI Spec (Minimal v1)

### 10.1 Global Alert Surfaces
- Header icon (badge count for warn/block only)
- Toasts:
  - inform/notify: ephemeral
  - warn: persistent until acknowledged
- Alert Center Panel:
  - accessible from anywhere
  - shows active alerts + recent events
  - includes search and filters

### 10.2 Contextual Surfaces
- Routine drawer: “Routine Alerts” + Open Loops
- Dealer Gravity: alert creation from structural features
- Risk Graph: alert creation from scenario thresholds
- Process drawer: prompts + unresolved alert overrides

---

## 11) Implementation Plan (Phased)

### Phase 1 — Foundations (1 week)
- Implement Alert Manager service skeleton
- DB tables: `alerts`, `alert_interpretations`, `alert_events`
- CRUD endpoints
- SSE channel `/sse/alerts`
- Minimal UI: Alert Center + basic toast notifications

**Exit criteria**
- user can create/edit/pause alerts
- events persist and stream to clients

---

### Phase 2 — Prompt Parsing + Compilation (1–2 weeks)
- Implement prompt parser (rule-based + AI-assisted)
- Persist `alert_interpretations` versions
- Compile to evaluator specs
- Add cooldowns and schedules

**Exit criteria**
- prompt-first creation reliably maps to evaluator specs
- re-parsing produces new interpretation version without losing history

---

### Phase 3 — Fast Evaluators (1–2 weeks)
- Price/time evaluators
- Position PnL/Greeks evaluators (via Risk Graph or Position API data)
- Portfolio posture evaluators (simple aggregates)

**Exit criteria**
- alerts can trigger off live data and stream events

---

### Phase 4 — Workflow Evaluators (1–2 weeks)
- Trade closed → journal prompt alert
- Routine incomplete → remind alert
- Block/override path implemented
- Process drawer integration for workflow prompts

**Exit criteria**
- “journal after close” works end-to-end
- overrides are logged and visible in Process

---

### Phase 5 — Cross-App Integrations (2–3 weeks)
- Dealer Gravity structural alerts integration
- Risk Graph scenario alerts integration
- Trade Selector selection guardrails integration

**Exit criteria**
- alerts can be authored within those tools and tracked centrally

---

### Phase 6 — Vexy Meta Alerts (1–2 weeks)
- Implement `/api/vexy/alert-digest`
- Add digest UI surface:
  - shown in Routine/Process contexts
  - optionally collapsible
- Add clustering and fatigue control

**Exit criteria**
- Vexy can summarize alert activity without being spammy
- digests are calm, descriptive, non-prescriptive

---

## 12) Determinism & Debuggability (Must-Haves)

- Every triggered alert event includes:
  - evaluator type
  - measured values at trigger time
  - reference state if relevant
  - interpretation version
- Override reasons are mandatory for block overrides
- Ability to replay alert evaluation against historical snapshots (future-friendly)

---

## 13) Future Enhancements (Post-v1)
- Behavioral pattern detection (revenge trading) with strong guardrails
- Alert “why” field to strengthen learning loop
- Personalization (regime-based sensitivity)
- Alert templates (shareable across users)
- ML-driven “alert relevance scoring” (careful; avoid overreach)

---

## 14) Summary

This system turns alerts into:
- a **process coach**
- a **risk awareness layer**
- a **learning trigger engine**
- a **meta narrative (Vexy) that prevents noise and creates coherence**

It is an unusually powerful foundation because it:
- keeps prompt-first creation
- preserves deterministic execution
- spans the left-to-right architecture cleanly
- uses Vexy as synthesis, not authority

---