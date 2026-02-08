# ## Risk Graph ↔ Dealer Gravity Live Backdrop Binding

### Source-of-Truth Requirement

The Dealer Gravity service is the **authoritative source of truth** for all
Volume Profile, GEX, and Structural Analysis data.

The Risk Graph does **not** compute, cache, or reinterpret Dealer Gravity
structures independently.

It **subscribes** to Dealer Gravity outputs.

---

### Live Binding Requirement

The Dealer Gravity backdrop rendered inside the Risk Graph must be **live-bound**
to the Dealer Gravity tool.

This means:

- If structural analysis changes in the Dealer Gravity app
- If AI analysis is re-run
- If configuration affecting structure is modified
- If new data alters detected structure

Then:

> **The Risk Graph backdrop must update automatically to reflect those changes.**

No manual refresh.  
No duplicated logic.  
No stale state.

---

### Synchronization Mechanism

Dealer Gravity must emit **real-time update events** (e.g. via SSE or equivalent)
whenever any of the following change:

- Volume Profile structure
- GEX structure
- Structural lines (Volume Nodes, Volume Wells, Crevasses, etc.)
- Analysis version or timestamp

Risk Graph must:

- Subscribe to the Dealer Gravity update stream
- Re-render the backdrop layers when updates arrive
- Preserve the Risk Graph’s own zoom, scale, and interaction state

---

### Data Ownership & Flow
```text
Dealer Gravity (authoritative)
├─ computes structure
├─ runs AI analysis
├─ emits visualization artifacts
└─ publishes update events
↓
Risk Graph (consumer)
├─ receives artifacts
├─ projects onto its price scale
└─ renders as backdrop
```
Risk Graph **never**:

- Re-runs Dealer Gravity analysis
- Infers structure on its own
- Mutates Dealer Gravity outputs

---

### Structural Lines Consistency

Structural lines rendered in the Risk Graph must be:

- Identical to those shown in the Dealer Gravity app
- Derived from the same analysis version
- Updated atomically when Dealer Gravity updates

This ensures:

- Visual consistency across tools
- Analytical trust
- Reproducibility in review and journaling

---

### Operator Experience Guarantee

From the operator’s perspective:

- Dealer Gravity is adjusted or re-analyzed
- Risk Graph **immediately reflects** the new structure
- The operator does not need to reconcile discrepancies
- Context follows analysis automatically

---

### Explicitly Not Allowed

- Risk Graph caching structural data independently
- “Snapshot” copies of Dealer Gravity structure
- Manual refresh buttons for backdrop sync
- Divergent representations of structure across tools

---

### Summary Statement

> The Dealer Gravity backdrop in the Risk Graph is a live, service-bound context layer.  
> Dealer Gravity owns structure; Risk Graph renders it.  
> Any change in Dealer Gravity must be reflected immediately and faithfully in the Risk Graph.

This requirement is **architectural and non-optional**.
