# # 📘 DOCUMENT #1 — SYSTEM OVERVIEW (MarketSwarm Intelligence Pipeline)

**Version:** 1.0
**Status:** Draft (to be validated against live orchestrator logs)
**Owner:** Architecture
**Audience:** Engineering, Operations, AI Systems, DevOps
**Purpose:** Establish a formal, authoritative description of the entire system, independent of the codebase, so implementations can be verified, maintained, and governed without regression.

⸻

# 1. PURPOSE OF THE SYSTEM

MarketSwarm is an end-to-end *news intelligence pipeline* designed to:
1. **Ingest upstream RSS feeds** (Tier-1 external sources)
2. **Extract the true article URLs**
3. **Fetch & normalize raw article HTML**
4. **Canonicalize into a Tier-0 structured article** (text-only, HTML-free)
5. **Enrich with intelligence metadata (Tier-3)**
6. **Generate premium, multi-layer RSS outputs (Tier-4)**
7. **Generate a Tail-Event Detector feed**
8. **Expose all artifacts to downstream systems (Vexy, agents, UI)**

⠀
The system is architected for:
* **Determinism**
* **Transparency**
* **Zero regressions**
* **Traceable transformations**
* **Full pipeline observability**

⠀
This document describes *what the system is*, not how any specific version behaves.
All implementations must conform to this document.

⸻

# 2. MACRO ARCHITECTURAL OVERVIEW

MarketSwarm is composed of **four subsystems** running in parallel:

⸻

### 2.1 Upstream Ingest Subsystem

**Objective:** Convert third-party RSS feeds into MarketSwarm’s internal event model.

**Responsibilities:**
* Poll upstream RSS feeds
* Extract source items
* Unwrap Google/MSN redirect URLs
* Generate Tier-1 Minimal Items
* Store into:
  * rss:item:{uid}
  * rss:index
  * rss:seen
  * rss:queue

⠀
**Input:** upstream RSS URLs
**Output:** Tier-1 minimal RSS items

⸻

### 2.2 Raw Article Fetch Subsystem (Tier-0 HTML Capture)

**Objective:** Convert URLs into HTML snapshots using headless browser fetch.

**Responsibilities:**
* Read UIDs from rss:index
* For each UID:
  * Fetch article HTML
  * Store canonical raw snapshot into rss:article_raw:{uid}
  * Add to rss:article_raw:index

⠀
**Input:** Tier-1 items
**Output:** raw HTML snapshot

This boundary **must be immutable** unless versioned.

⸻

### 2.3 Article Canonicalization + Enrichment (Tier-0 → Tier-3)

**Objective:** Convert HTML into a structured, normalized article substrate.

### Tier-0 Canonicalizer
* Strip **all HTML**
* Extract text
* Extract abstract
* Extract image
* Extract domain
* Store canonical record into:
  * rss:article_canonical:{uid}

⠀
### Tier-3 AI Enricher
* Summarization
* Sentiment
* Entities
* Tickers
* Takeaways
* Headlines
* Quality scoring
* Cluster membership
* Category override

⠀
**Output:** Tier-3 final structured articles (rss:article:{uid})

⸻

### 2.4 Publisher Subsystem (Tier-4 Output Feeds)

**Objective:** Generate Bloomberg-grade enriched RSS outputs.

**Responsibilities:**
* Merge canonical + enriched
* Generate category context blocks (AI-generated)
* Generate Tail-Event feeds
* Strict XML generation
* Write to publish directory

⠀
**Output:**
* /feeds/{category}.xml
* /feeds/tail_events.xml

⠀
⸻

# 3. DATAFLOW PIPELINE (END-TO-END)
```text
[External RSS] 
     ↓
[ingestor.py] 
     ↓ generates rss:item:{uid}, rss:index, rss:queue
[article_fetcher.py]
     ↓ generates rss:article_raw:{uid}
[article_schema.py]
     ↓ generates rss:article_canonical:{uid}
[article_ingestor.py]
     ↓ generates rss:article:{uid}
[publisher.py]
     ↓ generates category feeds + tail events
```
**Every arrow is a boundary.**
**Every boundary is a contract.**

⸻

# 4. REDIS KEYSPACE OVERVIEW

This is the authoritative high-level summary (expanded in Document #4):

### Tier-1 Items
```text
rss:item:{uid}
rss:index
rss:seen
rss:queue
```
**Tier-0 Raw Articles**
```text
rss:article_raw:{uid}
rss:article_raw:index
```
**Tier-0 Canonical**
```text
rss:article_canonical:{uid}
```
**Tier-3 Enriched**
```text
rss:article:{uid}
rss:article:index
```
**Publisher Outputs**

Files written to:
```text
/Sites/feeds/{category}.xml
/Sites/feeds/tail_events.xml
```

⸻

# 5. ORCHESTRATOR ARCHITECTURE

The orchestrator is the *system-of-systems* coordinator.

It launches four continuous loops:
```bash
1. start_workflow             (RSS ingest)
2. schedule_article_fetching  (raw HTML capture)
3. schedule_article_enrichment (canonical + enrichment)
4. schedule_feed_generation   (publisher)
```
All four run concurrently to form a full pipeline.

⸻

# 6. SYSTEM RESPONSIBILITY MATRIX
| **Subsystem** | **Role** | **Input** | **Output** |
|:-:|:-:|:-:|:-:|
| Ingestor | RSS ingestion + URL unwrap | External feed | rss:item:* |
| Fetcher | Fetch HTML | rss:item | rss:article_raw |
| Canonicalizer | Normalize | raw_html | canonical article |
| Enricher | AI metadata | canonical text | enriched article |
| Publisher | Tier-4 RSS | enriched articles | XML feeds |
| Orchestrator | Scheduler/Coordinator | truth + configs | pipeline execution |

⸻

# 7. BOUNDARY CONTRACTS

These are the rules you defined as *absolute*:

**Rule 1: Once a component is verified, it is immutable.**

No modifications without version bump + full pipeline revalidation.

**Rule 2: No stage may read from a downstream stage.**

Only forward flow allowed.

**Rule 3: Every stage must emit explicit logs for:**
```text
READ
WRITE
TRANSFORM
SKIP
ERROR
```
This allows self-diagnosis.

**Rule 4: No HTML may cross the Tier-0 → Tier-3 boundary.**

⸻

# 8. SELF-DIAGNOSTIC REQUIREMENTS

Each module must emit:
```json
[module] [READ] key=X
[module] [WRITE] key=Y fields=[...]
[module] [SKIP] reason=Z
[module] [ERROR] reason=E
```
This forms a traceable pipeline.

We will insert these logs during orchestrator verification.

⸻

# 9. SYSTEM GUARANTEES

When all components conform:
* No Google redirect URLs can ever propagate downstream
* No HTML ever enters enriched feeds
* All RSS output is deterministic
* Every item is traceable from Tier-4 back to Tier-1
* Orchestrator shows complete real-time pipeline diagnostics
* Regressions become impossible

⠀
⸻

# 10. NEXT STEP

Per your instruction:

**We now examine the orchestrator, document it, and verify correctness line-by-line against this document.
We will then insert instrumentation that aligns with the boundary contracts and diagnostics rules.**
