# 🌐 Volume Profile Structural Playbook (v1.0)

## 🧭 Purpose
To identify, classify, and reflect upon volume profile structures—specifically High Volume Nodes (HVNs), Volume Wells (LVNs), and Node Edges—to anticipate behavioral zones, support/resistance levels, and convexity opportunities.

---

## 🧱 Core Structures

### 1. **High Volume Nodes (HVNs)**
- **Definition**: Zones of high participation, long-term agreement, and value memory.
- **Behavior**: Mean-reverting, sticky, often provide strong support/resistance.
- **Use**:
  - Avoid initiating convexity structures here
  - Ideal for exits, fades, and traps

### 2. **Volume Wells (LVNs)**
- **Definition**: Zones lacking volume; absence of agreement.
- **Behavior**: Price moves quickly, low memory friction.
- **Use**:
  - Ideal fly centers
  - High optionality trade zones

### 3. **Node Edges**
- **Definition**: Boundaries of HVNs where value transitions occur.
- **Behavior**: High reactivity; act as forward S/R levels.
- **Use**:
  - Key levels for breakout/fade decisions
  - Long-term memory often retained

### 4. **Crevasses (Internal Volume Gaps)**
- **Definition**: Local voids within HVNs or Wells.
- **Behavior**: Flashpoints; false break zones.
- **Use**:
  - Watch for hesitation, trap setups
  - Use for short-lived fly exits or re-entries

---

## 🔁 Fractal Nature
- Profiles are fractal; large HVNs/Wells = stronger memory.
- Micro structures may evolve into macro ones.
- Node maturity increases power.

---

## 📊 Forward Signal Characteristics

| Zone Type     | Bar Behavior       | Signal Type             |
|---------------|--------------------|--------------------------|
| HVN           | Small bars, choppy | Reversion, fade          |
| Volume Well   | Large bars         | Expansion, breakout      |
| Node Edge     | Reversal or flip   | Structure test           |
| Crevasse      | Fakeout or trap    | Warning/hesitation       |

---

## 🧠 Reflection Prompts
- Is price in memory (HVN) or fleeing it (LVN)?
- Am I trading near a crevasse, an edge, or in balance?
- Is this structure emerging or mature?
- Could this zone evolve into a major node?
- Am I aligned with the market’s emotional memory?

---

## 🛠 Tools
- Tag zones by type: `HVN`, `LVN`, `Crevasse`, `Edge`
- Score zones by:
  - `fractal_level`: micro / macro
  - `maturity`: low / moderate / high
  - `bias`: fade / breakout / trap
  - `memory_persistence`: short-term / legacy

---

## 🧬 Integration with Convexity Stack
- Anchor fly centers in LVNs
- Avoid decaying inside HVNs
- Watch node edges for existential shifts
- Build trade timing on memory polarity flips

---

## 📘 Example Tag (JSON)
```json
{
  "zone": "5975–6000",
  "type": "HVN",
  "edge_top": 6002,
  "edge_bottom": 5973,
  "bias": "Fade to mean",
  "memory_persistence": "high",
  "fractal": "macro",
  "last_engagement": "2025-06-13"
}
```

# 🧭 Strategy Guide: Volume Profile in Practice

## 🎯 Objective
To apply the volume profile as a **forward analysis tool**—mapping behavior zones, preparing convex trades, and aligning entries with the market’s memory map.

---

## 🧱 Step 1: Identify the Structural Context

### 🔍 Ask:
- Where is price relative to **known HVNs**?
- Are we inside a **Volume Well**, or testing a **Node Edge**?
- Is this structure **mature**, or **emerging**?

### 🧠 Action:
- Use composite volume profile over the past **1–6 months** (or longer near ATHs)
- Focus only on the **range of prices we expect to trade in the next 1–2 weeks**
- Map HVNs, Wells, and key edges **manually**, noting structure transitions

---

## 🪜 Step 2: Classify the Current Zone

| Zone Type   | Behavior Signature                   | Trade Intent                     |
|-------------|---------------------------------------|----------------------------------|
| HVN         | Choppy, overlapping bars              | Fade extremes, wait              |
| Volume Well | Fast bars, directional acceleration   | Fly center or breakout play      |
| Node Edge   | Sudden reversal or breakout trigger   | Inflection zone → optional setup |
| Crevasse    | Confused movement or ghost rejections | Trap or abort; journaling focus  |

---

## 🧰 Step 3: Evaluate Trade Potential

### 🎯 Use Fractal Lens:
- **Macro HVN** = structural gravity → decay danger
- **Micro LVN** = fly opportunity → high optionality
- **Crevasse** = danger zone or trap → watch closely

### 🧠 Bias Filters:
- Am I assuming structure where there is none?
- Is memory **confirmed** by multiple re-tests?

---

## 📈 Step 4: Trade Execution with Profile Bias

### 🔁 Reversion Setup
- Price near edge of HVN
- Small candles, low energy
- Fade extremes → Iron Fly / Put Ratio Fly

### 🚀 Expansion Setup
- Price leaves HVN or enters a well
- Accelerating bars, opening range breaks
- Fly center in well → Debit Fly / Broken Wing / Skip Strike

### 🧨 Flip Zone Setup
- Price revisits edge → shows hesitation or force
- Look for trap candles, failed retests
- Optional entry → small fly + journal result

---

## 🧠 Reflection Protocol

Before Entry:
- Am I entering near **memory**, or **abandonment**?
- Will time help me, or kill me here?
- Is this a **zone of resolution**, or **hesitation**?

After Exit:
- Did the zone behave as expected?
- Was this a mature level, or one forming?
- Is this zone now more powerful?

---

## 📘 Notes for Charting

- Label every zone with:
  - `Zone Type` (HVN, LVN, Edge, Crevasse)
  - `Fractal` (Micro/Macro)
  - `Confidence` (Low/High)
  - `Trade Bias` (Fade/Breakout/Trap)

```json
{
  "zone": "6015–6025",
  "type": "Node Edge",
  "fractal": "macro",
  "confidence": "high",
  "bias": "watch for flip",
  "last interaction": "June 12 CPI reversal"
}