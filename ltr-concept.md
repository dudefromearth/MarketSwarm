# Fly on the Wall — Conceptual Application Design Document  
**A Left-to-Right Trading Operating System**

---

## 1. Purpose

Fly on the Wall (FOTW) is not a trading dashboard.  
It is a **process-driven operating system** for discretionary, convexity-based traders.

The application is designed to:
- Support a trader’s **daily routine**
- Enforce **structural thinking before execution**
- Make **risk explicit before commitment**
- Close the loop with **reflection and learning**

The UI is intentionally laid out **left to right**, mirroring how a disciplined trading day unfolds cognitively.

---

## 2. Core Design Principle

> **The UI should guide behavior without forcing it.**  
> It should make the trader *aware* of where they are in the process, not police them.

Fly on the Wall does this through:
- spatial layout
- subtle visual cues
- progressive emphasis
- intentional friction before execution

---

## 3. High-Level Layout

The application consists of **three primary zones**:
[ Routine Drawer ]  →  [ Action Surface ]  →  [ Process Drawer ]

- **Left Drawer:** Routine (Preparation)
- **Center:** Action Surface (Analysis, Decision, Execution)
- **Right Drawer:** Process (Reflection, Learning)

This layout is persistent and consistent across sessions.

---

## 4. First Entry State (Daily Onboarding)

When the user first opens the app for the day:

- The entire application is **slightly grayed out**
- No tools are immediately active
- A **horizontal process bar** is displayed prominently

### The Process Bar
- Displays the major phases of the trading loop:
  - Routine
  - Structural Analysis
  - Selection
  - Decision
  - Process
- The bar is informational only
- It does **nothing** when clicked
- Its purpose is orientation, not interaction

### Activation
- The moment the user clicks anywhere:
  - The gray overlay fades away
  - The app becomes fully interactive
  - Subtle visual emphasis appears on the **Routine drawer tab**

This creates a moment of **intentional entry** into the trading day.

---

## 5. The Routine Drawer (Left Side)

### Conceptual Role
The Routine drawer represents **preparation and grounding**.

It exists to answer:
> “Am I ready to engage the market today?”

### Characteristics
- Slide-out drawer on the **left**
- Labeled **Routine**
- Never forces itself open
- Gently hints at itself via subtle glow when appropriate

### Contents (Conceptual)
- Daily checklist
- Pre-market context
- Overnight action
- Volatility / regime awareness
- Open trade awareness (non-actionable)
- Notes or reminders

### Behavioral Constraint
- No execution
- No optimization
- No trade construction

This space is about **orientation**, not action.

When the trader is ready:
- They close the Routine drawer
- Or explicitly advance into structural analysis

---

## 6. The Action Surface (Center)

The center of the app is the **Action Surface** — where all analytical and decision-making tools live.

This area evolves naturally as the trader moves through the day.

### Tools That Live Here
- Dealer Gravity (Structural Analysis)
- Convexity Heatmap (Selection)
- Risk Graph (Decision)
- Trade Entry / Simulation (Execution)

The Action Surface is intentionally uncluttered and task-focused.

---

## 7. Structural Analysis: Dealer Gravity

Dealer Gravity is the **first active analytical step**.

### Conceptual Role
Dealer Gravity answers:
> “What is the market’s structure right now?”

It focuses on:
- Attention
- Neglect
- Instability
- Persistence

Using the Dealer Gravity lexicon:
- Volume Nodes
- Volume Wells
- Crevasses
- Market Memory

An AI assistant may:
- Highlight structural patterns
- Surface potential **entry events**
- Explain why attention may shift

Dealer Gravity produces **ideas**, not trades.

When the trader is done:
- Dealer Gravity is closed
- A structural thesis is carried forward mentally

---

## 8. Selection: Convexity Heatmap

The Convexity Heatmap translates structure into **candidate positions**.

### Conceptual Role
It answers:
> “What kind of position fits this structure?”

It emphasizes:
- Asymmetry
- Optionality
- Width vs volatility
- Strategy families (0DTE → multi-DTE)

This is still **pre-commitment**.

No execution happens here.

---

## 9. Decision: Risk Graph

Risk Graph is the **commitment gate**.

### Conceptual Role
Risk Graph exists to make risk **impossible to ignore**.

It answers:
> “Do I accept this risk profile?”

### Dealer Gravity Backdrop
Behind the Risk Graph, the trader can optionally display:
- Dealer Gravity volume topology
- GEX structure
- Structural levels / inflection lines

These are:
- **Backdrops**, not overlays
- Transparent
- Price-aligned
- Toggleable independently
- Always synced with Dealer Gravity

This visually ties **risk geometry** to **market structure**.

At this point, the trader chooses:
- Execute
- Ruminate
- Walk away

---

## 10. Execution

If the trader commits:

- The position is logged
- Entered into the simulator
- Optionally routed to a broker
- The trade becomes **live state**

From this point on:
- Analysis gives way to management
- The trade exists independently of intent

---

## 11. The Process Drawer (Right Side)

### Conceptual Role
The Process drawer is where the day is **completed**.

It represents:
- Reflection
- Learning
- Closure

### Characteristics
- Slide-out drawer on the **right**
- Labeled **Process**
- Larger than the Routine drawer
- Becomes more visually emphasized as the trader moves rightward

### Contents (Conceptual)
- Trade log
- Journal
- Playbooks
- Retrospectives
- Notes and insights

This space is deliberately calming.

---

## 12. Visual Progression & Color Language

A subtle visual gradient reinforces movement through the day:

- **Left (Routine):**  
  - Warm / yellowish tones  
  - Suggest readiness, caution, alertness  

- **Center (Action):**  
  - Neutral tones  
  - Focus and clarity  

- **Right (Process):**  
  - Cool / blue tones  
  - Calm, reflection, decompression  

As the trader interacts with tools closer to the Process side, the process bar subtly reflects that progression.

---

## 13. What This Design Enforces (Without Saying It)

- You prepared before acting
- You saw structure before selecting
- You saw risk before committing
- You reflected before ending the day

Skipping steps is possible — but visible.

---

## 14. Design Philosophy Summary

Fly on the Wall is designed to:
- Encourage **small, convex decisions**
- Reduce impulsive behavior
- Reinforce process over outcome
- Turn trading into a repeatable loop

> **Preparation → Structure → Selection → Decision → Execution → Reflection → Repeat**

The UI is not there to trade for you.  
It is there to help you **be the trader you intend to be**.

---

**End of Conceptual Design Document**