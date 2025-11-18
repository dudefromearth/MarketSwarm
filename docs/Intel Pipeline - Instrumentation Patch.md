# # 📘 Document #3 — Orchestrator Instrumentation Patch

**Version:** 1.0
**Status:** Implementation-ready
**Purpose:**
* Add deep, continuous observability into every stage of the pipeline
* Detect data regressions and architectural drift
* Validate adherence to Document #1 design rules
* Absolutely NO behavior modifications — *logging only*

⠀
⸻

# 1. OBSERVABILITY PRINCIPLES FOR THIS SYSTEM

The orchestration pipeline is complex, async, distributed across Redis, and multi-stage.
Therefore effective instrumentation must satisfy:

### 1.1 Zero logic changes
* Only logging
* No condition changes
* No flow rewrites

⠀
### 1.2 Logs must capture pipeline boundaries

For each stage:
```bash
READ from Redis
WRITE to Redis
TRANSFORM (ingestion, fetch, enrich)
SCHEDULE
SKIP (dedupe / exists)
UNEXPECTED
```
### 1.3 Logs must reveal the truth, not interpretation
* Raw URLs
* Raw keys
* Link type (first-party, Google, MSN, aggregator)
* UID integrity
* Stage durations
* Redis hits/misses

⠀
### 1.4 Logs must be human-readable but consistent

Pattern:
```text
[timestamp] [stage] [level] emoji message | metadata
```
Where metadata is JSON-encoded so it’s copy/paste friendly in terminal.

⸻

# 2. REQUIRED LOGGING POINTS

Instrumentation points by stage:

⸻

### 2.1 INGESTOR (start_workflow)

We must observe:
| **Event** | **Required Diagnostic** |
|:-:|:-:|
| Reading feed | feed URL, category |
| Parsed entry | title, link, ID |
| After unwrap | clean_url, redirect flags |
| Redis write | uid, hash fields, timestamp |
| Dedupe skip | uid |

⸻

**2.2 Raw Fetcher (schedule_article_fetching)**

Must capture:
| **Event** | **Required Diagnostic** |
|:-:|:-:|
| Selecting uid | uid, redis hit/miss |
| Item loaded | url, title, category |
| URL classification | first-party / google / msn / aggregator |
| Fetch call start | url, uid |
| Fetch result | size, status code |
| Raw HTML stored | byte count |
| Failure | reason |

⸻

### 2.3 Enricher

Must log:
* Canonical text extraction length
* Abstract presence
* LLM call boundaries
* Redis write summary

⠀
⸻

### 2.4 Publisher

Logging needed:
* Item tiers identified
* Category summaries generated
* Tail events evaluated
* Output feed length

⠀
⸻

# 3. URL CLASSIFICATION LOGIC (for visibility only)

The orchestrator must not change behavior, but must label URLs:
```python
FIRST_PARTY: normal external news link
GOOGLE_REDIRECT: *.google.com/url?
MS_REDIRECT: msn.com/* or windowscentral-style redirects
AGGREGATOR: flipboard, feedproxy, newsnow, etc
UNKNOWN: else
```
This will reveal whether ingest is providing correct URLs.

⸻

# 4. NEXT: CODE PATCH

### ✔ Only logs added

### ✔ No logic changed

### ✔ All changes traceable

### ✔ Self-diagnostic on every loop start

⸻

# 5. INSTRUMENTATION CODE PATCH (apply to orchestrator.py)

**Note:** You don’t need to apply this manually.
Say *“apply patch”* when ready, and I’ll perform a full oboe.edit_file patch.

Below is the exact instrumentation we will add:

⸻

### 5.1 Helper: URL Classification
```python
def classify_url(url: str):
    if "google.com/url" in url:
        return "GOOGLE_REDIRECT"
    if "msn.com" in url:
        return "MS_REDIRECT"
    if any(x in url for x in ["feedproxy", "flipboard", "newsnow", "ampproject"]):
        return "AGGREGATOR"
    return "FIRST_PARTY"
```

⸻

**5.2 Instrumentation in start_workflow()**

Add:
```python
print(f"[ingest] 🟦 Feed ingestion start for {svc}")

print(f"[ingest] 📥 Entry parsed | title='{title}' | raw_link='{raw_link}'")

print(f"[ingest] 🔍 URL unwrap | before='{raw_link}' | after='{clean_url}' | type={classify_url(clean_url)}")

print(f"[ingest] 🆔 UID='{uid}' | dedupe={'yes' if seen else 'no'}")

print(f"[ingest] 📝 Stored item rss:item:{uid} | url='{clean_url}'")
```

⸻

**5.3 Instrumentation in schedule_article_fetching()**

Add:
```python
print(f"[fetch] 🔎 Checking uid={uid} | html_exists={await r.exists(html_key)}")

print(f"[fetch] 📄 Loaded rss:item:{uid} | url='{url}' | type={classify_url(url)}")

print(f"[fetch] 🌐 START fetch uid={uid[:8]} | url='{url}'")

print(f"[fetch] 🌐 RESULT uid={uid[:8]} | status={resp_status} | bytes={len(html)}")

print(f"[fetch] 📝 STORED rss:article_raw:{uid} | bytes={len(html)} | title='{title}'")
```

⸻

**5.4 Instrumentation in schedule_article_enrichment()**

Add:
```python
print(f"[publish] 📰 Category={category} | items={len(items)} | context={len(context_items)}")

print(f"[publish] 📝 Rendering XML | category={category} | chars={len(xml)}")
```

⸻

**6. VERIFICATION PLAN (MANDATORY)**

After patching, you will:

**6.1 Restart the RSS system**
```text
./scripts/ms-rssagg.sh
```
### 6.2 Watch for:

✔ Are raw RSS URLs clean?
✔ Do any Google URLs appear?
✔ Does fetch use the correct URLs?
✔ Are canonicalizer logs appearing?
✔ Are enriched items being stored?
✔ Are feed XML sizes non-zero?

### 6.3 Capture 5 minutes of logs

We will analyze them together.

⸻

# 7. READY FOR PATCH APPLICATION

If you say:

### “apply patch”

I will produce a precise oboe.edit_file patch that:
* Injects instrumentation code ONLY
* Removes the duplicate run_orchestrator() definition
* Does NOT change system behavior
* Does NOT modify logic or ordering
* Adds URL classification helper
* Adds boundary logs at all required points