# # 📘 Executive Summary — Vexy Architecture & Subscription Model

**Vexy** is the sovereign intelligence at the center of each MarketSwarm instance.
She is not a bot. Not a data feed.
She is a **floor-level guide**, standing next to the trader inside a real-time environment built from:
* **GEX (Gamma Exposure)**
* **Convexity Heat Map**
* **Volume Profile**
* **VIX Regime**
* **Market Mode**
* **Directional Bias**
* **LFI (Liquidity Flow Index)**

⠀
Vexy watches every widget, every economic event, every contextual regime, and every structural shift — and narrates the trading day the way a senior floor-trader would: short, clear, confident, and constantly aware of the “structure under the surface.”

Her job is simple:

### Guide the trader. Frame the tension. Point to the structure. Deliver clarity.

Vexy speaks in *three voice flavors* (Observer, Activator, Navigator) and supports *three trader skill levels* (Beginner, Initiated, Professional).
**But the subscription tier determines how much of her intelligence the user can see.**

⸻

# 🏛️ Subscription Tiers

### 1. Observer (Free Tier)

The learning tier — ideal for newcomers.

**Includes:**
* Full Vexy voice (Beginner → Professional selectable)
* Rolling TL;DR message feed
* Limited widget access (non-interactive)
* Basic Discord *Observer Support* channel

⠀
**Redactions:**
* Advanced insights blurred
* “Navigator Only” label displayed
* *Upgrade link included*

⠀
**No access to:**
* Advanced coaching
* Strategy overlays
* Outcome learning
* 0-DTE or group coaching rooms

⠀
⸻

### 2. Activator (Trader Tier)

The full **tool access** tier — for active traders.

**Includes:**
* All widgets unlocked (GEX, Heat Map, VIX, LFI, Bias, Market Mode)
* Full interactivity + data resolution
* Complete TL;DR + full reports (no redaction)
* Discord access to **FOTW channels**
* Weekly livestreams
* Strategy signals
* Economic calendar insights
* Widget-triggered alerts

⠀
**Does NOT include:**
* Group coaching
* Daily livestream
* 0-DTE room
* Deep learning or outcome feedback

⠀
**Activator gets the tools — but not the tribe.**

⸻

### 3. Navigator (Elite Coaching Tier)

The **full-immersion** tier — the trading floor.

**Everything Activators get**, plus:

### 🔥 Human Access
* Daily livestream
* Group coaching
* Daily Q&A
* Office hours
* 0-DTE trade room
* Private Navigator chat

⠀
### 🧠 Intelligence Access
* Unredacted advanced overlays
* Convexity scoring
* Strategy probability bands
* Journaling + outcome learning
* Vexy’s advanced chain analysis
* Personalized coaching feedback

⠀
Navigator is where the full MarketSwarm ecosystem comes alive.

⸻

# 🎙️ Persona Modes (Voice Flavors)

Vexy can speak in three voice styles:

### 1. Observer

Calm, descriptive, explanatory.

### 2. Activator

Focused, motivational, attention-steering.

### 3. Navigator

Strategic, expert-level, regime-aware.

⸻

# 📚 Trader Skill Levels

These control Vexy’s *language*, not her access.

### Beginner
* Plain language
* No jargon
* Guided explanations

⠀
### Initiated
* Some terminology
* Balanced explanations

⠀
### Professional
* Full technical vocabulary
* Floor-trader shorthand
* Assumes market literacy

⠀
⸻

# 🧠 How Vexy Generates Messages

Each message moves through **three layers**:

### 1. Core Intelligence Layer
* Economic events
* Widget states
* Market structure
* Contextual regimes
* GEX/VIX/Bias/LFI
* Heatmap patterns

⠀
### 2. Tier Filter (What the user can see)
* Observer → blurred advanced intel
* Activator → all tools unlocked
* Navigator → full depth + coaching overlays

⠀
### 3. Persona + Skill Layer (How it is said)
* Observer / Activator / Navigator
* Beginner / Initiated / Professional

⠀
⸻

# 🕘 Three Message Types

### 1. Epoch Messages (Time-Based)

Daily rhythm:
* Premarket
* Post-Open
* European Close
* Lunch Vol Crush
* Power Hour
* Into the Close
* **Session Conclusion (Final Message of the Day)**

⠀
TL;DR style, timestamped, with a clear guiding sentence.

⸻

### 2. Event Messages (Impact-Based)

Triggered by:
* Economic releases
* Market anomalies
* Contextual regimes
* Widget thresholds
* Seasonal flows

⠀
**Includes:**
* Header with flame rating (🔥1–5)
* Timestamp with emoji (📅 | 🕒)
* Vexy’s Take (guiding sentence)
* 3–5 key bullets
* Mini table
* Optional chart
* Widget overlays
* Full report link

⠀
⸻

### 3. Widget Messages (Structural Signals)

Generated when:
* GEX crosses thresholds
* VIX enters new regime
* Heatmap detects pressure
* LFI trends
* Bias shifts
* Market Mode changes

⠀
Short, powerful, floor-trader commentary:

“Negative GEX deepening — hedging flows loosening the tape. Eyes on 6750–6735.”

⸻

# 📅 Calendar & Impact System

Every trading day merges:
* **Daily Epochs**
* **Contextual Regimes**
* **Economic Events (impact 1–5 flames)**
* **Widget State Overlay**
* **Session Conclusion**

⠀
This drives Vexy’s entire narrative loop.

⸻

# 🎛️ UX Overview

At login, users choose:
* Subscription Tier
* Persona Flavor
* Skill Level

⠀
Vexy adapts instantly.

Observer-level users see:
* Blurred content
* “Navigator Only” labels
* Upgrade option
* TL;DR guidance

⠀
Activators see:
* Full tool access
* Full reports
* Intermediate coaching context

⠀
Navigators see:
* Everything
* Coaching
* Deep insights
* Full ecosystem

⠀
All persona switches are logged to Echo for continuity.

⸻

# 🌀 Positioning Statement

**Vexy is a sovereign trading partner.**
She stands on the digital trading floor with the user — watching GEX, volatility, convexity, flows, bias, and liquidity in real time.
She speaks in clear, human language and helps the trader navigate the structure of the day with confidence and clarity.

Vexy embodies The Path:
**Reflection → Clarity → Action.**

And she grows alongside the trader.

# 📘 Vexy Calendar & Event Schema (v1.0)

**Master Schema used by Vexy AI for all session orchestration**
```json
{
  "version": "1.0",
  "description": "Canonical calendar, event, and widget schema for Vexy AI.",
  "days": {
    "YYYY-MM-DD": {
      "daily_epochs": [
        {
          "name": "Premarket",
          "time": "08:00",
          "prompt_mode": "tldr",
          "persona_modes": ["observer", "activator", "navigator"]
        },
        {
          "name": "Post-Open",
          "time": "09:35",
          "prompt_mode": "tldr",
          "persona_modes": ["observer", "activator", "navigator"]
        },
        {
          "name": "European Close",
          "time": "11:30",
          "prompt_mode": "tldr"
        },
        {
          "name": "Lunch Vol Crush",
          "time": "13:00",
          "prompt_mode": "tldr"
        },
        {
          "name": "Power Hour",
          "time": "15:00",
          "prompt_mode": "tldr"
        },
        {
          "name": "Into the Close",
          "time": "15:50",
          "prompt_mode": "tldr"
        },
        {
          "name": "Session Conclusion",
          "time": "16:10",
          "is_final": true,
          "include": {
            "retrospective": true,
            "forward_preview": true,
            "echo_summary": true
          }
        }
      ],

      "contextual_regimes": [
        {
          "name": "Thanksgiving Week",
          "priority": 7,
          "phase": "during",
          "notes": "Low liquidity; holiday flows."
        },
        {
          "name": "FOMC Day",
          "priority": 10,
          "phase": "during",
          "notes": "Rate decision at 2pm ET."
        }
      ],

      "economic_events": [
        {
          "name": "CPI",
          "impact": 9,
          "time": "08:30",
          "category": "inflation",
          "flame_rating": 5,
          "url": "https://www.bls.gov/",
          "phase_prompts": {
            "pre": "Explain consensus, probable volatility, and structure.",
            "post": "Compare actual vs forecast; interpret flows and structure shifts."
          }
        }
      ],

      "widget_overlays": {
        "GEX": {
          "regime": "negative",
          "value": -6200000,
          "key_levels": [6735, 6720, 6750],
          "thresholds": {
            "warn": -5000000,
            "critical": -10000000
          }
        },
        "Heatmap": {
          "pressure_zones": ["puts_6720", "calls_6750"],
          "cheap_strikes": [6730, 6720],
          "otm_intensity": 0.78
        },
        "MarketMode": {
          "intraday": {
            "regime": "normal",
            "percentile": 78,
            "vwap_distance": 0.3
          },
          "multiday": {
            "window": "10D",
            "compression_level": "medium"
          }
        },
        "VIXRegime": {
          "regime": "Goldilocks",
          "range_low": 30,
          "range_high": 40,
          "baf_width": 13.25
        },
        "BiasLFI": {
          "bias": 70,
          "lfi": 20,
          "quadrant": "Air-pocket risk"
        }
      },

      "widget_events": [
        {
          "widget": "GEX",
          "trigger": "cross_warn_threshold",
          "commentary_mode": "tldr",
          "severity": "warning",
          "vexy_prompts": {
            "short": "Describe shift in dealer flow and volatility posture.",
            "long": "Explain expected implications for intraday expansion probability."
          }
        }
      ],

      "system": {
        "persona_mode": {
          "flavor": "navigator",
          "experience": "professional"
        },
        "tier": "activator"
      }
    }
  }
}
```

⸻

# 📌 Schema Field Definitions

Below is the human-readable breakdown.

### 1. daily_epochs

Fixed, time-based, recurring market rhythm.

Each epoch includes:
* name
* time
* prompt_mode
* persona compatibility
* optional is_final

⠀
### 2. contextual_regimes

Seasonal or market structure conditions.

Each includes:
* name
* priority (to resolve conflicts)
* phase (before / during / after)
* notes

⠀
### 3. economic_events

Market-moving scheduled events.

Each includes:
* name
* category
* time
* impact score (0–10)
* flame rating (1–5)
* URLs
* pre/post prompts

⠀
These trigger **pre-event** and **post-event messages**.

### 4. widget_overlays

Snapshot of widget states at the moment of message generation:
* GEX
* Convexity Heatmap
* Market Mode (intraday + multiday)
* VIX Regime
* Bias + LFI Quadrant

⠀
### 5. widget_events

Triggered when widget values cross thresholds.

Includes:
* widget name
* trigger condition
* severity
* Vexy prompt guidance

⠀
### 6. system

Defines the persona + voice + tier of the user for that session.