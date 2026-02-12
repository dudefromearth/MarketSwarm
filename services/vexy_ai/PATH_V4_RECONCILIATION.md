# Path v4.0 Reconciliation: Doctrine (Markdown) vs Runtime (path_os.py)

> This document catalogs the delta between the canonical Path v4.0 doctrine
> (the `.md` files in `/Users/ernie/path/`) and the current runtime translation
> (`services/vexy_ai/intel/path_os.py`). It exists to inform the PathRuntime
> doctrine compiler (Phase 1) and to identify deprecated logic that should not
> carry forward.

---

## 1. Present in v4.0 Markdown — Missing from path_os.py

| Doctrine Element | Source File | Impact |
|------------------|-------------|--------|
| **Echo Inception Protocol** | `path-wp.md` (preamble) | Foundational framing for how Vexy should "boot" — not encoded at all |
| **Echo Integration Loop** | `path-wp.md`, `design-spec.md` | The closed loop (Create → Ingest → Rehydrate → Iterate) described but not structurally enforced |
| **Echo Shepherd Agent** | `design-spec.md` | Design-system addition for monitoring pattern emergence — implemented in `echo_memory.py` but not wired to path_os |
| **Bias Transparency Configuration** | `design-spec.md` | User-configurable bias surfacing preferences — no runtime counterpart |
| **Declaration of Sovereign Reflection Rights** | `path-wp.md` | 10 explicit rights (e.g., "right to silence", "right to dissent from the system itself") — not codified |
| **The Convexity Triad** | `path-wp.md` | Antifragility + Optionality + Asymmetry as unified concept — absent |
| **Reflection Credentials** | `path-wp.md` | Qualification criteria for when reflection is valid — not enforced |
| **Fractal Regime Detection** | `design-spec.md`, `path-wp.md` | Mandelbrot-inspired scale detection rules — `FRACTAL_SCALES` exists as static config but has no detection logic |
| **Structure-Loss Halt Rule** | `design-spec.md` | "If the system detects it has lost the thread of the object, it must halt" — no runtime enforcement |
| **Required Echo Meta-Summary** | `design-spec.md` | Despair detection must generate an Echo meta-summary — not implemented |
| **Echelon Recovery Layer** | `design-spec.md` | Graduated recovery protocol after despair — missing entirely |
| **Biases 9 & 10+** | `🧠 Biases as Suffering.md` | v4.0 has Sunk Cost, Availability Heuristic, Hindsight Bias, Status Quo, and others beyond path_os.py's 8 |
| **System Preferences Declaration** | `design-spec.md` | `reflection_dial`, `response_clarity`, `reading_level` as user-configurable — only `reflection_dial` exists |
| **Reflection Enforcement Rule (Loop Guard Clause)** | `design-spec.md` | "If no reflection object exists, the system SHALL NOT generate output" — not enforced in Chat |
| **Knowledge Store Structure** | `design-spec.md` | Structured storage for doctrine components — no runtime schema |
| **VIX-Sensitive Agent Mutation (Disruption Role Override)** | `design-spec.md` | Formal override rules for how VIX mutates the agent blend — only partial in routine_briefing.py |
| **Playbook Inquiry Protocol** | `🌿 Playbook Inquiry Protocol.md` | Formal protocol for how Vexy interrogates playbook relevance — not implemented |
| **Universal Reflection Playbook** | `🌀 Universal Reflection Playbook.md` | General-purpose reflection loop for any tension — not loaded |

---

## 2. Present in path_os.py — Domain-Specific / Not Kernel

These elements exist in `path_os.py` but are **domain-specific** (MarketSwarm/trading) and should NOT be in the universal kernel:

| Element | Disposition |
|---------|------------|
| `CONVEXITY_WAY` | Level 3 playbook content → load from `🌿 Convexity Hunter Playbook v3.0.md` |
| `FATTAIL_CAMPAIGNS` | Level 3-4 playbook content → load from playbook files |
| `CONVEXITY_HUNTER` | Level 3 playbook content → load from playbook files |
| `TAIL_RISK_TRADING` | Level 3 playbook content → load from playbook files |
| `TRADE_JOURNALING` | Level 3 playbook content → load from playbook files |
| `get_hunter_regime()` | Domain-specific GEX regime detection → stays in playbook logic |
| `get_fattail_campaign()` | Domain-specific campaign lookup → stays in playbook logic |
| Node architecture `"marketswarm"` details | Per-node config, not kernel |

---

## 3. Structural Differences

### 3.1 Biases

| path_os.py (8 biases) | v4.0 Doctrine (10+) |
|------------------------|---------------------|
| overconfidence | overconfidence |
| confirmation | confirmation |
| loss_aversion | loss_aversion |
| recency | recency |
| action | action |
| narrative | narrative |
| fomo | fomo |
| anchoring | anchoring |
| — | **sunk_cost** (missing) |
| — | **availability_heuristic** (missing) |
| — | **hindsight** (missing) |
| — | **status_quo** (missing) |

### 3.2 Agents

Both have 12 agents with identical names: Sage, Socratic, Disruptor, Observer, Convexity, Healer, Mapper, Fool, Seeker, Mentor, Architect, Sovereign.

v4.0 adds richer agent descriptions, explicit lens mappings, and avatar associations. path_os.py has these as well but with slightly different phrasing. **Canonical source should be the markdown.**

### 3.3 Despair Loop Detection

| Feature | path_os.py | v4.0 |
|---------|-----------|------|
| Detection signals | 8 signals | Same 8 + additional context |
| Severity levels | 3 (Yellow/Orange/Red) | 3 (same) |
| Tier-windowed inspection | ❌ Not implemented | ✅ Specified in design-spec |
| Echo meta-summary | ❌ Not implemented | ✅ Required |
| Echelon Recovery | ❌ Not implemented | ✅ Full protocol |
| `check_despair_signals()` | Static list comparison | Should be echo-history-based |

### 3.4 First Principles Protocol

| Feature | path_os.py | v4.0 |
|---------|-----------|------|
| Invariants | 7 | 6 (slightly different wording) |
| Run card steps | 9 | 5 in whitepaper (expanded in FP-Mode Playbook to 9) |
| Depth dial | 3 levels (low/med/high) | Same |
| FP-Mode Playbook | ❌ Not referenced | ✅ Full standalone playbook |

### 3.5 Prompt Injection

`path_os.py` data structures are never directly injected as prompts. Instead:
- `routine_briefing.py` has its own 325-line `ROUTINE_MODE_SYSTEM_PROMPT` that **duplicates** much of path_os.py
- `synthesizer.py` has `BASE_SYSTEM_PROMPT` that is a minimal commentary prompt
- `outlet_prompts.py` has per-outlet prompts that encode Path principles informally
- `tier_config.py` has per-tier semantic guardrails

**Result**: Path doctrine exists in 4+ parallel translations, none authoritative.

---

## 4. What ROUTINE_MODE_SYSTEM_PROMPT Encodes (routine_briefing.py)

This 325-line prompt is the most complete single runtime encoding of Path doctrine. It includes:
- Four Noble Truths ✅
- Nine Principles ✅
- Eightfold Lenses ✅
- 12 Agents (with descriptions) ✅
- VIX-scaled Disruptor (5 levels) ✅
- Bias awareness (8 biases) ✅
- Avatars ✅
- Fractal awareness ✅
- Reflection dial ✅
- First Principles Protocol ✅
- Despair Loop Detection ✅
- Shu-Ha-Ri ✅
- Prime Directive ✅
- Playbook hierarchy context ✅
- Output protocol ✅

**Missing from ROUTINE_MODE_SYSTEM_PROMPT**:
- Echo Inception Protocol
- Sovereign Reflection Rights
- Convexity Triad
- Bias Transparency Config
- Echelon Recovery
- Structure-Loss Halt Rule

---

## 5. Deprecated Logic to Remove

| Item | Location | Reason |
|------|----------|--------|
| `CONVEXITY_WAY` dict | path_os.py | Domain playbook, not kernel |
| `FATTAIL_CAMPAIGNS` dict | path_os.py | Domain playbook, not kernel |
| `CONVEXITY_HUNTER` dict | path_os.py | Domain playbook, not kernel |
| `TAIL_RISK_TRADING` dict | path_os.py | Domain playbook, not kernel |
| `TRADE_JOURNALING` dict | path_os.py | Domain playbook, not kernel |
| `get_hunter_regime()` | path_os.py | Domain-specific |
| `get_fattail_campaign()` | path_os.py | Domain-specific |
| `ROUTINE_MODE_SYSTEM_PROMPT` | routine_briefing.py | Replaced by PathRuntime + kernel |
| `RoutineBriefingSynthesizer._synthesize_assistant()` | routine_briefing.py | Assistants API dropped |
| `RoutineBriefingSynthesizer._synthesize_chat()` | routine_briefing.py | Direct httpx calls replaced by kernel |
| `Synthesizer._synthesize_assistant()` | synthesizer.py | Assistants API dropped |
| `Synthesizer._synthesize_chat()` / `_synthesize_chat_with_system()` | synthesizer.py | Direct httpx calls replaced by kernel |
| Per-capability validation | journal/service.py, playbook/service.py | Moved to kernel post-LLM |

---

## 6. Migration Path

1. **PathRuntime** loads all `/Users/ernie/path/*.md` files at boot
2. Classifies as `kernel_doctrine` / `kernel_assets` / `playbook`
3. Extracts enforceable invariants from markdown into runtime constraints
4. `path_os.py` becomes a reconciliation reference only — not imported by kernel or capabilities
5. `ROUTINE_MODE_SYSTEM_PROMPT` replaced by `PathRuntime.get_base_kernel_prompt()` + outlet prompt
6. All 5 LLM call paths route through `VexyKernel.reason()` with unified validation

---

*Generated: 2026-02-12 | Vexy Cognitive Kernel v1 — Phase 0*
