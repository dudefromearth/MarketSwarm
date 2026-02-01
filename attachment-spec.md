# Fly on the Wall (FOTW) — Journal Attachment UI Specification

## 1. Purpose & Role

**Role:**  
Attachments preserve *what the trader saw* at the time of reflection.

They are memory artifacts, not presentation assets.

Attachments exist to:
- capture charts, screenshots, and reference material
- preserve historical context
- support written reflection

Attachments do **not**:
- organize knowledge
- decorate entries
- replace written reflection
- act as analysis tools

Text remains primary. Attachments are secondary.

---

## 2. Core Design Principles

- **Low friction:** Attachments must be quick to add
- **Non-disruptive:** Writing flow must never be interrupted
- **Secondary emphasis:** Attachments never dominate the journal entry
- **Snapshot integrity:** Attachments are frozen in time
- **No ceremony:** No required metadata, captions, or workflows

---

## 3. Attachment Placement

Attachments are displayed in a **dedicated attachment area** associated with the journal entry.

### Placement Rules
- Attachments appear **below the main text editor** or in a **subtle side gutter**
- The attachment area may be collapsed by default
- Attachments never appear above the journal text
- Attachments do not auto-insert inline

This preserves writing as the primary activity.

---

## 4. Attachment Ingestion Methods

Attachments may be added through any of the following methods:

### 4.1 Drag & Drop
- Files can be dragged anywhere into the editor area
- Drop location does not affect placement
- Attachment is added silently to the attachment area

---

### 4.2 Clipboard Paste
- Screenshots pasted from the clipboard are accepted
- Pasted content is treated as an attachment by default
- No inline image insertion occurs automatically

---

### 4.3 Attach Action
- A small, non-prominent “Attach” affordance is available
- Located in the editor footer or toolbar
- No call-to-action language is used

---

## 5. Attachment Display (Tile Model)

Each attachment is displayed as a **tile**, not an embed.

### Attachment Tile Contents
- Thumbnail preview (for images)
- File icon (for non-image files)
- Truncated filename
- Optional timestamp (subtle)

### Display Constraints
- Tiles are uniform in size
- Tiles do not expand the editor layout
- No captions are required

Attachments are visible, but quiet.

---

## 6. Inline References (Optional, User-Initiated)

If a trader wishes to reference an attachment inline:

- A lightweight “Insert Reference” action is available on the attachment tile
- This inserts a text reference at the cursor location, e.g.:

```text
[Chart snapshot – SPX 5m]