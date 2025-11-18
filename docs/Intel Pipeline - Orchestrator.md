# 📘 DOCUMENT #2 — ORCHESTRATOR INSPECTION & VERIFICATION

**Version:** 1.0
**Status:** Draft (Pending Instrumentation)
**Owner:** Architecture
**Purpose:**
* Inspect and verify the orchestrator against the System Overview
* Identify design drift, violations, and regressions
* Define required instrumentation and corrections
* Freeze behavioral contracts before modifying anything

⠀
⸻

# 1. PURPOSE OF THE ORCHESTRATOR

The orchestrator is the **system coordinator** that launches and manages:
1. RSS ingestion (Tier-1)
2. Raw article fetching (Tier-0 HTML)
3. Canonicalization + enrichment (Tier-0 → Tier-3)
4. Publisher (Tier-4)

⠀
Its responsibility is **only scheduling and coordination**, not data transformation.

⸻

# 2. EXPECTED BEHAVIOR (From Document #1)

The orchestrator must:

### 2.1 Launch EXACTLY FOUR concurrent loops
```bash
1. start_workflow            → ingest RSS -> rss:item
2. schedule_article_fetching → fetch HTML -> rss:article_raw
3. schedule_article_enrichment → build canonical + enriched
4. schedule_feed_generation → produce category feeds
```
### 2.2 Load configuration and truth
* Must load feeds.json
* Must read truth.json for redis routing
* Must connect to intel-redis and system-redis

⠀
### 2.3 Maintain strict stage boundaries

No mixing of responsibilities.

### 2.4 Initialize nothing beyond its own operation

Initialization belongs to setup scripts, not orchestrator.

⸻

# 3. ACTUAL IMPLEMENTATION — Inspection

Below is the orchestrator as you provided.
We inspect the code **as-is**, in six structural blocks.

⸻

### 3.1 Imports & Dependencies
```python
from .ingestor import ingest_all
from .publisher import generate_all_feeds
from .article_ingestor import enrich_articles
from .article_fetcher import fetch_and_store_article
```
### Verification
* All four major pipeline components are imported.
* The fetcher import matches the intended Tier-0 system.

⠀
### Deviation
* ingestor appears to be using the old URL-extraction path.
* Must inspect later.

⠀
⸻

### 3.2 load_feeds_config()

### Verified:
* Correct three-tiered lookup (env → local → docker).
* Fulfills config contract.

⠀
### Issue:
* No verification log.
* No explicit failure mode (besides FileNotFoundError).
* Should emit diagnostic boundaries per Document #1.

⠀
⸻

### 3.3 schedule_feed_generation()

### Verified:
* Publishes feeds in a loop.
* Uses asyncio.to_thread() correctly for CPU-bound XML generation.

⠀
### Issues:
* No READ/WRITE boundary logs.
* No category reporting.

⠀
⸻

### 3.4 schedule_article_fetching()

This is a critical component. Let’s break it down:

### Expected Behavior (spec):
* Must fetch HTML only for **true external links**
* Must never fetch Google/Microsoft redirect chains
* Must ONLY fetch URLs that came from **post-unwrap** RSS items

⠀
### Actual Code Behavior:
```python
uids = await r.zrevrange("rss:index", 0, 50)
```
* Pulling from the same index as ingestor, correct.
```python
raw_key = f"rss:item:{uid}"
html_key = f"rss:article_raw:{uid}"
```
* Correct: raw HTML is separate.
```python
if await r.exists(html_key):
    continue
```
* Correct: skip already-fetched items.

⠀
### CRITICAL BREAK IN CONTRACT

You said:

Google feeds must be stripped and replaced with extracted URLs.

But the orchestrator does not verify this.
It blindly trusts that rss:item:{uid} contains a correct unwrapped URL.

**Therefore the orchestrator may fetch Google links**, because ingestor may be producing these items incorrectly.

### Required verification:
* Log the URL being fetched
* Flag any URL containing:
  * google.com/url?
  * msn.com/redirect
  * known aggregator masks

⠀
Right now we cannot tell if orchestrator is receiving bad input, or fetcher is failing.

⸻

### 3.5 schedule_article_enrichment()

### Verified:
* Enrichment loop runs separately.
* Wraps errors correctly.

⠀
### Issues:
* No boundary logs.
* No canonicalization guarantee.

⠀
⸻

### 3.6 start_workflow() (RSS ingest)

### Verified:
* Correct RSS → items loop.

⠀
### Issues:
* No verification that *unwrap* is being performed.
* No verification that canonical article fetch begins only *after ingest_all* has populated the minimal items.
* No diagnostics showing item URLs.

⠀
This is likely why the system ingests Google redirect URLs.
We simply never instrumented that stage.

⸻

### 3.7 run_orchestrator() Entrypoint

### Verified:
* Correct use of asyncio.gather().
* Launches all loops concurrently.

⠀
### MAJOR PROBLEM:

You have **two run_orchestrator definitions** in the same file:
```python
async def run_orchestrator(svc, setup_info, truth):
    ...
    # Start all parallel pipeline stages
    await asyncio.gather(...)
    )

# Then again inside the same file:
async def run_orchestrator(svc, setup_info, truth):
    ...
    await asyncio.gather(...)
```
One overwrites the other at import time.

This is a major systemic regression.

This may cause:
* incomplete pipeline activation
* old loops running
* duplicated logic
* or orphaned fetchers
* or loss of Google-unwrapping

⠀
This explains recent behavior.

### Status:

**FAIL: Orchestrator has redundant overwritten entrypoints.
Needs immediate cleanup.**

⸻

# 4. SUMMARY OF VERIFIED FAILURES
| **Component** | **Verified Issue** |
|:-:|:-:|
| orchestrator entrypoint | **DUAL DEFINITION** – one overwrites the other |
| URL quality | No validation on orchestrator side |
| Boundary logging | Missing in all stages |
| Google redirect filtering | Not validated |
| stage correctness | No READ/WRITE logging |
| scheduler lifecycle | No startup diagnostics |
| downstream impacts | fake “no canonical items”, garbage feeds |


⸻

# 5. NEXT STEPS (Per Your Process)

Your rule:

Once a step has been verified, it cannot be changed without re-verification.

Given that:
1. The orchestrator has two definitions → **must be fixed FIRST**
2. The orchestrator does not verify ingest → **must be instrumented FIRST**
3. Google/MSN links must be validated at ingest stage → **must confirm actual values**

⠀
### Therefore the next step is:

**Insert instrumentation in orchestrator ONLY.
No logic changes yet.
Just READ/WARN/ERROR logs to reveal the truth of what is happening.**

You want the system to **self-diagnose** on startup.

⸻

# 6. READY FOR NEXT ACTION

If you confirm:

**I will now produce “Document #3 — Orchestrator Instrumentation Patch”**,
which includes:
* Diagnostic logging spec
* Exact instrumentation points
* Code patch (no logic alterations)
* Output format
* Verification procedure