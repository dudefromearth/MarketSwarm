## Risk Graph — Dealer Gravity Backdrop Requirements

### Conceptual Clarification

Dealer Gravity visual elements are rendered as a **backdrop** to the Risk Graph,  
**not** as an overlay and **not** as a separate chart.

The Risk Graph remains the **primary analytical object**.

Dealer Gravity provides **contextual background structure** only.

---

### Backdrop Components (Independently Toggleable)

The operator must be able to independently enable or disable the following
Dealer Gravity backdrop layers:

1. **Volume Profile (VP) Backdrop**
2. **Gamma Exposure (GEX) Backdrop**
3. **Structural Lines Backdrop** (AI-derived structure)

Each component is controlled by a dedicated toggle.

---

### Required Operator Controls

| Control | Description |
|------|------------|
| VP Backdrop Toggle | Enables/disables Volume Profile rendering behind the Risk Graph |
| GEX Backdrop Toggle | Enables/disables Gamma Exposure rendering behind the Risk Graph |
| Structural Lines Toggle | Enables/disables AI-derived structural levels |
| Backdrop Opacity Control | Adjusts transparency to prevent visual dominance |
| Reset to Default | Restores recommended opacity and visibility settings |

---

### Rendering Rules (Non-Negotiable)

- Dealer Gravity elements **must render behind** all Risk Graph elements
- Risk Graph curves, envelopes, and markers always remain visually dominant
- Backdrops must:
  - Share the **exact same price scale**
  - Share the **exact same vertical mapping**
  - Resize and zoom in perfect sync with the Risk Graph
- Backdrops **must not** introduce:
  - Independent axes
  - Independent zoom
  - Independent layout logic

---

### Structural Lines (AI Analysis)

Structural Lines represent AI-identified market structure such as:

- Volume Nodes
- Volume Wells
- Crevasses
- Other inflection or structural levels

Rendering requirements:

- Rendered as **vertical lines**
- Aligned precisely to the Risk Graph price axis
- Low visual weight (thin stroke, muted color)
- Always subordinate to risk curves
- Toggleable independently from VP and GEX

These lines provide **structural context**, not signals.

---

### Mental Model (Authoritative)

Dealer Gravity backdrops behave like:

> Geological layers beneath a terrain map

They provide **context and memory**, not instructions.

The Risk Graph remains the **decision surface**.

---

### Explicitly Not Allowed

- VP/GEX as a foreground overlay
- VP/GEX drawn with equal or greater visual weight than risk curves
- Independent chart components inside the Risk Graph panel
- Screenshot-based or rasterized backdrops
- Any backdrop logic that can drift from the Risk Graph scale

---

### Summary Statement

> Dealer Gravity provides selectable, scale-locked, low-opacity backdrops to the Risk Graph, enabling structural and gamma context to be seen *behind* payoff geometry without competing for analytical attention.

This requirement is **architectural**, not cosmetic.