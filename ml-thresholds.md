# ML Confirmation Thresholds Specification  
**Fly on the Wall / The Path**  
**Status: Provisional (Exploratory Phase)**

---

## 0. Purpose

This specification defines how Machine Learning findings may **confirm**, **reinforce**, or **remain silent** with respect to human-observed patterns — without asserting truth, causality, or prescription.

ML does **not** discover Playbooks.  
ML does **not** initiate meaning.  
ML exists to say, *at most*:

> “This appears more often than chance would suggest.”

Nothing more.

---

## 1. Core Doctrine (Non-Negotiable)

1. ML is **confirmatory**, never generative
2. ML never names patterns
3. ML never recommends actions
4. ML never escalates urgency
5. ML silence is always valid
6. Human reflection always outranks model confidence

If any of these are violated, the system must default to **no output**.

---

## 2. ML Confidence States (Not Decisions)

ML does not operate in “true / false”.  
It operates in **confidence states**, each with strictly limited expressive power.

### 2.1 Confidence Levels

| Level | Name        | Meaning (Internal Only)                  | User-Facing Behavior |
|------:|-------------|------------------------------------------|----------------------|
| 0     | Silent      | Insufficient signal                      | No output            |
| 1     | Weak Echo   | Slight recurrence above baseline         | Silence preferred    |
| 2     | Emerging    | Non-random recurrence observed           | Gentle reflection   |
| 3     | Consistent  | Stable recurrence across contexts        | Confirmatory note   |
| 4     | Persistent  | Longitudinal consistency across periods  | Rare mention        |

**Important:**  
Levels 3–4 should be *rare* in early system life.

---

## 3. Baseline Requirements (Minimum Data)

ML confirmation is **disabled** unless all are met:

- ≥ **5 completed retrospectives**
- ≥ **20 closed trades**
- ≥ **2 distinct periods** (e.g., weeks)

If unmet → ML remains silent.

---

## 4. Pattern Eligibility Criteria

ML may *consider* confirmation only when a pattern meets **all**:

1. Appears in **human-generated text**
   - Journal
   - Retrospective responses
2. Appears across **multiple artifacts**
   - Not a single session
3. Appears without **prompted repetition**
   - Not induced by templates
4. Is **behavioral or contextual**, not outcome-based

### 4.1 Disallowed Pattern Classes

ML must **never** confirm:
- P&L-only patterns
- Strategy performance claims
- Market predictions
- “Good / bad” behavior labels
- Optimization outcomes

---

## 5. Confirmation Thresholds (Exploratory Defaults)

These are **starting values**, explicitly marked for revision.

### 5.1 Emerging Pattern (Level 2)

- ≥ 3 occurrences
- Across ≥ 2 retrospectives
- Within ≤ 30 days
- Language similarity score ≥ 0.65
- No contradictory signals > 50%

**Allowed Output:**  
A single, optional reflection line.

---

### 5.2 Consistent Pattern (Level 3)

- ≥ 5 occurrences
- Across ≥ 3 retrospectives
- Across ≥ 2 different market regimes
- Persistence ≥ 2 weeks
- Stability score ≥ 0.75

**Allowed Output:**  
One confirmatory sentence, max.

---

### 5.3 Persistent Pattern (Level 4)

- ≥ 8 occurrences
- Across ≥ 4 retrospectives
- Across ≥ 3 periods (weeks/months)
- Stability score ≥ 0.85
- Low variance in description

**Allowed Output:**  
Only when user already engaged with Playbooks.

---

## 6. Language Constraints (Critical)

ML-backed language must follow **Process Echo rules**, not Alert rules.

### 6.1 Allowed Language

- “This has appeared before.”
- “This pattern shows up across multiple sessions.”
- “This has been consistent recently.”
- “You’ve named something that seems stable.”

### 6.2 Forbidden Language

- “This means…”
- “You should…”
- “This causes…”
- “This improves…”
- “This works…”

If the model *wants* to explain, it must remain silent.

---

## 7. Timing Rules

ML confirmation may occur only in these contexts:

- Retrospective mode
- Journal reflection (non-intrusive)
- Process Echo (lowest priority)

ML confirmation is **forbidden**:
- During live trading
- During execution
- During alert handling
- During market stress events

---

## 8. Human Override & Deference

If a trader:
- Dismisses ML confirmation
- Ignores it repeatedly
- Expresses disagreement

Then:
- ML must downshift confidence
- ML must remain silent for that pattern for ≥ 14 days

---

## 9. Versioning & Tightening Protocol

This framework is **explicitly provisional**.

Future tightening may include:
- Regime-adjusted thresholds
- User-specific baselines
- Playbook-aware weighting
- Confidence decay functions

But **never**:
- Automatic Playbook creation
- Strategy validation
- Prescriptive escalation

---

## 10. Success Criteria (Early Phase)

This system is working if:
- Most users never see ML confirmation
- When they do, it feels obvious
- Traders say “I already felt that”
- No one feels corrected or instructed

---

## Final Guardrail

> **ML exists to support reflection, not replace it.**  
> If reflection disappears, ML has gone too far.

---

**Status:**  
Approved for exploratory implementation  
Safe to evolve without breaking doctrine