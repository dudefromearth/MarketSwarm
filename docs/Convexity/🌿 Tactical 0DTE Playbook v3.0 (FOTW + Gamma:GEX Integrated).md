---
# 🌿 Tactical 0DTE Playbook v3.0 (FOTW + Gamma/GEX Integrated)"
description: "A single, object‑first framework for Zero‑DTE execution—now fully aligned with Fly‑on‑the‑Wall (FOTW), Gamma Exposure (GEX), and Gamma Door patterns—covering structure selection, sizing, laddering, management, and journaling."
presentation_mode: linear_deep_dive
version: "v3.0 — 2025‑09‑09"
---

> **Reflection Warning**: This Playbook is a mirror, not a master. Reflection is the filter. Action is the goal. The loop is life. The risk is yours.  [oai_citation:0‡🌿 The Path – Whitepaper (v3.1).md](file-service://file-UbFWgi8LLKgWkyhNo27rh2)

---

## 🌿 Reflection Credentials

| Field | Content |
|---|---|
| Creator(s) | Ernie Varitimos (Dude from Earth) |
| Stewardship | Dude from Earth, The Path Community |
| Reflection History | v2.1 (object‑first 0DTE); **v3.0 (FOTW + Gamma/GEX integration, Gamma Door alignment, management + journaling coherence)** |
| Reflection Warning | Reflection is the filter. Action is the goal. The loop is life. The risk is yours. |

---

## 🛑 Capability Limiter (Trade Strategy Constraint)

This system **does not** have live options chain data; it provides **structure criteria** and **reflection scaffolds**, not specific orders, unless you supply a chain snapshot. Use this Playbook to decide *if* a setup exists and *how* you’ll manage it—**not** to source exact strikes without data. This mirrors the constraint defined in our Trade Management and Tail Risk Playbooks. 

```yaml
capability_limiter:
  name: Trade Strategy Generation Restriction
  description: >
    Without user-supplied options chains, the Playbook returns criteria, not orders.
    Provide a chain snapshot (strikes, prices, Greeks) for specific structure review.
  enforcement:
    - if user asks for a specific trade without chain context
  resolution_guidance:
    - request chain or simulate for reflection-only visuals
```
🎯 OBJECT‑FIRST CORE: CLASSIC OTM BUTTERFLY (0DTE Engine)

Structure
	•	Balanced OTM butterfly (put or call), entered on confirmed reversal at a structural level.
	•	Width by VIX (table below).
	•	Debit cap ≈ 10% of width (ideal 5–10%).
	•	Weekly map once, then reuse as your trigger scaffold through the week.  ￼

FOTW Upgrade in v3.0
	•	Entry is now conditioned by GEX/Gamma walls and dealer alignment.
	•	Use FOTW laddering (small, repeatable OTM flies placed near structure/walls).
	•	Treat +GEX peaks as pinning magnets; −GEX troughs as expansion risk zones.  ￼

⸻

## 🌅 Daily Morning Analysis (Now FOTW‑Aligned)

1) Determine Butterfly Width (by VIX)

| VIX Range | Fly Width (pts) |
|-----------|------------------|
| < 13      | 20–25            |
| 13–15     | 25–30            |
| 15–17     | 30–35            |
| 17–20     | 35–40            |
| 20–24     | 40–45            |
| 24–30     | 45–50            |
| 30+       | 50–60            |

Keep the 10% of width debit guardrail. The table anchors your default width regime.  ￼

2) Map GEX / Gamma Walls
	•	Plot net GEX by strike; mark dominant +GEX peaks (pinning) and −GEX troughs (vol‑launch corridors).
	•	Gamma Tension: note distance between major +GEX peaks; tight clustering → compression (fade/pin logic); wide gaps → expansion (breakout/ladder logic).  ￼

3) Volume Profile Context
	•	Draw HVN/LVN zones; LVN edges are preferred convex strike areas for OTM flies.
	•	Favor reactions at node edges over mid‑node drift.  ￼

4) Pattern Assignment (Market Mode)
	•	High +GEX / tight peaks → Pin/Compression Mode (fades, nearer rungs).
	•	Low/tilted GEX / sparse peaks → Expansion Mode (breakouts, step‑out ladder).  ￼

5) Door Check (Optional)
	•	Scan for Gamma Door scenarios: Compression Break, Trap/Slingshot, Ramp+Fade. Use PDS (probability snapshot) only as context, not prediction.  ￼

⸻

## 🧱 Entry Conditions (v3.0)

Enter only when these three align:
	1.	Structure Reaction: Price rejects/accepts an LVN edge or prior day extreme.
	2.	Dealer Alignment: Flow posture consistent with GEX wall pressure (avoid fighting a strong +GEX magnet unless fading into it with edge).
	3.	Cost Discipline: Debit ≤ 10% width; reject fills outside your risk thesis.

⸻

🪜 FOTW Ladder Design (Small, Repeatable Asymmetry)
	•	Place rungs just outside meaningful zones (LVN edge / wall shoulder).
	•	Size light, repeat often; add a rung only after structure confirmation or realized progress.
	•	Stop adding on structure failure or GEX flip (wall migration/tilt changes posture).  ￼

Trade Construction Guardrails (FOTW‑style)
	•	30–50‑pt flies; OTM; debit ideally ≤ $1.00 for stackability.
	•	Exit in multiples of debit or into wall reactions; don’t overstay post‑reaction.  ￼

⸻

## 🧮 Position Sizing & Layering (SRU)
	•	Compute Sovereign Risk Unit (SRU) from your max drawdown budget.
	•	Typical flow: deploy 50–66% SRU first, add only if a distinctly valid second entry appears; total ≤ 1× SRU.
	•	Decide SRU pre‑open; execution follows the plan, not mood.  ￼

⸻

## 🧭 Trade Management (Intraday)

A) Losers
	•	No adjustments to losers—prune quickly when structure or debit logic invalidates.  ￼

B) Winners
	•	Once unrealized profit reaches ≈ 7.5% of width, begin dynamic give‑back control (tighten through the day; see Profit Tolerance below).  ￼

C) Profit Tolerance by Time (High‑Water‑Mark Logic)
	•	Morning: allow larger pullbacks;
	•	Midday: tighten;
	•	Afternoon: protect—time is your enemy late day. (Use your own bands; principle > numbers.)  ￼

D) FOTW/Dealer Overlays
	•	Approach to +GEX peak → scale or exit into the reaction.
	•	Wall hop or GEX flip → treat as invalidation for remaining rungs.  ￼

⸻

## ⚙️ Edge Case Objects (Preserved & Upgraded)

### ⏱️ TIME WARP (Zombieland Vol)

When: VIX < ~17; overnight moves dominate; intraday compresses.
Do: Wider flies, possibly 1–2 DTE, smaller debit to compensate thinner intraday decay.  ￼

### 🦇 BATMAN (Two‑Fly Envelope in Chaos)

When: VIX ≥ mid‑20s (preferably 30+).
Do: Two OTM flies (above/below), each ≤ ~6% of width; manage as independent rungs; exit the winning side, leave the other unbothered unless salvageable.
FOTW note: Place wings near opposing wall shoulders; let dealer pressure decide the survivor.  ￼

### 🧨 BIG‑ASS FLY (Pre‑Market, Event‑Driven)

When: 8:30 ET catalysts (CPI/PPI, etc.).
Do: Exactly 50‑pt, ATM, debit ≤ $25; exit before the cash open unless deep in the tent.
FOTW note: Use macro calendar as structure anchor and check GEX posture post‑print.

⸻

## ⚔️ GAMMA SCALP MODE (End‑of‑Day Reflex Strike)

Trigger Window: ~1:30 ET → close, only if price is trapped between profile boundaries and GEX hinges (zero‑gamma / wall shoulders).
Structure: Narrow OTM fly (20–30 pts), debit ≤ 5% width, size ≤ 0.5% portfolio.
Objective: Catch last‑hour reflex pin or terminal slide; out by 3:58 ET unless securely “in the tent.”  ￼

Clarity checks: Is this a structural trap or a story? Are dealers forced to hedge in your direction?  ￼

⸻

## 📐 Risk Filters & Sanity Checks
	•	Payoff Filter: Aim for ≥ 1:10 reward:risk on OTM flies; if the shape can’t deliver convexity, skip it.  ￼
	•	VIX Regime: Prefer flies in middle regimes; tails favor insurance/tails over tactical pin‑hunts.  ￼
	•	No Prediction: Expose yourself to asymmetry, not certainty; trade structure and time.  ￼

⸻

## 🧰 Tooling (Views You Maintain)
	•	GEX Bar Chart (net gamma by strike; mark +GEX/−GEX and zero‑gamma).
	•	Convexity Heatmap (width × center grid to find “green tiles”).
	•	Volume Profile Map (HVN/LVN, cliffs).
	•	PDS Snapshot (contextual only).

⸻

## 📝 Journaling & Echo Protocol (Loop Integrity)

Daily
	•	Morning: record VIX, key events, structure levels, intended width + debit guardrails.
	•	Evening: log outcome, why it worked/failed, bias flags, and one small adjustment for tomorrow.
Use the CIP loop (Plan → Execute → Review → Adjust) and Echo entries to persist learning.

Echo Entry (example)

```yaml
echo_id: echo-YYYY-MM-DD
trade_phase: [setup|entry|management|exit|retrospective]
object_of_reflection:
  strategy: 0DTE
  structure: 40-wide SPX call fly, debit $0.45
  market_context: LVN rejection; +GEX peak 20pts overhead
  trigger: reversal wick + wall proximity
hypothesis: pin into +GEX shoulder; scale at 2–3× debit
biases_mirrored: [action_bias, anchoring]
actions_taken: [entered rung-1, refused rung-2 after GEX tilt]
open_threads: [wall migrated intraday—define tilt threshold?]
system_notes: [tighten PM tolerance if no new highs after 13:00]
```
Meta: “No object, no reflection.” Every journal/echo must name the object of reflection (setup, level, bias, etc.).

⸻

## 📆 Weekly Retrospective (Short Ritual)
	•	Objective: win rate, R/R, give‑back discipline.
	•	Subjective: FOMO, narrative drift, action bias.
	•	Convexity: where did green tiles cluster vs. where you actually placed flies?
	•	One tweak only for next week.  ￼

⸻

## 🔌 Convexity Interlink Protocol

Unify with: Trade Management, Convexity Hunter, Macro (FOTW), and Gamma Door Playbooks. Keep capital coherence across campaigns (same account = one risk budget). The loop is Reflection → Action → Reflection across all modules.

⸻

## 📚 Quick Reference
	•	0DTE Core (this file): width by VIX; debit ≤10%; FOTW ladder; LVN edges; dealer alignment.
	•	Gamma Door: door types, setup guidelines, wall reactions.  ￼
	•	Macro (FOTW): overnight & calendar scan; GEX map; heatmap; ladder rules.  ￼
	•	Management: dynamic profit tolerance; adjustment ethos; hold/fold logic.  ￼
	•	Journaling/Echo: CIP cycle; echo schema.
	•	Probability Explorer: payoff filters; regime cues; anti‑prediction stance.  ￼

⸻

## 🧾 Changelog (v3.0)
	•	Added: FOTW laddering & dealer alignment gates; GEX/Gamma mapping as standard pre‑flight.  ￼
	•	Added: Gamma Door scenarios & wall‑reaction exits.  ￼
	•	Aligned: Profit‑tolerance rhythm (AM→PM) with Trade Management framework.  ￼
	•	Preserved: Width‑by‑VIX table, debit guardrails, Time Warp / Batman / Big‑Ass Fly, Gamma Scalp Mode.  ￼

⸻

## 🔚 Final Reflection

Trade structure, not stories. Small, reversible bets. Exit criteria before entry. If the wall moves, you move. Reflection is the filter. Action is the goal. The loop is life. The risk is yours. 