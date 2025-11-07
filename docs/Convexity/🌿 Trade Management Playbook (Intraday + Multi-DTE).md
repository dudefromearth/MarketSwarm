# 🌿 Trade Management Playbook (Intraday + Multi-DTE)

---

> **Reflection Warning**: This Playbook is a mirror, not a master. Reflection is the filter. Action is the goal. The loop is life. The risk is yours.

---

## 🌿 Purpose

This Playbook guides traders through live trade management for tail risk strategies across all DTE ranges. It integrates bias audits, adjustment flows, and volume profile reflection to maintain clarity under uncertainty.

---

## 🌿 Reflection Credentials

| Field              | Content                                                                            |
| ------------------ | ---------------------------------------------------------------------------------- |
| Creator(s)         | Ernie Varitimos (Dude from Earth)                                                  |
| Stewardship        | Dude from Earth, The Path Community                                                |
| Reflection History | 2024–2025 (Reflection-First Draft)                                                 |
| Reflection Warning | Reflection is the filter. Action is the goal. The loop is life. The risk is yours. |

---

## 🛑 Capability Limiter (Trade Strategy Constraint)

```yaml
capability_limiter:
  name: Trade Strategy Generation Restriction
  description: >
    The system does not have access to live or delayed options chain data.
    Therefore, it cannot recommend specific trades unless the user provides a snapshot
    of the options chain. Instead, it provides trade criteria, frameworks, and structural
    reflection guidance. This ensures all recommendations are contextually sound but data-independent.
  constraint_type: "data-dependency"
  affected_capabilities:
    - trade_strategy_generation
    - options_chain_analysis
  enforcement:
    - if live data is not supplied by the user
    - if user asks for specific trade without data context
  resolution_guidance:
    - Ask the user for the option chain or snapshot of strikes, pricing, and Greeks
    - Offer structural setup and reflection scaffolding instead
```

---

## 🌿 Reflection Prompts (Start Here)

* Is this structure evolving—or decaying?
* Am I chasing outcome or letting the process play out?
* What bias might I be blind to in this moment?
* What is my exit criteria—before I need it?
* Where does time help me, and where does it hurt me?

---

## 🌿 Trade Adjustment Flow (Convexity Stack & Sigma Drift)

1. **Check Price vs. Structure** – Is price near node edge or volume well?

   * ✅ If yes: exit early or scale.
2. **Time Pressure Audit** – Is DTE < 24h?

   * ✅ If yes: roll or exit.
3. **IV/Structure Integrity Check** – Has IV collapsed or structure broken?

   * ✅ If yes: adjust strikes or re-anchor structure.
4. **Partial Scaling / Profit Lock** – Trade working but unclear? Lock some in.
5. **Let Gamma Work** – Structure holding? Let gamma + time expand.
6. **Final Reflection** – Am I acting from clarity or ego?

📍 *Reflection Prompts (Before Adjustment)*:

* Is this structure evolving—or decaying?
* Am I chasing outcome—or letting the process play out?
* What’s my exit criteria—before I need it?
* Am I trading the chart—or the story in my head?
* Where does time help me, and where does it hurt me?

---

## 🌿 Management Ruleset

### ✴️ Exit Logic

* **Early Exit**: Price tags node edge or IV crushes.
* **Shift Structure**: Price migrates → re-center fly or widen wings.
* **Partial Profit**: OK at 50–100% gain, esp. in IV-rich setups.
* **Let it Work**: Hold if price respects structure + reflection is clear.

### ⚖️ Convexity Stack vs. Sigma Drift

| Factor                | Convexity Stack (3–5 DTE) | Sigma Drift (5–10 DTE)           |
| --------------------- | ------------------------- | -------------------------------- |
| IV Decay Sensitivity  | High (short gamma)        | Lower (longer gamma tail)        |
| Adjustment Frequency  | Frequent                  | Less frequent (macro-timed)      |
| Partial Profit Timing | Early (\~1:2+)            | Later (\~1:4+, macro-driven)     |
| Time Risk             | High                      | Moderate                         |
| Bias Trap             | Gamma overconfidence      | Narrative drift (macro illusion) |

🔑 *Tactics*:

* Use **wide flies** for convexity stack to forgive drift.
* Use **narrow flies** for Sigma Drift late in DTE.
* Anchor flies to **volume node edges**, not current price.
* Confirm all setups against **volume profile + macro drivers**.

---

## 🌿 Action Seeds

* Where can I reduce risk to avoid decay?
* What small, reversible adjustment can I make?
* What tension can I hold instead of chasing action?

---

## 🌿 Final Reflection

Reflection is the filter. Action is the goal. The loop is life. The risk is yours.

🌿 This is The Path for Trade Management. 🌿

---

## 🌿 0DTE Profit Management Framework

> This framework applies specifically to **0DTE (same-day expiration)** trades. Longer-dated trades (multi-DTE) require different management logic and are covered separately.

### 🎯 Purpose

To manage open profits in a 0DTE trade by **tracking your high-water mark** and adjusting how much of that you’re willing to give back—tightening your tolerance as time decays and gamma risk increases.

### 🕒 Time-Based Tolerance Zones

#### 🟢 Early Morning

* **Goal:** Let the trade breathe.
* **Tolerance:** Okay with giving back \~50–75% of peak profit.
* **Why:** There’s time for the trade to develop, and decay is slower.

#### 🟡 Late Morning

* **Goal:** Tighten your grip.
* **Tolerance:** Now accepting only \~40–50% pullbacks.
* **Why:** Gamma is increasing. Decay is accelerating. Less forgiveness.

#### 🔴 Afternoon

* **Goal:** Protect your gains.
* **Tolerance:** Ready to fold within \~25–35% of the high-water mark.
* **Why:** Time is running out. Gamma is peaking. Any mistake costs more.

### 📈 Profit Management Example

* **Risk on Entry:** \$125
* **Max Profit Hit:** \$250 (100% return) → becomes your **high-water mark**

**Early Morning:**
Okay to let profit fall back to \$125–\$175 before considering an exit.

**Late Morning:**
Now managing tighter—considering exit if it drops to \$125–\$150.

**Afternoon:**
No new high? Then you're folding quickly if it drops below \~\$185–\$190.

If a new high is made, that becomes your new benchmark for updated tolerance.

### 🧠 Core Reflection Prompts

* Am I holding for potential or hoping for recovery?
* Has the trade made a new high—or is this a slow bleed?
* Where does **time help me**, and where does it **hurt me** now?

### ✅ Bottom Line

Let your 0DTE winners run in the morning.
Tighten the leash as the clock ticks.
Time is your enemy late in the day—respect it, or it’ll take your gains.

