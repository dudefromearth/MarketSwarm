# **📄 MarketSwarm Architecture & Design Document

Markdown as the Baseline Format (v1.0)**

### Purpose

Define a unified data and processing model for MarketSwarm where **Markdown is the canonical substrate** for all article content flowing through ingestion, enrichment, and delivery systems.

This ensures:
* LLM-native processing
* Human readability
* Uniform, flexible publishing
* Seamless integration with Discord, web, mobile, and agent systems
* Future-proof interoperability

⠀
⸻

# 1. Why Markdown?

Markdown is chosen as the **baseline representation** because:

### ✔ LLM-optimized
* Preserves semantic structure (headers, lists, quotes).
* Removes layout noise (tables, ads, div clutter).
* Stable tokens → predictable LLM performance.
* Markdown → easier summarization than raw HTML.

⠀
### ✔ Human-readable
* Developers can inspect data instantly.
* Users (e.g., Discord and chat platforms) consume it directly.

⠀
### ✔ Technology-neutral

Markdown can be transformed into:
* RSS XML
* HTML
* PDFs
* Embeds
* JSON
* Vector embeddings
* Chat messages

⠀
### ✔ Clean intermediate substrate

A canonical Markdown file is more durable than HTML and simpler than JSON.

⸻

# 2. System Architecture Overview
```text
         ┌───────────────────────────────┐
         │         RAW HTML              │
         │ (browser fetch / Oxylabs)     │
         └─────────────┬─────────────────┘
                       │
                       ▼
             [Tier-0 Canonicalizer]
      Extract main content → convert to Markdown
      Store: markdown + metadata
                       │
                       ▼
            [Tier-3 LLM Enrichment Layer]
     Markdown → LLM structured metadata → enriched record
                       │
                       ▼
            [Delivery + Publication Layer]
   RSS / JSON / Discord Markdown / Web Embeds / Agents
```
**Markdown becomes the substrate between fetching and intelligent output.**

⸻

# 3. Markdown in the Pipeline

### 3.1 Tier-0: Canonical Markdown Article

The canonical fetcher:
* Pulls HTML
* Extracts main article with Readability
* Converts to Markdown
* Extracts:
  * title
  * abstract
  * image
  * word count
  * domain

⠀
### Stored in Redis at:
```text
rss:article_canonical:{uid}
```
**Required fields:**
```text
{
  uid,
  url,
  category,
  title,
  markdown,        ← canonical content
  abstract,
  image,
  markdown_len,
  fetched_ts
}
```

⸻

# 3.2 Tier-3: LLM Enrichment

LLM receives:
* title
* markdown content
* fallback image

⠀
LLM produces:
* clean_title
* abstract
* summary
* bullet takeaways
* sentiment
* entities
* tickers
* category
* quality_score
* reading_time
* hero_image

⠀
### Stored in:
```text
rss:article_enriched:{uid}
```
This is the structured intelligence layer.

⸻

# 3.3 Downstream Consumers (All Markdown-Friendly)

Markdown can be rendered into:

### Discord messages

Markdown → Discord = perfect formatting.

### Web App

Direct Markdown → React Markdown component.

### Mobile

Native clients can render Markdown.

### LLM Agents (Vexy bots)

Markdown gives consistent signals to the model.

### Export Formats
* RSS XML: pulls fields from canonical store
* JSON API: wraps markdown into JSON
* PDF: markdown → HTML → PDF
* Emails: markdown → HTML → email body

⠀
Markdown → one-to-many output capability.

⸻

# 4. Markdown Canonicalization Rules (MarketSwarm Standard)

### Rule 1. Extract only primary article body
* Use Readability
* Remove navigation, ads, footers

⠀
### Rule 2. Lossless structural preservation
* # for headings
* - for bullet lists
* > for quotes
* ** for bold emphasis

⠀
### Rule 3. Sanitize broken or useless tags

No:
* inline CSS
* scripts
* tracking pixels
* empty <div> or <span> artifacts

⠀
### Rule 4. No external HTML except code blocks

If HTML is required:
```html
<!-- HTML allowed -->
<div class="chart">...</div>
```
This is rare.

⸻

**5. Markdown Storage Format**

**Required keys:**
```text
markdown           → full canonical article
abstract           → first meaningful paragraph
markdown_len       → number of characters
image              → first usable image
title              → chosen hierarchical title
```
All metadata is stored **alongside markdown**, not within it.

⸻

# 6. LLM Workflow Advantages

Markdown → predictable token boundaries
→ cleaner summarization
→ consistent extraction
→ fewer hallucinations
→ lower latency
→ smaller cost

Example prompt effect:
```text
# Inflation Hits 3.2% in January
The Federal Reserve...
```
vs. raw HTML:
```html
<div class="article-header"><h1>Inflation Hits...</h1> <div class="byline">...
```

⸻

# 7. Publication Layer Architecture

### 7.1 RSS Feeds

Canonical markdown is not directly published to RSS.
RSS pulls:
* title
* URL
* abstract
* image
* pubDate

⠀
The markdown remains internal but drives the metadata.

### 7.2 Discord Feeds (recommended)

Directly publish:
* abstract
* summary
* takeaways
* link
* sentiment
* optional markdown snippet

⠀
Discord Markdown → perfect rendering.

### 7.3 Web UI

Serve canonical markdown → rendered client-side.

### 7.4 JSON API

Return:
```json
{
  uid,
  title,
  url,
  markdown,
  abstract,
  summary,
  entities,
  tickers,
  sentiment,
  quality_score,
  reading_time
}
```

Markdown is always included.

⸻

# 8. Future Extensions

### 8.1 Embeddings (Vector Search)

Embed markdown → higher semantic quality than text-stripped HTML.

### 8.2 Automated QA

Users can ask questions about an article.
Markdown → stored context for RAG.

### 8.3 Code Interpreter Analysis

Markdown → safe input for transformation, charting, extraction.

### 8.4 Human curation console

Internal UI shows raw markdown + enriched metadata.

⸻

# 9. Summary (Principles)

### 1. Markdown is canonical content.

All articles are stored and processed in Markdown.

### 2. HTML is temporary and discarded.

Used only once for extraction → replaced by Markdown.

### 3. LLMs always take Markdown as input.

Consistency = better results.

### 4. Publishers convert Markdown into target formats.

Discord → Markdown
RSS → XML
Web App → rendered Markdown
API → JSON with Markdown

### 5. Markdown is the internal substrate of truth.

All other representations are derived from it.