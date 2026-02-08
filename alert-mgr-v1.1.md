# Fly on the Wall – Alert Manager v1.1  
## Design Specification & Implementation Plan

---

## 1. Purpose & Philosophy

The Alert Manager is **not a price alert system**.

It is a **situational awareness and process reinforcement engine** designed to:
- Support discretionary trading
- Reinforce discipline and routine
- Surface structural risk early
- Reduce cognitive overload
- Enable learning through reflection

Alerts exist to **support judgment**, not replace it.

---

## 2. Core Design Principles

1. **Prompt-First**  
   Alerts are created via natural language prompts.  
   Alert “types” are compilation targets, not user-facing concepts.

2. **Process-Aware**  
   Alerts integrate across the full Fly on the Wall workflow:
   - Routine (prep)
   - Structure (Dealer Gravity)
   - Selection (Heatmap)
   - Analysis (Risk Graph)
   - Action (Execution / Simulation)
   - Process (Journal, Retrospective)

3. **Severity Escalation (Not Binary)**  
   Alerts move through a spectrum:
   - Inform
   - Notify
   - Warn
   - Block (with override)

4. **Trader Sovereignty**  
   Alerts may block UI actions, but **never execute trades**.
   All blocks are overrideable with reason (logged).

5. **Learning Loop**  
   Alerts feed retrospectives, journaling, and Vexy coaching.

---

## 3. Alert Lifecycle
CREATED → WATCHING → UPDATE → WARN → ACCOMPLISHED | DISMISSED | OVERRIDDEN
- **Watching**: Conditions monitored
- **Update**: Informational context change
- **Warn**: Action-worthy condition
- **Block**: Prevents UI action until acknowledged or overridden
- **Accomplished**: Intent satisfied (not merely condition ended)

---

## 4. Alert Scope

Every alert declares its scope explicitly:

| Scope          | Description |
|----------------|-------------|
| `position`     | Bound to a specific position |
| `symbol`       | Applies to an instrument (e.g. SPX) |
| `portfolio`   | Aggregated exposure / risk |
| `behavioral`  | Trader behavior patterns |
| `workflow`    | Routine / journaling / process |

---

## 5. Alert Binding Model

Alerts may be created **before** their target exists.

| Binding State | Description |
|---------------|-------------|
| `unbound` | No target yet |
| `symbol_bound` | Bound to symbol |
| `position_bound` | Bound to position |
| `portfolio_bound` | Portfolio-wide |
| `workflow_bound` | Process-driven |

### Binding Policies
- `manual`
- `auto_on_next_position`
- `auto_on_matching_symbol`

---

## 6. Alert Definition vs Evaluation (Critical Separation)

### Alert Definition (Stable, Declarative)
- Prompt text
- Scope
- Severity policy
- Binding policy
- Cooldown & budget
- Origin tool
- Process phase

### Alert Evaluation (Dynamic)
- Threshold evaluators (price, delta, gamma)
- Time evaluators
- Event evaluators (trade closed, journal missing)
- AI evaluators (pattern, regime, drift)
- Meta evaluators (fatigue, clustering)

Alerts are **declarative objects**; evaluators interpret them.

---

## 7. Severity Levels

| Level | Behavior |
|------|----------|
| Inform | Passive awareness |
| Notify | Draw attention |
| Warn | Requires acknowledgment |
| Block | Prevents action; override allowed |

### Overrides
- Require reason
- Logged
- Visible in retrospectives

---

## 8. Fatigue Control (Mechanical, Not AI-Only)

### Required Controls (v1)
- **Cooldown**: minimum time between triggers
- **Budget**: max alerts per severity per window
- **Coalescing**: repeated triggers merged into one event

Vexy synthesizes **after** these controls.

---

## 9. Alert Center (Primary UI Surface)

A single, central home for all alerts.

### Features
- Active / Snoozed / Archived
- Filters: scope, severity, symbol, position, tool
- Prompt-based creation
- Alert cards with:
  - Current stage
  - Trigger count
  - Reference state
  - Parse confidence

---

## 10. Integration Across Fly on the Wall (Left → Right)

### Routine Drawer
- Alerts for:
  - Missing prep steps
  - Macro events
  - VIX regime shifts
- Vexy provides **morning briefing digest**

### Dealer Gravity
- Structural alerts:
  - Volume Nodes / Wells / Crevasses
  - Market Memory changes
- Structural level alerts shared with Risk Graph backdrop

### Heatmap / Selection
- Opportunity alerts
- Overcrowding warnings
- Strategy fit alerts

### Risk Graph (Analysis)
- Alerts tied to:
  - Convexity decay
  - Gamma inflection
  - Assignment zones
- Risk Graph interaction highlights **Analysis** phase

### Action (Execution / Simulation)
- Pre-trade gates (Warn / Block)
- “You are about to violate X” alerts

### Process Drawer
- Journal reminders
- Pattern detection
- Retrospective prompts

---

## 11. Vexy as Meta-Alert System

### Vexy Responsibilities
1. **Digest**  
   Summarize recent alert activity into a concise narrative.

2. **Cluster**  
   Group related alerts into themes (e.g. “Gamma pressure building”).

3. **Coach**  
   Ask *one* reflective question tied to intent.

### Vexy Must Not (v1)
- Execute trades
- Auto-create alerts
- Escalate severity automatically

### Vexy Inputs
- Recent alert events
- Current process phase
- Active positions
- Trader intent metadata

### Vexy Output
- Narrative digest
- Attention priorities
- Optional reflection prompt

---

## 12. Data Model (Simplified)

### alerts
- id
- prompt
- scope
- binding_state
- severity
- cooldown_seconds
- budget_class
- origin_tool
- phase
- created_at

### alert_interpretations
- alert_id
- parsed_spec
- parse_confidence
- model_version

### alert_events
- alert_id
- event_type
- severity
- timestamp
- override_reason (nullable)
- session_id

---

## 13. Offline & Resume Behavior

- Alerts continue evaluating server-side
- Client reconnect:
  - Receives missed events (via last_event_id)
  - Receives **one Vexy digest** summarizing missed activity

---

## 14. APIs (High Level)

| Method | Endpoint | Description |
|------|---------|-------------|
| POST | /api/alerts | Create alert (prompt-first) |
| GET | /api/alerts | List alerts |
| PATCH | /api/alerts/:id | Update alert |
| DELETE | /api/alerts/:id | Archive |
| SSE | /sse/alerts | Real-time alert events |
| POST | /api/vexy/alert-digest | Meta synthesis |

---

## 15. Implementation Plan

### Phase 1 – Foundations
- Alert definitions
- Prompt parsing
- Threshold evaluators
- Alert Center UI
- SSE delivery

### Phase 2 – Process Integration
- Routine + Risk Graph integration
- Override logging
- Reference state capture

### Phase 3 – Vexy Meta Layer
- Digest synthesis
- Clustering
- Reflection prompts

### Phase 4 – Learning Loop
- Journal linkage
- Retrospective analysis
- Alert efficacy metrics

---

## 16. Success Metrics

- Alert adherence rate
- Override frequency
- Reduction in repeated rule violations
- User trust (dismiss vs disable)
- Qualitative feedback on Vexy digests

---

## 17. Summary

This system is:
- A **process coach**
- A **risk awareness layer**
- A **memory system**
- A **learning engine**

Alerts do not shout.
They *remind, warn, and teach*—in the context of how the trader actually works.
