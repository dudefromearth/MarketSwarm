# Retrospectives as Journal Entries (Unified Editor Design)

## Core Decision

Retrospectives are **not a separate activity** and do **not require a separate editor**.

A retrospective **is a journal entry**.

Creating a dedicated editor for retrospectives would fracture the mental model and introduce unnecessary ceremony.

---

## Why a Separate Retrospective Editor Is Incorrect

A separate editor would imply that:

- retrospectives are a different kind of thinking
- retros require more formality or effort
- journaling is “light,” while retros are “serious work”
- reflection happens in discrete modes

This contradicts the core FOTW principle:

> **Process is continuous. Reflection is a single loop.**

Professional traders do not switch tools to reflect — they widen perspective.

---

## The Correct Mental Model

### There is **one Journal Editor**

The same editor supports:
- daily journal entries
- trade reflections
- weekly retrospectives
- monthly retrospectives

The tooling does not change.  
Only the **context and time horizon** change.

---

## What Makes a Retrospective Different (And What Does Not)

A retrospective differs only by:

- time anchor (week or month)
- optional template insertion
- optional entry type or tag

A retrospective does **not** differ by:
- editor
- layout
- permissions
- attachment handling
- reference capability

This preserves continuity and reduces cognitive friction.

---

## Role of the Retrospective Panel

The Retrospective Panel is a **navigator**, not a workspace.

Its purpose is to:
- surface recent weekly and monthly retrospectives
- provide quick access to past entries
- initiate new retrospective entries

It does **not**:
- contain a separate editor
- manage content
- impose structure

---

## Creating a New Retrospective Entry

When a trader selects:
- “New Weekly Retrospective” or
- “New Monthly Retrospective”

The system should:

1. Open the **existing Journal editor**
2. Anchor the entry to the appropriate week or month
3. Optionally pre-insert a lightweight template
4. Optionally tag the entry as a retrospective

From the trader’s perspective:

> “I’m journaling — just at a wider lens.”

---

## Templates and Retrospectives

Templates are applied at **entry creation**, not at the editor level.

- Daily entry → optional daily template
- Weekly retrospective → optional weekly template
- Monthly retrospective → optional monthly template

Templates are pasted into the same editor as freeform text and may be edited or deleted immediately.

---

## Psychological Benefits of a Unified Editor

- No new UI to learn
- No “special mode” anxiety
- No increase in perceived effort
- Familiar muscle memory
- Lower activation energy

This reframes retrospectives from a task into a natural extension of journaling.

---

## Design Principle (One Line)

**Retrospectives are not a different activity — they are journaling with more time in view.**

---

## Outcome

By reusing the Journal editor for retrospectives, FOTW preserves:

- coherence of the reflection loop
- trader sovereignty
- low-friction adoption
- alignment with real trader behavior
- avoidance of reflection theater

One editor.  
One journal.  
Many lenses.