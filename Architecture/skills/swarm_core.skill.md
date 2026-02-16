# MarketSwarm Swarm Core Skill

## Skill Name
swarm_core

## Purpose

This skill enforces architectural synchronization across all Claude instances operating within MarketSwarm.

It guarantees:

- Canonical Schema authority
- Transformation discipline
- Doctrine alignment
- Engine contract integrity
- No wrapper introduction
- No structural drift

This skill must be activated before any implementation work.

---

# 1. Architectural Authority

All work must obey this hierarchy:

1. Canonical Schema (`architecture/01_canonical/`)
2. Transformation Specifications (`architecture/04_transformation/`)
3. Vexy Doctrine (`architecture/05_doctrine/`)
4. Engine Interface Contracts (`architecture/02_contracts/`)
5. Architectural Manifest (`architecture/00_manifest.md`)
6. Implementation Code

If conflict exists:
- Code is wrong.
- Doctrine must adapt to canonical truth.
- Canonical truth derives from exchange authorities.

Authoritative sources include:
- CBOE
- CME
- OCC
- Exchange rulebooks
- Exchange-published strategy definitions
- Official settlement documentation

---

# 2. Structural Invariants

The following may never be violated:

- Contract is atomic.
- Position is the canonical risk unit.
- Strategy is derived, never primary.
- Settlement is deterministic and exchange-aligned.
- American vs European style must be explicitly modeled.
- BPV (Big Point Value) must be explicitly modeled.
- Multi-day expirations must be supported.
- Futures must be first-class.
- Stock must be first-class.
- Options must support equity and futures underlyings.
- No geometry wrappers.
- No dual schemas.

---

# 3. Transformation Discipline

During canonical transformation:

- No compatibility adapters.
- No temporary translation layers.
- No fallback logic.
- No legacy mode.
- No duct tape.
- No incremental geometry patching.
- Replace, do not wrap.

---

# 4. Required Pre-Execution Sequence

Before performing any task, the agent must:

1. Read `CLAUDE.md`
2. Read `architecture/00_manifest.md`
3. Identify governing specification
4. Confirm structural alignment
5. State which authority documents govern the task

No implementation begins without alignment declaration.

---

# 5. Engine Discipline

Engines must:

- Consume canonical Position model only.
- Never fabricate settlement.
- Never override exchange semantics.
- Publish interface contracts before implementation.
- Remain independently deployable.

---

# 6. Doctrine Alignment

Vexy Doctrine must:

- Reflect exchange truth.
- Attribute all canonical definitions to their source.
- Never invent structural semantics.
- Remain philosophically aligned without distorting geometry.

---

# 7. Enforcement Clause

If a task would introduce architectural drift:

The agent must stop and explicitly declare the conflict before proceeding.
