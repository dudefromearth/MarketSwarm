# Fly on the Wall — Process & Routine Cues Design Specification

## Purpose

This document defines the design and behavioral specification for **Process and Routine Cues** in Fly on the Wall (FOTW).

Process and Routine Cues are **orientation mechanisms**, not notifications.  
They exist to support the trader’s daily operating loop without becoming intrusive, coercive, or gamified.

This spec establishes:
- what cues are
- how they behave
- what users may customize
- what must remain invariant

---

## Core Design Principle

> **Cues guide awareness, not behavior.**  
> They should feel like a whisper, not an instruction.

Fly on the Wall does not enforce discipline.  
It **reveals** discipline.

---

## Conceptual Model

Process and Routine Cues are:

- **Ambient**
- **Non-blocking**
- **Non-verbal**
- **Non-judgmental**
- **Contextual**

They reinforce the left-to-right flow of the trading day:
**Preparation → Structure → Selection → Decision → Execution → Reflection**

They are not alerts, reminders, or productivity nudges.

---

## Where Cues Live in the UI

### 1. Process Bar (Persistent)
- Always visible
- Displays the phases of the trading loop
- Informational only
- Not interactive
- Cannot be disabled

This bar is the **anchor of orientation**.

---

### 2. Routine Drawer Cue (Left Side)
- Subtle visual emphasis on the Routine drawer tab
- Signals preparation phase
- Most prominent at session start
- Fades as user progresses into action surface

---

### 3. Process Drawer Cue (Right Side)
- Subtle visual emphasis on the Process drawer tab
- Grows more noticeable as the user interacts with later-stage tools
- Signals reflection and closure

---

## First-Entry State (Daily)

When the user first opens the app for the day:

- Entire application is softly grayed out
- Only the Process Bar is visually emphasized
- No forced action
- No modal dialogs

The first click:
- Removes the gray overlay
- Activates the app
- Introduces subtle Routine drawer emphasis

This creates a moment of **intentional entry**, not friction.

---

## Cue Progression Logic (Conceptual)

Cues respond to **where the user spends time**, not what they click.

- Interaction near left-side tools → Routine emphasis
- Interaction in center → neutral
- Interaction near right-side tools → Process emphasis

This is **ambient feedback**, not scoring or progress tracking.

---

## User Customization: Philosophy

Users may control **how loud the whisper is** —  
but not whether the process exists.

Customization is about **expression**, not **structure**.

---

## User Settings: Process Cues

### Settings Scope
- These settings affect **visual intensity only**
- They do not affect logic, ordering, or meaning

### Available Modes

| Mode | Description |
|-----|------------|
| **Off** | No dynamic cues; static process bar only |
| **Subtle (Default)** | Gentle glow, low contrast, slow fade |
| **Guided** | More noticeable glow, longer persistence, soft motion |

No numerical sliders.  
No arbitrary tuning.

---

### Adjustable Parameters (Bounded)

Users may adjust:
- **Cue Intensity** (via mode selection)
- **Cue Duration**
  - Short
  - Normal
  - Extended
- **Cue Frequency**
  - Once per session
  - Contextual only

---

### Non-Adjustable Elements (Invariant)

The following **cannot be disabled or altered**:

- Presence of the Process Bar
- Left-to-right phase ordering
- Semantic meaning of phases
- Relationship between Routine → Action → Process

The process is always visible, even if cues are muted.

---

## Defaults & Graduation

### Default for New Users
- Process Cues: **Guided**
- First-entry gray overlay: **Enabled**
- Routine emphasis: **Enabled**

### Progressive Autonomy
After sufficient usage (e.g., multiple completed days or trades), the system may optionally suggest:

> “Would you like fewer process cues?”

This suggestion:
- is optional
- appears once
- respects user autonomy

---

## Emotional Color Language (Non-Configurable)

Color semantics are consistent across the system:

- **Left / Routine:** Warm yellow tones  
  - readiness
  - alertness
  - mild caution

- **Center / Action:** Neutral tones  
  - clarity
  - focus

- **Right / Process:** Cool blue tones  
  - calm
  - reflection
  - decompression

Users do not customize colors, only intensity.

---

## Anti-Patterns (Explicitly Avoided)

The system must **never**:
- show popups or toasts for process cues
- block interaction
- gamify progression
- shame or warn users
- enforce completion of steps
- reset cues intraday based on P&L

Process cues are **non-judgmental**.

---

## Relationship to Other Tools

Process and Routine Cues:
- do not interfere with Dealer Gravity
- do not interfere with Risk Graph
- do not affect TradeLog or execution
- do not impact ML or scoring systems

They are **purely experiential scaffolding**.

---

## Canonical Statement

> Process cues exist to help traders remember who they intended to be —  
> not to tell them what to do.

> You may ignore the process.  
> You may not pretend it isn’t there.

---

## Implementation Note (Non-Prescriptive)

This document defines **behavioral intent**, not implementation.

Specific animation techniques, timing constants, or CSS treatments are intentionally left open, as long as they honor the principles above.

---

**End of Design Specification**