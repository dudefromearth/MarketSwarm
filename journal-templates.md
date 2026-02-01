# FOTW Journal Templates — Insertion & Usage Specification

## Purpose

Journal templates in FOTW exist to **reduce activation energy**, not to impose structure.

They are designed to:
- help traders start writing
- provide optional reflection prompts
- disappear into the document once used

Templates are not forms.  
They are not constraints.  
They are disposable scaffolding.

---

## Core Interaction Model

### Template Selection
- FOTW provides a set of **stored templates** (e.g.:
  - End-of-Day Reflection
  - Trade Reflection
  - Weekly Retrospective
  - Monthly Retrospective
)
- Templates are selected manually by the user
- A **blank journal entry** is always the default starting state

Templates are opt-in.

---

### Template Insertion Behavior

When a user selects a template:

- The template content is **pasted directly into the journal document**
- It is inserted at the current cursor position
- It appears as **fully editable rich text / markdown**
- No fields are locked
- No sections are required

After insertion, the template is treated as ordinary document content.

The system does not retain awareness of the template once inserted.

---

## Post-Insertion Rules

After a template is pasted:

- The user may:
  - delete sections
  - reorder sections
  - rewrite prompts
  - ignore prompts
  - add freeform content anywhere

- The system does **not**:
  - track template completion
  - warn about missing sections
  - enforce structure
  - score or evaluate usage
  - treat templated entries differently from non-templated entries

A templated entry is simply a journal entry.

---

## Multiple Templates per Entry

- Users may insert **multiple templates into a single journal entry**
- Templates may be mixed (e.g.:
  - End-of-Day + Trade Reflection
  - Weekly Retrospective + Freeform Notes
)

This supports nonlinear reflection and avoids artificial separation of thought.

---

## Visual Feedback (Optional, Non-Persistent)

- Upon insertion, newly pasted template content may be briefly highlighted
- The highlight fades automatically
- No persistent visual distinction remains

This confirms the action without creating structure dependency.

---

## Template Lifecycle

- Templates are **ephemeral**
- Once pasted, they have no ongoing system identity
- Deleting all template text has no consequence
- Templates do not create metadata, states, or flags

---

## Future Extension (Optional)

### User-Defined Templates
- Users may save any journal entry as a personal template
- Personal templates behave identically to system templates
- No ranking, scoring, or recommendation of templates

---

## Explicit Non-Goals

Templates must never:
- auto-insert based on context
- block journaling until used
- enforce answers to prompts
- generate insights automatically
- imply correctness or completeness
- act as checklists

These behaviors destroy honest reflection.

---

## One-Sentence Essence

**FOTW journal templates are disposable starting points — pasted into the page, then fully owned, reshaped, or discarded by the trader.**