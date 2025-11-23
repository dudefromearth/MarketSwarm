# MarketSwarm – Vexy AI Play-by-Play Architecture  
**Version 1.0 — November 2025**  
**Authors:** Ernie & Conor  
**Status:** Canonical Design Document

---

## 1. Mission Statement

Vexy AI is the **live, human-like voice** of the trading day.  
It speaks only when something meaningful happens — never noise, never filler.  
Every word is derived from **two rivers of truth**:

1. **Intel River** – curated macro, news, economic calendar  
2. **Market River** – SPX options chain + derived gamma/vol data

Vexy delivers **epoch commentary** (scheduled) and **event commentary** (unscheduled) — published to a single Redis channel: `vexy:playbyplay`.

---

## 2. High-Level Pipeline

```mermaid
graph TD
    A[Economic Calendar<br/>Macro Aggregates] --> B[rss_agg]
    B --> C[vexy:intake<br/>(Intel River)]
    D[massive] --> E[sse:chain-feed<br/>(Market River)]
    C --> F[Vexy AI Orchestrator]
    E --> F
    F --> G[vexy:playbyplay<br/>(market-redis)]
    G --> H[FrontEndNode SSE]
    H --> I[All Browsers Live]
```

---

## 3. The Two Rivers — Canonical Data Sources

| River     | Source Service | Redis Channel           | Cadence       | Primary Content                                      | Future Expansion                     |
|-----------|----------------|--------------------------|---------------|------------------------------------------------------|---------------------------------------|
| Intel     | `rss_agg`      | `vexy:intake`            | 2–8 minutes   | Enriched Markdown + metadata + provenance            | Economic calendar, macro aggregates   |
| Market    | `massive`      | `sse:chain-feed`         | Every 10s     | Full SPX options chain + spot + GEX/vol profiles     | Gamma alerts, skew, term structure    |

---

## 4. Vexy AI Service Structure

```
services/vexy_ai/
├── main.py                 ← Entry point (identical pattern to rss_agg)
├── setup.py                ← Truth loading & validation
├── intel/
│   ├── orchestrator.py     ← 60-second loop
│   ├── epochs.py           ← Immutable daily schedule
│   ├── events.py           ← Real-time event detection engine
│   └── publisher.py        ← Single source of speech
└── scripts/
    └── ms-vexyai.sh        ← Menu-driven launcher (identical to ms-rssagg.sh)
```

---

## 5. Epoch Commentary — The Rhythm of the Trading Day

| Time (ET) | Epoch Name               | Condition                     | Example Commentary                                      |
|-----------|--------------------------|-------------------------------|----------------------------------------------------------|
| 08:00     | Premarket                | Always                        | "This is Premarket on 2025-11-20..."                    |
| 08:35     | Post-Reports Premarket   | After major data release      | "CPI just printed hot — premarket reaction underway..." |
| 09:35     | Post-Open                | Always                        | "The bell has rung. Market opening with conviction..."  |
| 11:30     | European Close           | Always                        | "Europe is done for the day..."                        |
| 13:00     | Lunch Vol Crush          | Always                        | "Vol is collapsing into lunch..."                       |
| 14:00     | Commodity Shadow         | Always                        | "Commodity markets entering shadow close..."           |
| 15:00     | Power Hour Begins        | Always                        | "We are now in Power Hour — final stretch begins..."   |
| 15:50     | Into the Close           | Always                        | "Ten minutes to the bell — into the close..."           |
| 16:01     | Post-Close Wrap          | Always                        | "The day is over. Here’s what mattered..."              |

---

## 6. Event Commentary — The Market’s Reflexes

| Trigger Type         | Source       | Example Commentary                                      |
|----------------------|--------------|----------------------------------------------------------|
| Gamma Squeeze        | massive      | "Extreme positive GEX flip — gamma squeeze in progress" |
| Volume Spike         | massive      | "Unusual 0DTE call volume — dealers scrambling"         |
| Macro Shock          | rss_agg      | "FOMC just hiked 50bps — bearish surprise"              |
| Skew Inversion       | massive      | "Put skew just exploded — tail risk rising fast"         |
| Spot Anomaly         | massive      | "SPX just broke 4500 on no volume — trap forming"        |

---

## 7. Output Contract — `vexy:playbyplay` Payload

```json
{
  "kind": "epoch|event",
  "text": "This is Power Hour Begins on 2025-11-20...",
  "meta": {
    "epoch": "Power Hour Begins",
    "type": "gamma_squeeze",
    "symbol": "SPX",
    "level": "critical"
  },
  "ts": "2025-11-20T19:00:00Z",
  "voice": "anchor"
}
```

---

## 8. Core Design Principles (Immutable Law)

1. **One voice, one channel** — `vexy:playbyplay` on market-redis
2. **First principles only** — if you can’t explain it in one sentence, it’s wrong
3. **Redis is truth** — no local state, no files, no drift
4. **Logging standard** — `[timestamp] [vexy_ai|step] message`
5. **Healer watches everything** — Vexy is immortal
6. **Documentation is law** — every file has purpose, notes, future guidance
7. **All design documents in Markdown** — drop-in ready for Obsidian/Notion

