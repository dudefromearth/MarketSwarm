# # Document #4 — Canonical Fetcher Architecture & Design

### (Stage 2 — Clean Article Acquisition from Origin URLs)

⸻

### 1. Purpose of Step 2 (Canonical Fetching)

After Step 1 generates **clean sets of origin URLs grouped by category**, Step 2 turns each URL into a **canonical article**—a normalized, durable, text-first article object with a 7-day lifespan.

### The objective:

✔ Convert **URLs → Canonical Articles**
✔ Remove HTML noise
✔ Extract text, first image, abstract
✔ Normalize structure
✔ Deduplicate automatically
✔ Avoid re-fetching old or failed URLs
✔ Trigger processing only when new URLs appear
✔ Maintain transparency via stats and logs

⸻

### 2. Inputs and Outputs

### Inputs

From Step 1 (Ingestor):
```python
rss:category_links:<category> — SET of clean URLs, TTL=48h
```
### Outputs

Step 2 produces:

**Canonical Article (HASH)**
```python
rss:article_canonical:<uid>
  uid
  url
  category
  raw_len
  text_len
  clean_text
  abstract
  image
  fetched_ts
  status=success|failure
```
**Category Index (SET)**
```text
rss:articles_by_category:<category>
```
**Global Index (ZSET)**
```text
rss:article_canonical_index  (score = timestamp)
```
**Attempt Tracking (SET)**
### *(30-day TTL)*
```text
rss:canonical_attempted
```
**Failure Codes (ZSET)**
```text
rss:canonical_failures
```

⸻

### 3. Responsibilities of the Canonical Fetcher

### ✔ A. Detect when Step 1 produced new URLs

The fetcher **must not be a perpetual scanner**.
It only runs when new URLs appear.

Mechanism:
* Snapshot of all URLs (from all categories)
* Compare against rss:canonical_attempted
* Compute new_urls_to_fetch = snapshot - attempted_set
* If empty → exit quietly
* If not → process only the new URLs

⠀
### ✔ B. Guarantee non-reprocessing

UTIDs derived from url:
```bash
uid = sha1(url)[:16]
```
This means:
* same URL always → same UID
* article already exists → skip
* attempted within last 30 days → skip

⠀
### ✔ C. Download HTML (with fallback)
* aiohttp with 15s timeout
* if response <400 and HTML length >200 → proceed
* else → mark failure

⠀
### ✔ D. Canonicalize content

Using BeautifulSoup:
* remove <script>, <style>, noscript
* extract all text, normalize whitespace
* find first image
* generate abstract from first >40-char paragraph

⠀
### ✔ E. Save canonical result into Redis

TTL: 7 days

### ✔ F. Log results for observability

Sample log:
```bash
[canon] 🌐 Fetching → https://example.com/xyz
[canon] ⚠️ Bad HTML → skip
[canon] ✅ Stored canonical → fb18a22e994f51c
```
### ✔ G. Store structured failure codes

Helps influence feed curation later.

Example:
```bash
rss:canonical_failures:
   (score: timestamp) → uid:FAIL_BAD_HTML
```

⸻

### 4. Data Flow

**1. Ingestor publishes URL sets:**
```text
rss:category_links:jobs_report = {url1, url2, ...}
```
**2. Canonical Fetcher checks for new URLs:**
```bash
read all category_links sets  
read rss:canonical_attempted  
compute new URLs  
```
### 3. For each new URL:
* generate uid
* download HTML
* normalize
* write canonical article
* add uid to:
  * attempted set
  * category index
  * global index

⠀
### 4. Stop immediately after finishing batch

No looping, no repeated scans.

⸻

### 5. Canonical Fetcher Run Conditions

### The canonical fetcher is triggered when:
1. Step 1 completes an ingestion cycle
2. New URLs were added
3. Canonical data has not been created for them
4. Attempts older than 30 days may be retried (TTL-driven cleaning)

⠀
### It is not triggered when:
* No new URLs exist
* All new URLs were already attempted
* Ingestor had no new articles since last run

⠀
This is the most efficient and clean pipeline behavior.

⸻

### 6. Redis Structures for Step 2
| **Key** | **Type** | **TTL** | **Purpose** |
|:-:|:-:|:-:|:-:|
| rss:category_links:<cat> | SET | 48h | URLs from Step 1 |
| rss:canonical_attempted | SET | 30d | Prevent retries |
| rss:article_canonical:<uid> | HASH | 7d | Canonical article |
| rss:articles_by_category:<cat> | SET | 7d | Category-indexed UIDs |
| rss:article_canonical_index | ZSET | None | Global chronological index |
| rss:canonical_failures | ZSET | None | Failure events |

⸻

**7. Algorithm Overview (Pseudocode)**
```python
function canonical_fetcher_run_once():
    r = redis client

    all_urls = union of all rss:category_links:* sets

    attempted = SMEMBERS(rss:canonical_attempted)

    new = all_urls - attempted

    if new is empty:
        exit

    for url in new:
        uid = sha1(url)[:16]

        if EXISTS(rss:article_canonical:uid):
            SADD(rss:canonical_attempted, uid)
            continue

        html = fetch_html(url)
        if invalid:
            log failure
            add to failure index
            add to attempted set
            continue

        clean_text, first_img, abstract = clean_html(html)

        write canonical article
        TTL=7 days

        update category indexes
        update global index
        SADD(rss:canonical_attempted, uid)
```

⸻

**8. Failure Modes and Handling**

**Failure Types we track:**
| **Code** | **Meaning** |
|:-:|:-:|
| FAIL_BAD_HTML | HTML <200 chars, invalid markup |
| FAIL_HTTP | Non-200 response |
| FAIL_TIMEOUT | Network timeout |
| FAIL_PARSE | BeautifulSoup couldn’t parse text |
| FAIL_EMPTY | No meaningful text extracted |
Stored in:
```python
rss:canonical_failures
  member: "<uid>:<CODE>"
  score: timestamp
```
**In full mode:**
```python
loop ingest_feeds()
after each loop:
    canonical_fetcher_run_once()
start raw/enrich/publish loops
```
Canonical fetcher **is not a loop**.
It runs **once per ingestion cycle**, and **only processes new URLs**.

⸻

### 10. Benefits of This Design

### ✔ Deterministic and predictable

No background repeated scraping.

### ✔ Efficient

Only fetches new URLs.

### ✔ Self-cleaning

Attempt set expires after 30 days.

### ✔ Resilient

Failing URLs do not block the pipeline.

### ✔ Transparent

Logged, indexed, and measured.

### ✔ Simple to reason about

Step 2 is now a clean, bounded operation.