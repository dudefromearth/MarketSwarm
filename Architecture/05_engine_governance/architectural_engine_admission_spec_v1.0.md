# ARCHITECTURAL ENGINE ADMISSION SPECIFICATION v1.0

## Location:
architecture/05_engine_governance/architectural_engine_admission_spec_v1.0.md

## Authority:
This specification governs the admission, construction, and integration of all new engines within the MarketSwarm system.

This document supersedes feature-driven implementation priorities.

No engine may be implemented unless compliant with this specification.

---

# I. PURPOSE

The purpose of this specification is to ensure:

1. No new engine is built on pre-canonical geometry.
2. No new logic reintroduces non-canonical abstractions.
3. All engines operate exclusively on Canonical Schema v1.0 entities.
4. Architectural invariants are preserved before feature velocity resumes.
5. MarketSwarm evolves from foundation, not patchwork.

This specification is binding.

---

# II. ENGINE ADMISSION DOCTRINE

An engine may not be constructed unless the following conditions are met:

## 1. Canonical Dependency Rule

The engine must operate exclusively on:

- Canonical Instrument
- Canonical Contract
- Canonical Position
- Canonical Portfolio

No engine may depend on:

- `strategy` as primary structure
- `side` as structural determinant
- `width` as geometry abstraction
- Derived geometry shortcuts
- Pre-canonical composite abstractions

Strategy must always be derived.
Position is the only structural primitive.

---

## 2. Transformation Precondition Rule

Before engine construction begins:

- Canonical Schema v1.0 must be defined and frozen.
- Canonical Conformance Transformation Specification must exist.
- Refactor & Audit Specification must exist.
- Refactor scope must be defined.

If transformation is incomplete, engine construction is prohibited.

---

## 3. No Transitional Architecture Rule

Engines must not introduce:

- Compatibility adapters
- Dual schema support
- Legacy mode
- Translation layers
- Shadow models
- Parallel entity hierarchies

All engines consume the same canonical model.

---

## 4. Single P&L Path Rule

All financial computation must resolve through:

Canonical Position → Canonical Contract → Canonical Instrument

There may only exist:

- One settlement computation path
- One P&L computation path
- One margin computation path
- One exposure aggregation path

No engine may create an alternate computation path.

---

# III. ENGINE ELIGIBILITY CHECKLIST

Before an engine is admitted for development, the following checklist must be completed:

### Structural Compliance
- [ ] Uses Canonical Position model exclusively
- [ ] Uses canonical legs for multi-leg strategies
- [ ] Does not store derived strategy geometry
- [ ] Derives strategy classification from legs

### Computational Compliance
- [ ] No duplicate P&L math
- [ ] No duplicate intrinsic logic
- [ ] No duplicate multiplier logic
- [ ] No hard-coded geometry shortcuts

### Doctrine Alignment
- [ ] Engine behavior aligns with authoritative exchange definitions
- [ ] Settlement semantics respect instrument style (American/European)
- [ ] Big Point Value (BPV) respected where applicable
- [ ] No fabricated data
- [ ] No speculative inference

### Governance
- [ ] Referenced in CLAUDE.md
- [ ] Bound to Canonical Schema version
- [ ] Reviewed under Refactor & Audit Specification

If any box is unchecked, engine development is halted.

---

# IV. ENGINE BUILD ORDER

Engines must be built in the following sequence:

1. Canonical Schema
2. Canonical Conformance Transformation
3. Refactor & Audit Completion
4. Execution Engine
5. Cost & Commission Engine
6. Settlement Engine
7. Margin Engine
8. Backtesting Engine
9. Forward-Walk Engine
10. Machine Learning Analysis Layer

No downstream engine may precede upstream foundation.

---

# V. ENGINE CLASSIFICATION

Engines are classified as follows:

## Tier 1 — Structural Engines
- Execution Engine
- Position Engine
- Cost & Commission Engine

## Tier 2 — Financial Engines
- Settlement Engine
- Margin Engine
- Risk Engine

## Tier 3 — Analytical Engines
- Backtesting Engine
- Forward-Walk Engine
- Statistical Edge Engine

## Tier 4 — Cognitive Engines
- AFI Integration
- Playbook Engine
- Vexy Cognitive Interpretation Layer

Each tier depends on prior tiers being canonical-compliant.

---

# VI. PROHIBITED SHORTCUTS

The following patterns are explicitly banned:

- Strategy-first modeling
- Butterfly width shortcuts without canonical legs
- Vertical width as primary entity
- Implicit BPV assumptions
- Hard-coded 100 multiplier defaults
- Ignoring American/European style semantics
- Ignoring exchange-defined settlement timing
- Simulated P&L detached from canonical contract geometry

---

# VII. FREEZE DIRECTIVE

Until Canonical Conformance is declared complete:

- No new engine enters production.
- No engine bypasses Canonical Position.
- No feature work supersedes architecture work.

This freeze is architectural independence.

---

# VIII. ADMISSION DECLARATION

Before engine implementation begins, the following declaration must be logged:

> "This engine complies with Architectural Engine Admission Specification v1.0  
> and operates exclusively on Canonical Schema v1.0 entities."

---

# IX. ENFORCEMENT

This specification is enforced through:

- Refactor Audit Specification
- CLAUDE.md governance rules
- Swarm Skill Enforcement
- Spec Enforcer Agent

Any violation requires immediate halt and architectural review.

---

# X. PHILOSOPHICAL ALIGNMENT

This specification exists to protect:

- Structural integrity
- Mathematical invariance
- Exchange-aligned truth
- Convexity domain purity
- Long-term system coherence

Feature velocity does not supersede foundational correctness.

Foundation precedes expansion.

---

# STATUS

Effective immediately upon adoption.

All engine plans currently in progress must be evaluated against this specification before continuation.