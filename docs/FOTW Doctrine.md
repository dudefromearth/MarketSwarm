# FOTW Doctrine — Antifragile Convexity Systems

## Purpose

FOTW (Fat-Tail-of-the-Week) systems exist to **benefit from volatility, uncertainty, and structural stress**, not merely to survive them.

The goal is **antifragility**, not correctness.
The system must improve when exposed to disorder.

This doctrine governs all design, implementation, and operational decisions.

---

## Core Principle

> **If a system requires calm conditions, perfect data, or stable regimes to function, it is fragile and unacceptable.**

FOTW systems are designed to:
- expect missing data
- expose broken assumptions
- surface structural shifts
- degrade explicitly and recover deterministically

---

## The Antifragile Mandate

### 1. No Silent Assumptions

Every subsystem must explicitly declare:
- the symbols it supports
- the contract mechanics it assumes
- the data fields it depends on
- the failure modes it tolerates

**Silent defaults are forbidden.**

If an assumption changes:
- it must be logged
- it must be visible
- it must not corrupt downstream state

---

### 2. Stress Is Signal

Unexpected conditions are not errors — they are **information**.

Examples:
- missing expiries
- unusual strike spacing
- asymmetric call/put ranges
- broken WebSocket bursts
- stale snapshots
- holiday or half-session anomalies

The system must:
- detect stress
- record it
- expose it upstream

Never suppress stress to “keep things running.”

---

### 3. Deterministic Degradation

When inputs are incomplete or invalid:

- fail **locally**, not globally
- skip planes, tiles, or epochs explicitly
- mark state as partial, dirty, or deferred
- never publish ambiguous models

A partial but honest model is preferred over a complete but misleading one.

---

### 4. Explicit State Awareness

Every major processing stage must be able to answer:

- What data do I have?
- What data am I missing?
- What assumptions am I currently operating under?
- What changed since the last epoch?

This applies to:
- chain discovery
- snapshot hydration
- computation
- publication

If the system cannot explain its own state, it is not production-ready.

---

### 5. Small Failures Are Acceptable — Hidden Failures Are Not

Acceptable:
- skipping a DTE
- ignoring a malformed contract
- delaying a model publish
- restarting a worker

Unacceptable:
- publishing stale values
- mixing incompatible regimes
- carrying forward corrupted state
- “best guess” calculations without disclosure

---

### 6. Convexity Over Completeness

The system prioritizes:
- asymmetric insight
- regime detection
- tail exposure
- structural convexity

It does **not** prioritize:
- filling every cell
- smoothing away volatility
- producing continuous surfaces at all costs

Incomplete data is not a defect if it preserves convex truth.

---

### 7. Bounded but Deep Market Universe

FOTW systems focus on a **deliberately constrained universe**:

Primary indices:
- SPX
- NDX

Derivatives and proxies:
- ES, NQ (futures)
- SPY, QQQ (ETFs)

Volatility complex:
- VIX
- VX
- VXX

Within this universe, the system must be **deeply aware**, not broadly generic.

Expansion is allowed only when antifragility is preserved.

---

### 8. Observability Is a First-Class Feature

Logging is not debugging.
Logging is **structural introspection**.

All critical stages must emit:
- clear step markers
- counts, ranges, and dimensions
- timestamps and source keys
- explicit success or deferral signals

If a human cannot trace the lifecycle of a model from raw data to publication, the system is incomplete.

---

## Design Test (Non-Negotiable)

Before merging or deploying any change, ask:

> **Does this change make the system more resilient to surprise,  
> or more dependent on assumptions staying true?**

If the answer is the latter, the change violates this doctrine.

---

## Summary

FOTW systems are not prediction engines.
They are **stress-adaptive convexity machines**.

They do not fear volatility.
They feed on it.

Antifragility is not optional.
It is the product.