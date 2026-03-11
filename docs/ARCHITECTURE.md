# AI-Powered Daily Executive Briefing System — Architecture Document

**Version:** 1.0
**Date:** 2026-03-10
**Status:** Draft — for engineer implementation

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [High-Level Architecture Diagram](#2-high-level-architecture-diagram)
3. [Component Breakdown](#3-component-breakdown)
4. [Data Models](#4-data-models)
5. [Memory & Deduplication System](#5-memory--deduplication-system)
6. [Audience Ranking & Personalization Engine](#6-audience-ranking--personalization-engine)
7. [LLM Generation Design](#7-llm-generation-design)
8. [Delivery Architecture](#8-delivery-architecture)
9. [Telemetry & Feedback Loop](#9-telemetry--feedback-loop)
10. [API Contracts](#10-api-contracts)
11. [Deployment Topology on OCI](#11-deployment-topology-on-oci)
12. [Security Considerations](#12-security-considerations)
13. [Scalability Notes](#13-scalability-notes)

---

## 1. System Overview

The AI Daily Briefing System is an automated intelligence pipeline that ingests content from 20+ sources (RSS feeds, news APIs, HN, Reddit, GitHub trending, vendor blogs, earnings transcripts), normalizes and semantically deduplicates stories across a rolling 7-day window using vector embeddings and keyword overlap, scores each candidate article against four OCI executive audience profiles (Karan, Nathan, Greg, Mahesh), and generates personalized HTML email briefings via Claude — delivered each morning via Postmark, archived to OCI Object Storage, and instrumented with per-audience click tracking, open-pixel telemetry, and an explicit feedback mechanism (thumbs up/down, More/Less like this) that feeds back into audience profile weight refinement over time.

### Key Design Principles

| Principle | Description |
|-----------|-------------|
| **Ingest once** | A single ingestion pass fetches and stores raw articles; no source is polled per-audience |
| **Score once** | Source credibility, novelty, momentum, and strategic impact are computed once per article against the global context |
| **Deduplicate once** | Story clustering and 7-day novelty comparison are global operations, not per-audience |
| **Render differently per audience** | Only the final selection and LLM generation steps are audience-specific |
| **Primary sources first** | Tier 1 sources anchor facts; community signals (Tier 4) inform momentum, not headlines |
| **No repetition without delta** | A story cluster is suppressed for 7 days unless a structured fact delta (capacity, deal size, customer name, status) exceeds threshold |
| **Track what was suppressed** | The system records suppressed items, not only delivered items, enabling audit and threshold tuning |
| **Confidence tagging** | Every item carries an internal confidence tag: `confirmed`, `credible_report`, `weak_signal`, or `follow_up` |
| **Editorial rules as code** | Hard-coded guardrails (no community post as top story without corroboration, every item gets an OCI implication, max word counts per audience) are enforced in the pipeline, not in prompts |

---

## 2. High-Level Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                            INGESTION LAYER                                       │
│                                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────┐   │
│  │  RSS Poller │  │ News APIs   │  │ Community   │  │  Newsletter Parser   │   │
│  │             │  │ (NewsAPI,   │  │ Fetchers    │  │  (email inbox →      │   │
│  │ - Vendor    │  │  Bing News, │  │             │  │   MIME extractor)    │   │
│  │   blogs     │  │  GDELT)     │  │ - HN Algolia│  │                      │   │
│  │ - Press rel.│  │             │  │ - Reddit API│  │  Crawlers            │   │
│  │ - Earnings  │  │ Web Crawler │  │ - GitHub    │  │  (IR pages, SEC,     │   │
│  │ - Trade     │  │ (Scrapy /   │  │   Trending  │  │   utility filings)   │   │
│  │   press RSS │  │  Playwright)│  │ - LinkedIn  │  │                      │   │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────────┬───────────┘   │
│         └────────────────┴─────────────────┴─────────────────────┘              │
│                                      │                                           │
│                               raw_article_queue                                  │
│                              (OCI Queue / Redis)                                 │
└──────────────────────────────────────┬───────────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                        NORMALIZATION & ENRICHMENT                                │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  Normalizer                                                             │    │
│  │  - Extract full text (Trafilatura / Readability)                        │    │
│  │  - Clean boilerplate, normalize whitespace                              │    │
│  │  - Canonical URL resolution (follow redirects, strip tracking params)   │    │
│  │  - Publisher / source metadata tagging                                  │    │
│  │  - Timestamp normalization → UTC                                        │    │
│  │  - Source tier classification (Tier 1–4)                                │    │
│  │  - Language detection → discard non-English (configurable)             │    │
│  └─────────────────────┬───────────────────────────────────────────────────┘    │
│                         │                                                        │
│  ┌─────────────────────▼───────────────────────────────────────────────────┐    │
│  │  Entity & Event Enricher                                                │    │
│  │  - NER: companies, products, executives, regions, dates, dollar amounts │    │
│  │  - Event verb classification: launched, partnered, raised, expanded,    │    │
│  │    delayed, sued, announced, shipped, confirmed, denied                 │    │
│  │  - Topic taxonomy tagging (Financial, Power, Datacenter, Compete, AI,  │    │
│  │    Deals, Community, Security)                                          │    │
│  │  - Headline embedding (Claude claude-haiku-4-5 / text-embedding-3-large)        │    │
│  │  - Summary embedding                                                    │    │
│  │  - Source credibility score assignment                                  │    │
│  └─────────────────────┬───────────────────────────────────────────────────┘    │
│                         │                                                        │
│                    writes to: articles table (Postgres)                          │
│                    writes embeddings to: Qdrant / pgvector                       │
└─────────────────────────┬────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                      STORY INTELLIGENCE LAYER                                    │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  Clustering Engine                                                      │    │
│  │  - Embedding cosine similarity search (Qdrant ANN)                     │    │
│  │  - Entity overlap scoring (Jaccard on company + product + region sets)  │    │
│  │  - Event-type overlap check                                             │    │
│  │  - Assign to existing story_cluster or create new                       │    │
│  └─────────────────────┬───────────────────────────────────────────────────┘    │
│                         │                                                        │
│  ┌─────────────────────▼───────────────────────────────────────────────────┐    │
│  │  Deduplication & Novelty Engine                                         │    │
│  │  - Query delivered_items for cluster in last 7 days                     │    │
│  │  - Compare fact_deltas: capacity_mw, deal_size, customer_name,          │    │
│  │    model_name, partner_name, region, date, status                       │    │
│  │  - Compute novelty_score = f(semantic_distance, fact_delta_count)       │    │
│  │  - Tag: new | follow_up | candidate_duplicate | suppressed              │    │
│  └─────────────────────┬───────────────────────────────────────────────────┘    │
│                         │                                                        │
│  ┌─────────────────────▼───────────────────────────────────────────────────┐    │
│  │  Global Scorer                                                          │    │
│  │  - source_credibility_score (from tier table)                           │    │
│  │  - momentum_score (cross-outlet coverage count, HN/Reddit velocity)     │    │
│  │  - strategic_impact_score (keyword + topic match against OCI watchlist) │    │
│  │  - timeliness_score (decay function on published_at)                    │    │
│  │  - duplication_penalty (applied if candidate_duplicate)                 │    │
│  │  → writes global_score to story_clusters                                │    │
│  └─────────────────────┬───────────────────────────────────────────────────┘    │
│                         │                                                        │
│              writes to: story_clusters, cluster_articles,                        │
│                         fact_deltas (Postgres)                                   │
└─────────────────────────┬────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                      AUDIENCE RANKING ENGINE                                     │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  Per-Audience Ranker (runs 4x, one per executive)                       │    │
│  │  - Load audience_profile (section_weights, companies_of_interest,       │    │
│  │    topics_of_interest, negative_topics, geo_focus)                      │    │
│  │  - Compute audience_relevance_score per cluster:                        │    │
│  │      section_weight × (entity_boost + topic_boost + embedding_sim)      │    │
│  │  - final_score = global_score components + audience_relevance_score     │    │
│  │  - Enforce editorial rules (no Tier-4-only story in top 3)             │    │
│  │  - Select top 8–15 items, ordered by section then score                │    │
│  └─────────────────────┬───────────────────────────────────────────────────┘    │
└─────────────────────────┬────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                LLM GENERATION LAYER (Claude)                                     │
│                                                                                  │
│  Stage 1: Common Bundle Generation (shared)                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  - Build canonical ranked bundle of 20–40 story objects                │    │
│  │  - Each story gets: headline, 2–4 sentence neutral summary,             │    │
│  │    key facts, confidence_tag, follow_up metadata                       │    │
│  │  - Model: claude-opus-4-5 for generation, claude-haiku-4-5 for classification   │    │
│  └─────────────────────┬───────────────────────────────────────────────────┘    │
│                         │                                                        │
│  Stage 2: Audience-Specific Generation (4× parallel)                            │
│  ┌─────────────────────▼───────────────────────────────────────────────────┐    │
│  │  For each audience:                                                     │    │
│  │  - Inject audience persona, tone, section weights into prompt           │    │
│  │  - Generate: audience-specific headline variation, OCI implication,     │    │
│  │    optional watch item, section commentary                              │    │
│  │  - Enforce max_length and include_speculative_analysis flags            │    │
│  └─────────────────────┬───────────────────────────────────────────────────┘    │
└─────────────────────────┬────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                       2-STAGE RENDERER                                           │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  HTML Email Renderer                                                    │    │
│  │  - Inject tracking pixels (1×1 img tag → tracking endpoint)            │    │
│  │  - Replace article URLs → per-audience tracking redirect URLs          │    │
│  │  - Inject feedback buttons (More/Less like this, thumbs up/down)       │    │
│  │  - Render responsive HTML (table-based for email client compat)        │    │
│  │  - Write rendered HTML → OCI Object Storage (archive)                  │    │
│  └─────────────────────┬───────────────────────────────────────────────────┘    │
└─────────────────────────┬────────────────────────────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
┌─────────────────────┐     ┌──────────────────────────┐
│   DELIVERY          │     │   OCI OBJECT STORAGE      │
│                     │     │                            │
│  Postmark API       │     │  briefings/               │
│  - Send HTML email  │     │    {date}/                │
│  - Per-audience     │     │      karan.html           │
│    template         │     │      nathan.html          │
│  - Track bounces    │     │      greg.html            │
│  - Open tracking   │     │      mahesh.html          │
│    (Postmark pixel) │     │  (public read URL)        │
└─────────────────────┘     └──────────────────────────┘
              │
              ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                    TRACKING & ANALYTICS                                          │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  Click Tracking Redirect Service (OCI Function / FastAPI)               │    │
│  │  GET /{date}/{audience_id}/{story_id}                                   │    │
│  │  - Log tracking_event to Postgres                                       │    │
│  │  - 302 redirect → canonical article URL                                │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  Open Tracking Pixel Service                                            │    │
│  │  GET /pixel/{date}/{audience_id}.gif                                    │    │
│  │  - Return 1×1 transparent GIF                                          │    │
│  │  - Log open event to Postgres                                           │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  Feedback Ingestion Endpoint                                            │    │
│  │  POST /feedback                                                         │    │
│  │  - Receives: audience_id, story_id, date, feedback_type                │    │
│  │  - Writes to feedback_events table                                      │    │
│  │  - Queues for manual review → eventual profile weight update           │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                 SCHEDULER / ORCHESTRATOR                                         │
│                                                                                  │
│  OCI Scheduler (cron: 04:00 UTC daily)                                          │
│  → triggers: Ingestion → Normalization → Story Intelligence                     │
│           → Audience Ranking → LLM Generation → Rendering → Delivery            │
│                                                                                  │
│  Retry logic: exponential backoff (max 3 retries per stage)                     │
│  Failure alerting: OCI Notifications → email / PagerDuty                        │
└──────────────────────────────────────────────────────────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                        DATA STORES                                               │
│                                                                                  │
│  ┌──────────────────────┐    ┌──────────────────────────────────────────┐       │
│  │  PostgreSQL          │    │  Qdrant (vector store)                   │       │
│  │  (OCI DB System /    │    │  - headline_embeddings collection        │       │
│  │   Autonomous DB)     │    │  - summary_embeddings collection         │       │
│  │                      │    │  - payload: article_id, cluster_id,      │       │
│  │  - articles          │    │    published_at, source_tier             │       │
│  │  - story_clusters    │    │  - ANN search: cosine similarity         │       │
│  │  - cluster_articles  │    │  - Filter by published_at > now()-7d     │       │
│  │  - audience_profiles │    └──────────────────────────────────────────┘       │
│  │  - delivered_items   │                                                        │
│  │  - tracking_links    │    ┌──────────────────────────────────────────┐       │
│  │  - tracking_events   │    │  OCI Object Storage                      │       │
│  │  - feedback_events   │    │  - briefings/{date}/{audience_id}.html   │       │
│  │  - fact_deltas       │    │  - Public pre-authenticated URLs         │       │
│  └──────────────────────┘    └──────────────────────────────────────────┘       │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Component Breakdown

### 3.1 RSS Poller

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Poll RSS/Atom feeds on a schedule; fetch new entries since last poll |
| **Inputs** | Feed URL list (config), last-polled timestamps (Postgres or Redis) |
| **Outputs** | Raw article records to `raw_article_queue` |
| **Key design decisions** | Use `feedparser` library; store ETag and Last-Modified headers per feed to minimize bandwidth; poll every 30–60 minutes for Tier 1 sources, every 2 hours for Tier 3 |

### 3.2 News API Fetcher

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Query NewsAPI, Bing News Search, and GDELT for articles matching topic and keyword watchlists |
| **Inputs** | Keyword/query config, API credentials from OCI Vault |
| **Outputs** | Raw article records to `raw_article_queue` |
| **Key design decisions** | Deduplicate by canonical URL before enqueuing; GDELT used for international and geopolitical signals; schedule queries to avoid rate limits |

### 3.3 Community Fetchers (HN, Reddit, GitHub)

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Fetch top HN stories (Algolia API), relevant Reddit posts (r/MachineLearning, r/sysadmin, r/datascience, r/oracle, r/CloudComputing), GitHub trending repos |
| **Inputs** | Subreddit/query config, HN API, GitHub trending scrape |
| **Outputs** | Raw article records tagged `source_tier=4`, with upvote/comment counts as momentum signals |
| **Key design decisions** | Community items get `source_tier=4`; they can boost momentum of existing clusters but cannot be promoted to top story without Tier 1–2 corroboration; score velocity (upvote rate) not just raw count |

### 3.4 Newsletter Parser

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Parse inbound newsletters from a dedicated ingestion inbox (e.g., `briefing-ingest@yourorg.com`) |
| **Inputs** | IMAP/MIME messages from inbox |
| **Outputs** | Extracted article-like items to `raw_article_queue` |
| **Key design decisions** | Use `mailparser` or Python `email` module; extract text content, links, and publication metadata; mark source as the newsletter name |

### 3.5 Web Crawler

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Crawl IR pages, SEC EDGAR feeds, utility press releases, and other non-RSS sources on schedule |
| **Inputs** | URL list with XPath/CSS selectors per source (config), change detection hashes |
| **Outputs** | Extracted content to `raw_article_queue` |
| **Key design decisions** | Use Scrapy for structured crawling; Playwright for JS-heavy pages; only re-process pages when content hash changes |

### 3.6 Normalizer

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Extract clean article text, resolve canonical URLs, assign source metadata and tier, normalize timestamps |
| **Inputs** | Raw article from queue |
| **Outputs** | Normalized article record written to `articles` table |
| **Key design decisions** | Use Trafilatura as primary text extractor (outperforms Newspaper3k on boilerplate removal); canonical URL via `canonicalize_url` with redirect following; reject articles with <100 characters of body text |

### 3.7 Entity & Event Enricher

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Extract named entities, classify event verbs, assign topic taxonomy, generate embeddings |
| **Inputs** | Normalized article from `articles` table |
| **Outputs** | Updated `articles` record with entities, event_type, topic_tags, embeddings; embedding vectors written to Qdrant |
| **Key design decisions** | Use spaCy `en_core_web_trf` for NER (transformer-based for accuracy); Claude claude-haiku-4-5 for event verb classification and topic taxonomy (fast, cheap); `text-embedding-3-large` (OpenAI) or Claude Embeddings for vector generation; store both headline and body embeddings separately |

### 3.8 Clustering Engine

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Group articles about the same real-world event into `story_clusters` |
| **Inputs** | New article embedding from Qdrant; article entities from Postgres |
| **Outputs** | Updated `story_clusters` and `cluster_articles` records |
| **Key design decisions** | Two-pass: (1) ANN search in Qdrant (cosine similarity > 0.82) to find candidate matches, (2) entity overlap check (Jaccard > 0.3 on company+region+product) to confirm; new cluster created if no match found; cluster representative updated to highest-credibility article |

### 3.9 Deduplication & Novelty Engine

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Determine whether a story cluster has already been sent and whether it qualifies as a follow-up |
| **Inputs** | `story_clusters` record; `delivered_items` for the last 7 days; `fact_deltas` for the cluster |
| **Outputs** | `novelty_status` field on `story_clusters`: `new`, `follow_up`, `candidate_duplicate`, `suppressed` |
| **Key design decisions** | See Section 5 for full design; key thresholds: semantic similarity > 0.88 → candidate_duplicate; fact_delta count ≥ 1 overrides duplicate suppression |

### 3.10 Global Scorer

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Compute the global score for each story cluster independent of audience |
| **Inputs** | Story cluster record with source_tier, novelty_status, published_at, momentum signals |
| **Outputs** | `global_score` on `story_clusters` |
| **Key design decisions** | Score formula: `source_credibility(0–30) + momentum(0–20) + strategic_impact(0–20) + timeliness(0–15) + novelty(0–15) - duplication_penalty(0–30)` — all components normalized to their stated ranges |

### 3.11 Audience Ranking Engine

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Re-rank story clusters per audience using profile weights, company/topic boosts, and negative topic suppression |
| **Inputs** | Global-scored story clusters; audience profiles from `audience_profiles` |
| **Outputs** | Ranked list of 8–15 story items per audience, ordered by section then score |
| **Key design decisions** | See Section 6 for full design; editorial guardrails enforced here (Tier-4-only items cannot be top 3, every item must have an assigned section) |

### 3.12 LLM Generation Layer

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Generate audience-specific headlines, summaries, OCI implications, and watch items |
| **Inputs** | Ranked story items per audience; audience persona definitions; article text from `articles` |
| **Outputs** | `rendered_item` objects per audience per story |
| **Key design decisions** | See Section 7 for full design; Claude claude-opus-4-5 for substantive generation, Claude claude-haiku-4-5 for classification/scoring; generation is parallelized across audiences |

### 3.13 HTML Renderer

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Assemble final HTML email with injected tracking URLs, open pixel, and feedback controls |
| **Inputs** | `rendered_item` list per audience; tracking link records |
| **Outputs** | Rendered HTML string; file written to OCI Object Storage |
| **Key design decisions** | Use Jinja2 templates; table-based layout for email client compatibility; inline CSS for Gmail/Outlook; tracking pixel as last element to improve open detection accuracy |

### 3.14 Delivery Service

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Send personalized HTML emails via Postmark; record delivery outcomes |
| **Inputs** | Rendered HTML per audience; recipient email addresses |
| **Outputs** | Postmark message IDs; delivery records in `delivered_items` |
| **Key design decisions** | Use Postmark transactional API (not templates) for full HTML control; record `postmark_message_id` for webhook correlation; handle bounces via Postmark webhook |

### 3.15 Tracking & Feedback Services

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Handle click redirects, open pixel requests, and explicit feedback form submissions |
| **Inputs** | HTTP GET/POST requests from email clients |
| **Outputs** | `tracking_events` and `feedback_events` records in Postgres |
| **Key design decisions** | Deployed as OCI Functions (serverless) for low cost at small scale; stateless; no PII stored beyond audience_id; see Section 9 for full design |

### 3.16 Orchestrator

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Schedule and sequence all pipeline stages; retry on failure; alert on terminal failure |
| **Inputs** | OCI Scheduler cron trigger |
| **Outputs** | Pipeline execution log; OCI Notification on failure |
| **Key design decisions** | MVP: Python script with sequential stage execution and retry; production: Prefect or Temporal for DAG-based orchestration with per-stage retries and observability |

---

## 4. Data Models

All tables use PostgreSQL. UUIDs are preferred for primary keys to support future multi-tenant sharding.

```sql
-- ─────────────────────────────────────────────
-- ARTICLES
-- Raw ingested and normalized article records
-- ─────────────────────────────────────────────
CREATE TABLE articles (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_url           TEXT NOT NULL UNIQUE,
    title                   TEXT NOT NULL,
    body_text               TEXT,
    summary_text            TEXT,                          -- extracted or generated 1-para summary
    published_at            TIMESTAMPTZ,
    fetched_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_name             TEXT NOT NULL,                 -- e.g. "Reuters", "Hacker News"
    source_tier             SMALLINT NOT NULL CHECK (source_tier BETWEEN 1 AND 4),
    source_url              TEXT,                         -- RSS feed URL or API endpoint used
    author                  TEXT,
    language                CHAR(2) DEFAULT 'en',
    word_count              INTEGER,

    -- Enrichment fields
    entities                JSONB,       -- {companies: [], people: [], regions: [], products: []}
    event_type              TEXT,        -- launched | partnered | raised | expanded | delayed |
                                         -- announced | shipped | confirmed | denied | filed | other
    topic_tags              TEXT[],      -- [financial, power, datacenter, compete, ai, deals, community, security]
    confidence_tag          TEXT CHECK (confidence_tag IN ('confirmed','credible_report','weak_signal','follow_up')),

    -- Scoring
    source_credibility_score NUMERIC(5,2),  -- 0–30
    momentum_score           NUMERIC(5,2),  -- 0–20 (updated as more outlets cover the story)
    timeliness_score         NUMERIC(5,2),  -- 0–15 (decays with age)

    -- Vector references (embedding stored in Qdrant; store IDs here for join)
    headline_vector_id      TEXT,         -- Qdrant point ID
    summary_vector_id       TEXT,         -- Qdrant point ID

    -- Provenance
    raw_payload             JSONB,        -- original API response or feed entry
    ingestion_source        TEXT,         -- rss | newsapi | bing | gdelt | hn | reddit | github | crawler | newsletter

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_articles_published_at ON articles (published_at DESC);
CREATE INDEX idx_articles_source_tier ON articles (source_tier);
CREATE INDEX idx_articles_canonical_url ON articles (canonical_url);
CREATE INDEX idx_articles_topic_tags ON articles USING GIN (topic_tags);
CREATE INDEX idx_articles_entities ON articles USING GIN (entities);


-- ─────────────────────────────────────────────
-- STORY CLUSTERS
-- Canonical deduplicated story groups
-- ─────────────────────────────────────────────
CREATE TABLE story_clusters (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    representative_article_id UUID REFERENCES articles(id),  -- highest-credibility article in cluster

    -- Cluster identity
    cluster_title           TEXT,                   -- auto-generated canonical title
    primary_topic           TEXT,                   -- dominant topic tag
    entities                JSONB,                  -- union of all article entities in cluster
    event_type              TEXT,

    -- Scoring
    global_score            NUMERIC(6,2),           -- computed by Global Scorer
    source_credibility_score NUMERIC(5,2),
    momentum_score           NUMERIC(5,2),
    strategic_impact_score   NUMERIC(5,2),
    timeliness_score         NUMERIC(5,2),
    novelty_score            NUMERIC(5,2),
    duplication_penalty      NUMERIC(5,2) DEFAULT 0,

    -- Deduplication
    novelty_status          TEXT CHECK (novelty_status IN ('new','follow_up','candidate_duplicate','suppressed')),
    parent_cluster_id       UUID REFERENCES story_clusters(id),  -- if follow_up, link to original cluster
    first_seen_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Date range of covered events
    earliest_article_at     TIMESTAMPTZ,
    latest_article_at       TIMESTAMPTZ,

    article_count           INTEGER DEFAULT 1,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_story_clusters_global_score ON story_clusters (global_score DESC);
CREATE INDEX idx_story_clusters_novelty_status ON story_clusters (novelty_status);
CREATE INDEX idx_story_clusters_primary_topic ON story_clusters (primary_topic);
CREATE INDEX idx_story_clusters_last_updated ON story_clusters (last_updated_at DESC);


-- ─────────────────────────────────────────────
-- CLUSTER ARTICLES
-- Many-to-many join between clusters and articles
-- ─────────────────────────────────────────────
CREATE TABLE cluster_articles (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cluster_id              UUID NOT NULL REFERENCES story_clusters(id) ON DELETE CASCADE,
    article_id              UUID NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    similarity_score        NUMERIC(5,4),           -- cosine similarity to cluster representative
    added_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (cluster_id, article_id)
);

CREATE INDEX idx_cluster_articles_cluster_id ON cluster_articles (cluster_id);
CREATE INDEX idx_cluster_articles_article_id ON cluster_articles (article_id);


-- ─────────────────────────────────────────────
-- AUDIENCE PROFILES
-- Executive profiles and personalization weights
-- ─────────────────────────────────────────────
CREATE TABLE audience_profiles (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    audience_id             TEXT NOT NULL UNIQUE,   -- 'karan' | 'nathan' | 'greg' | 'mahesh'
    display_name            TEXT NOT NULL,
    email_address           TEXT NOT NULL,          -- encrypted at rest
    title                   TEXT,

    -- Personalization configuration (stored as JSONB for flexibility)
    topics_of_interest      TEXT[],
    negative_topics         TEXT[],
    companies_of_interest   TEXT[],
    geo_focus               TEXT[],
    preferred_tone          TEXT,                   -- 'concise' | 'ecosystem-oriented' | 'technical' | 'platform'
    time_horizon            TEXT,                   -- 'immediate' | 'strategic' | 'both'
    max_length              TEXT,                   -- 'short' | 'medium' | 'long'
    include_community_signals BOOLEAN DEFAULT TRUE,
    include_speculative_analysis BOOLEAN DEFAULT FALSE,

    -- Section weights (must sum to 1.0 per audience)
    section_weights         JSONB NOT NULL,
    -- Example: {"financial": 0.35, "compete": 0.25, "datacenter": 0.15, "ai": 0.15, "deals": 0.10}

    -- Learned weights from feedback (starts null, populated after feedback analysis)
    learned_topic_weights   JSONB,
    learned_source_weights  JSONB,

    is_active               BOOLEAN DEFAULT TRUE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ─────────────────────────────────────────────
-- DELIVERED ITEMS
-- What was sent to whom on which date
-- ─────────────────────────────────────────────
CREATE TABLE delivered_items (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    briefing_date           DATE NOT NULL,
    audience_id             TEXT NOT NULL REFERENCES audience_profiles(audience_id),
    cluster_id              UUID NOT NULL REFERENCES story_clusters(id),
    article_id              UUID REFERENCES articles(id),    -- representative article delivered

    -- Positioning in the email
    section                 TEXT NOT NULL,
    position_in_section     INTEGER,
    position_global         INTEGER,

    -- Rendering metadata
    novelty_status_at_delivery TEXT,                -- snapshot of status when sent
    confidence_tag          TEXT,

    -- Delivery outcome
    postmark_message_id     TEXT,
    delivered_at            TIMESTAMPTZ,
    delivery_status         TEXT CHECK (delivery_status IN ('sent','bounced','failed')),

    -- Archive
    archive_url             TEXT,                   -- OCI Object Storage public URL

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (briefing_date, audience_id, cluster_id)
);

CREATE INDEX idx_delivered_items_briefing_date ON delivered_items (briefing_date DESC);
CREATE INDEX idx_delivered_items_audience_id ON delivered_items (audience_id);
CREATE INDEX idx_delivered_items_cluster_id ON delivered_items (cluster_id);
-- Key query: find clusters delivered to any audience in last 7 days
CREATE INDEX idx_delivered_items_date_cluster ON delivered_items (cluster_id, briefing_date DESC);


-- ─────────────────────────────────────────────
-- TRACKING LINKS
-- Per-audience per-story unique redirect URLs
-- ─────────────────────────────────────────────
CREATE TABLE tracking_links (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    briefing_date           DATE NOT NULL,
    audience_id             TEXT NOT NULL REFERENCES audience_profiles(audience_id),
    cluster_id              UUID NOT NULL REFERENCES story_clusters(id),
    article_id              UUID REFERENCES articles(id),

    -- URL structure
    tracking_path           TEXT NOT NULL UNIQUE,  -- /{date}/{audience_id}/{cluster_id}
    canonical_url           TEXT NOT NULL,          -- destination after redirect

    -- Context metadata (stored for analytics, no redirect-time lookup needed)
    section                 TEXT,
    position_in_section     INTEGER,
    position_global         INTEGER,
    source_name             TEXT,
    source_tier             SMALLINT,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (briefing_date, audience_id, cluster_id)
);

CREATE INDEX idx_tracking_links_tracking_path ON tracking_links (tracking_path);
CREATE INDEX idx_tracking_links_briefing_date ON tracking_links (briefing_date DESC);


-- ─────────────────────────────────────────────
-- TRACKING EVENTS
-- Click and open events
-- ─────────────────────────────────────────────
CREATE TABLE tracking_events (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type              TEXT NOT NULL CHECK (event_type IN ('click','open')),
    briefing_date           DATE NOT NULL,
    audience_id             TEXT NOT NULL,
    cluster_id              UUID REFERENCES story_clusters(id),    -- null for open events
    tracking_link_id        UUID REFERENCES tracking_links(id),    -- null for open events

    -- Context (denormalized for analytics efficiency)
    section                 TEXT,
    position_in_section     INTEGER,
    position_global         INTEGER,
    source_name             TEXT,

    -- Request metadata
    ip_address              INET,                   -- for deduplication only; purged after 24h
    user_agent              TEXT,
    occurred_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Open tracking specific
    open_pixel_id           TEXT                    -- matches /pixel/{date}/{audience_id}
);

CREATE INDEX idx_tracking_events_audience_date ON tracking_events (audience_id, briefing_date DESC);
CREATE INDEX idx_tracking_events_cluster_id ON tracking_events (cluster_id);
CREATE INDEX idx_tracking_events_event_type ON tracking_events (event_type);
CREATE INDEX idx_tracking_events_occurred_at ON tracking_events (occurred_at DESC);


-- ─────────────────────────────────────────────
-- FEEDBACK EVENTS
-- Explicit feedback from recipients
-- ─────────────────────────────────────────────
CREATE TABLE feedback_events (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    briefing_date           DATE NOT NULL,
    audience_id             TEXT NOT NULL REFERENCES audience_profiles(audience_id),
    cluster_id              UUID NOT NULL REFERENCES story_clusters(id),

    feedback_type           TEXT NOT NULL CHECK (feedback_type IN (
                                'thumbs_up','thumbs_down',
                                'more_like_this','less_like_this',
                                'too_repetitive','useful','not_useful'
                            )),
    feedback_value          SMALLINT,               -- +1 or -1 for weight adjustment
    section                 TEXT,

    -- Processing state
    review_status           TEXT DEFAULT 'pending' CHECK (review_status IN ('pending','reviewed','applied','rejected')),
    reviewed_at             TIMESTAMPTZ,
    applied_at              TIMESTAMPTZ,
    notes                   TEXT,                   -- manual reviewer notes

    occurred_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_feedback_events_audience_id ON feedback_events (audience_id);
CREATE INDEX idx_feedback_events_cluster_id ON feedback_events (cluster_id);
CREATE INDEX idx_feedback_events_review_status ON feedback_events (review_status);


-- ─────────────────────────────────────────────
-- FACT DELTAS
-- Structured fact extraction for follow-up detection
-- ─────────────────────────────────────────────
CREATE TABLE fact_deltas (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cluster_id              UUID NOT NULL REFERENCES story_clusters(id) ON DELETE CASCADE,
    article_id              UUID NOT NULL REFERENCES articles(id),
    extracted_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Structured fact fields (any populated field represents a potential delta)
    capacity_mw             NUMERIC(10,2),           -- data center capacity in megawatts
    customer_name           TEXT,                    -- named customer
    deal_size               NUMERIC(15,2),           -- deal value in USD
    deal_size_currency      CHAR(3) DEFAULT 'USD',
    model_name              TEXT,                    -- AI model name
    partner_name            TEXT,                    -- partner organization
    region                  TEXT,                    -- geographic region or market
    event_date              DATE,                    -- key date mentioned in article
    status                  TEXT,                    -- announced | confirmed | delayed | cancelled | closed | live

    -- Delta comparison metadata
    is_new_fact             BOOLEAN DEFAULT TRUE,    -- false if same value existed in prior cluster fact
    prior_fact_delta_id     UUID REFERENCES fact_deltas(id),  -- link to prior fact this supersedes
    delta_fields            TEXT[],                  -- which fields changed from prior fact

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_fact_deltas_cluster_id ON fact_deltas (cluster_id);
CREATE INDEX idx_fact_deltas_article_id ON fact_deltas (article_id);
CREATE INDEX idx_fact_deltas_is_new_fact ON fact_deltas (is_new_fact) WHERE is_new_fact = TRUE;
```

---

## 5. Memory & Deduplication System

The 7-day memory system is the most critical correctness requirement in the pipeline. It runs as a 5-step sequential process for every new article after normalization.

### 5.1 Step 1: Normalize

**Goal:** Transform raw article text into structured, comparable representations.

**Inputs:** Normalized article from `articles` table (body text, title, entities)

**Operations:**
- Entity extraction using spaCy `en_core_web_trf`:
  - Organizations, Products, People, Geopolitical Entities (GPE), Money amounts, Dates
  - Output: `entities` JSONB with keys: `companies[]`, `products[]`, `people[]`, `regions[]`, `amounts[]`, `dates[]`
- Event verb classification using Claude claude-haiku-4-5:
  - Prompt: "Classify the primary event in this article into one of: launched, partnered, raised, expanded, delayed, sued, announced, shipped, confirmed, denied, filed, other. Return only the single word."
  - Stored in `articles.event_type`
- Topic taxonomy tagging using Claude claude-haiku-4-5:
  - Multi-label classification against: financial, power, datacenter, compete, ai, deals, community, security
  - Stored in `articles.topic_tags[]`
- Generate two embeddings (1536-dim via `text-embedding-3-large` or equivalent):
  - Headline embedding: `title` field
  - Summary embedding: first 512 tokens of `body_text`
  - Store embedding vectors in Qdrant with payload: `{article_id, cluster_id (null initially), published_at, source_tier}`
  - Store Qdrant point IDs in `articles.headline_vector_id` and `articles.summary_vector_id`

### 5.2 Step 2: Cluster

**Goal:** Map the new article to an existing story cluster or create a new one.

**Candidate retrieval from Qdrant:**
```
Search: headline_embeddings collection
Query vector: new article headline embedding
Filter: published_at >= now() - interval '30 days'  -- wider than 7-day window to catch evolving stories
Limit: 20 candidates
Metric: cosine similarity
```

**Two-pass confirmation:**

Pass 1 — Semantic similarity:
- `cosine_similarity(new_article.headline_embedding, candidate.headline_embedding) > 0.82`
- OR `cosine_similarity(new_article.summary_embedding, candidate.summary_embedding) > 0.78`

Pass 2 — Entity overlap (Jaccard):
```python
entity_jaccard = len(new.companies & candidate.companies) / len(new.companies | candidate.companies)
region_match   = bool(new.regions & candidate.regions)
event_match    = (new.event_type == candidate.event_type)

# Confirm cluster match if:
(semantic_pass AND entity_jaccard > 0.30) OR
(semantic_pass AND event_match AND region_match)
```

**Cluster assignment:**
- If match found: add to existing `story_cluster`, update `cluster_articles`, update `story_clusters.last_updated_at` and `article_count`; update Qdrant payload with `cluster_id`
- If no match: create new `story_cluster`, assign new `cluster_id`, write initial `fact_deltas`

### 5.3 Step 3: Compare Against 7-Day Window

**Goal:** Determine if this cluster has already been delivered to any audience within the past 7 days.

**Query:**
```sql
SELECT DISTINCT cluster_id, briefing_date, audience_id
FROM delivered_items
WHERE cluster_id = $cluster_id
  AND briefing_date >= CURRENT_DATE - INTERVAL '7 days';
```

**Semantic similarity check (for near-duplicate clusters not yet linked):**
```
Search: Qdrant summary_embeddings
Query: new article summary embedding
Filter: published_at >= now() - interval '7 days'
        AND cluster_id IN (SELECT cluster_id FROM delivered_items WHERE briefing_date >= now()-7d)
Limit: 5
```
- If `cosine_similarity > 0.88` against any delivered cluster → mark `novelty_status = 'candidate_duplicate'`
- Merge clusters if similarity > 0.95 (same story, different ingestion path)

### 5.4 Step 4: Detect Follow-Up

**Goal:** Override `candidate_duplicate` suppression if the article adds materially new information.

**Fact delta extraction:** Claude claude-haiku-4-5 extracts structured facts from the new article:
```
Prompt: "Extract structured facts from this article. Return JSON with keys:
capacity_mw, customer_name, deal_size, model_name, partner_name, region, event_date, status.
Use null for any field not mentioned."
```

**Comparison logic:**
```python
# Fetch prior fact_deltas for this cluster
prior_facts = db.query(fact_deltas).filter(cluster_id=cluster_id).all()

new_fact_fields = [field for field in FACT_FIELDS if new_facts[field] is not None]
prior_fact_fields = {f for prior in prior_facts for f in prior.delta_fields}

# A field is a new delta if:
# 1. It is newly populated (was null in all prior facts), OR
# 2. Its value has materially changed from the most recent prior value
delta_count = 0
for field in new_fact_fields:
    if field not in prior_fact_fields:
        delta_count += 1  # new fact added
    elif new_facts[field] != get_most_recent_prior(prior_facts, field):
        delta_count += 1  # existing fact changed

if delta_count >= 1:
    novelty_status = 'follow_up'
else:
    novelty_status = 'suppressed'
```

**Valid follow-up signals from the brief:**
- New numbers (capacity, deal size, valuation)
- Official confirmation or denial of previously reported information
- Financing closed (status: announced → closed)
- Timeline changed (event_date updated)
- Customer named for previously anonymous deal
- Launch date set
- Geographic expansion (new region added)
- Deal value revealed
- Partner list expanded
- Outage resolved or worsened (status field)

### 5.5 Step 5: Render as Follow-Up

**Goal:** Tag follow-up stories visually and narratively distinct from new stories.

**Tagging schema stored in `delivered_items.novelty_status_at_delivery`:**

| Tag | Display label | Rendering |
|-----|--------------|-----------|
| `new` | (no badge) | Standard rendering |
| `follow_up` | "UPDATE" | Orange badge; LLM prompt instructed to reference prior coverage and highlight what changed |
| `follow_up` with significant delta | "MAJOR UPDATE" | Red badge; promoted in section ordering |
| `suppressed` | Not included | Logged to `delivered_items` with delivery_status = 'suppressed' for audit |

**Follow-up LLM prompt addition:**
```
This is a follow-up to a story previously covered on {prior_date}.
The new information is: {delta_fields joined as natural language}.
Begin the summary by acknowledging the prior coverage and leading with what is new.
Do not repeat facts already covered unless necessary for context.
```

**Duplication penalty feeding into scoring:**
```python
duplication_penalty = 0
if novelty_status == 'candidate_duplicate':
    duplication_penalty = 30  # maximum penalty, effectively suppresses
elif novelty_status == 'follow_up':
    duplication_penalty = 5   # small penalty; story is valid but slightly less novel
elif novelty_status == 'new':
    duplication_penalty = 0
```

---

## 6. Audience Ranking & Personalization Engine

### 6.1 Score Formula

For each `(audience, story_cluster)` pair:

```
audience_relevance_score =
    section_weight[cluster.primary_topic] × 40
    + company_boost × 20
    + topic_boost × 15
    + embedding_similarity_to_audience_brief × 15
    + geo_boost × 10

final_audience_score =
    source_credibility_score    (0–30)
    + momentum_score            (0–20)
    + strategic_impact_score    (0–20)
    + timeliness_score          (0–15)
    + novelty_score             (0–15)
    - duplication_penalty       (0–30)
    + audience_relevance_score  (0–100, normalized to 0–30 contribution)
```

### 6.2 Component Calculations

**Section weight application:**
```python
section_weight = audience_profile.section_weights.get(cluster.primary_topic, 0.05)
# base contribution = section_weight × 40 (maps 0.0–1.0 weight to 0–40 points)
```

**Company boost:**
```python
cluster_companies = set(cluster.entities.get('companies', []))
interest_companies = set(audience_profile.companies_of_interest)
overlap = cluster_companies & interest_companies
company_boost = min(len(overlap) * 10, 20)  # cap at 20 points
```

**Topic boost:**
```python
topic_overlap = set(cluster.topic_tags) & set(audience_profile.topics_of_interest)
topic_boost = min(len(topic_overlap) * 5, 15)  # cap at 15 points
```

**Embedding similarity to audience brief:**
- Pre-compute a rolling "audience interest embedding" from the last 30 days of clicked items for this audience
- Cosine similarity between cluster summary embedding and audience interest embedding → 0–15 points
- On first run (no click history): use a static "seed embedding" derived from the audience profile text

**Negative topic suppression:**
```python
negative_overlap = set(cluster.topic_tags) & set(audience_profile.negative_topics)
if negative_overlap:
    final_audience_score *= 0.1  # near-complete suppression
```

**Geo boost:**
```python
cluster_regions = set(cluster.entities.get('regions', []))
interest_regions = set(audience_profile.geo_focus)
if cluster_regions & interest_regions:
    geo_boost = 10
```

### 6.3 Editorial Guardrails (enforced before output)

1. No item with `source_tier = 4` and no corroborating Tier 1–3 article in the cluster can appear in positions 1–3 of any section.
2. Every selected item must have an assigned `section` value from the defined taxonomy.
3. `include_community_signals = False` → all `source_tier = 4` only clusters are removed from candidate list.
4. `include_speculative_analysis = False` → items with `confidence_tag = 'weak_signal'` are removed.
5. Maximum items per section is 3 (prevents single-topic domination).
6. Items with `delivery_status = 'suppressed'` in the last 7 days are excluded from candidates.

### 6.4 Two-Stage Rendering Pipeline

**Stage 1: Common Editorial Bundle (runs once per day)**

Inputs: All globally-scored story clusters from the past 48 hours with `novelty_status IN ('new', 'follow_up')`

Process:
1. Apply base global scoring to all candidates.
2. Select the top 60–80 clusters by global score as the candidate pool.
3. Generate shared LLM content for each cluster (neutral headline, factual 2–4 sentence summary, key entities, confidence tag). This is the shared computation; no audience persona is injected here.
4. Store as `canonical_bundle` in memory/Redis for the day's run.

**Stage 2: Audience-Specific Selection (runs 4× in parallel)**

For each audience:
1. Apply `audience_relevance_score` to all 60–80 bundle items.
2. Re-rank by `final_audience_score`.
3. Apply editorial guardrails.
4. Select top 8–15 items.
5. Group and order by section (section order is determined by section_weights, highest weight → first).
6. Generate audience-specific content via Claude claude-opus-4-5:
   - Audience-aware headline variant
   - OCI implication paragraph (audience-specific angle)
   - Watch item (optional, for top 2–3 items)
   - Commentary tone injection per `preferred_tone`
7. Enforce `max_length` word count budget.
8. Assemble final ordered item list → pass to renderer.

**Section ordering per audience (example for Karan):**

Section weights: Financial (35%), Compete (25%), Datacenter (15%), AI (15%), Deals (10%)
→ Section order in email: Market & Financial → Competitive Moves → Power & Datacenter → AI Platform → Deals → OCI Implications

### 6.5 Audience Profile Reference

| Attribute | Karan | Nathan | Greg | Mahesh |
|-----------|-------|--------|------|--------|
| Role | SVP Product Mgmt | SVP Product Strategy | EVP Data/AI | EVP Security & Dev Platform |
| Top section | Financial (35%) | Multi-cloud (30%) | Compete (35%) | Datacenter (25%) |
| 2nd section | Compete (25%) | AI (25%) | AI (35%) | Deals (20%) |
| 3rd section | Datacenter (15%) | Deals (25%) | OSS/Innovation (15%) | AI (20%) |
| Tone | Concise, strategic, implication-heavy | Ecosystem-oriented, partner-aware | Technical executive, capability gaps | Platform, resilience, scale readiness |
| Community signals | No | Yes | Yes (GitHub/OSS focus) | No |
| Speculative analysis | No | Yes | Yes | No |

---

## 7. LLM Generation Design

### 7.1 Prompt Architecture

**Stage 1 prompt (shared neutral summary) — Claude claude-opus-4-5:**

```
System:
You are an editorial assistant for a technology intelligence briefing for senior executives
at Oracle Cloud Infrastructure. Your summaries must be factual, precise, and grounded in
the provided source text. Do not speculate beyond what the sources state. Maintain a
neutral professional tone.

User:
Source article title: {title}
Source article body: {body_text[0:3000]}
Source: {source_name} ({source_tier_label})
Published: {published_at}
Confidence tag: {confidence_tag}
Entities identified: {entities_json}
Event type: {event_type}

Generate:
1. canonical_headline: A factual headline under 15 words. Do not editorialize.
2. neutral_summary: 2–4 sentences covering who, what, when, where.
   Include specific numbers and named entities.
   If confidence_tag is 'credible_report' or 'weak_signal', acknowledge uncertainty.
3. key_facts: List 2–4 bullet-point facts with specific figures where available.
4. relevance_to_cloud_infra: 1 sentence on why this matters to cloud infrastructure.

Return as JSON with keys: canonical_headline, neutral_summary, key_facts, relevance_to_cloud_infra.
```

**Stage 2 prompt (audience-specific) — Claude claude-opus-4-5:**

```
System:
You are a strategic intelligence analyst briefing {display_name}, {title} at Oracle Cloud
Infrastructure. Your job is to contextualize technology news specifically for their role
and decision-making needs.

Persona: {preferred_tone description}
Focus areas: {topics_of_interest joined as natural language}
Companies of strategic interest: {companies_of_interest joined}
Time horizon: {time_horizon}

Writing constraints:
- Tone: {preferred_tone}
- Maximum words for this item: {per_item_word_budget}
- Include speculative analysis: {include_speculative_analysis}
{follow_up_instruction if novelty_status == 'follow_up'}

User:
Canonical headline: {canonical_headline}
Neutral summary: {neutral_summary}
Key facts: {key_facts}
Relevance to cloud infra: {relevance_to_cloud_infra}
Section: {section}
Confidence tag: {confidence_tag}

Generate:
1. audience_headline: A headline variant tailored to {display_name}'s perspective.
   Under 15 words. May be more pointed or strategic than the canonical headline.
2. oci_implication: 2–3 sentences on what this means specifically for OCI.
   Be concrete. Reference competitive position, opportunity, or risk.
3. watch_item (optional, only if this is a top-tier story): One sentence on what to monitor next.

Return as JSON with keys: audience_headline, oci_implication, watch_item.
```

**Classification prompts — Claude claude-haiku-4-5:**

Event type classification (fast, single token output):
```
Classify the primary event in this article headline into exactly one of these categories:
launched | partnered | raised | expanded | delayed | sued | announced | shipped |
confirmed | denied | filed | other
Headline: {title}
Return only the single category word.
```

Topic taxonomy (fast, multi-label):
```
Classify this article into all relevant categories from this list:
financial | power | datacenter | compete | ai | deals | community | security
Article title: {title}
First 200 words: {body_text[0:200]}
Return a JSON array of matching category strings.
```

### 7.2 Audience Tone Persona Injection

Each audience profile contains a `preferred_tone` string that is expanded into a persona description injected into Stage 2 system prompts:

| Audience | Tone string | Expanded persona injection |
|----------|-------------|---------------------------|
| Karan | `concise, high signal, strategic, implication-heavy` | "Write with maximum signal density. Lead with implications and strategic conclusions before facts. Avoid padding. Every sentence must add distinct value. Karan reads in under 2 minutes." |
| Nathan | `ecosystem-oriented, partner-aware, customer-facing implications` | "Frame every story through the lens of partner ecosystems, customer impact, and multi-cloud positioning. Highlight alliance opportunities and commercial motion." |
| Greg | `technical but executive, focuses on capability gaps and opportunities` | "Balance technical depth with executive framing. Identify capability gaps vs. competitors. Note OSS momentum and developer ecosystem implications. Greg will want to know what Oracle can or should build." |
| Mahesh | `Platform, resilience, secure operations, scale readiness` | "Emphasize platform reliability, security architecture implications, developer experience, and operational readiness at scale. Flag risks to uptime, data sovereignty, and platform integrity." |

### 7.3 Model Selection

| Task | Model | Rationale |
|------|-------|-----------|
| Stage 1 neutral summary generation | `claude-opus-4-5` | Highest quality factual synthesis; run once per article |
| Stage 2 audience-specific generation | `claude-opus-4-5` | Requires nuanced persona adherence and strategic reasoning |
| Event type classification | `claude-haiku-4-5` | Single-token output; high volume; speed and cost priority |
| Topic taxonomy tagging | `claude-haiku-4-5` | Short structured output; high volume |
| Fact delta extraction | `claude-haiku-4-5` | Structured JSON extraction; speed-critical; run per article |
| Confidence tag assignment | `claude-haiku-4-5` | Simple 4-class classification |

### 7.4 Token Budget Estimation

**Per daily run (4 recipients, 40–80 raw articles, 20–30 clusters reaching generation):**

| Task | Calls | Avg tokens/call | Total tokens |
|------|-------|----------------|--------------|
| Stage 1 generation (claude-opus-4-5) | 25 clusters | 4,000 in / 600 out | 115,000 |
| Stage 2 generation (claude-opus-4-5) | 25 × 4 audiences | 1,500 in / 400 out | 190,000 |
| claude-haiku-4-5 classification (event, topic, fact, confidence) | 80 articles × 4 tasks | 400 in / 50 out | 144,000 |
| **Daily total (Opus)** | | | ~305,000 |
| **Daily total (Haiku)** | | | ~144,000 |

**Cost estimate (2026 pricing, approximate):**
- claude-opus-4-5: ~$0.015/1K input, ~$0.075/1K output → ~$18–25/day
- claude-haiku-4-5: ~$0.00025/1K input, ~$0.00125/1K output → ~$0.25/day
- **Total: ~$18–26/day**

### 7.5 Failure Handling

| Failure mode | Detection | Response |
|-------------|-----------|----------|
| LLM API timeout | Timeout after 30s | Retry with exponential backoff (max 3 attempts) |
| LLM API rate limit (429) | HTTP 429 response | Exponential backoff + jitter; alert if >5 consecutive failures |
| Malformed JSON response | JSON parse error | Re-prompt with stricter schema instruction; fall back to raw text if second attempt fails |
| claude-opus-4-5 unavailable | HTTP 5xx | Fall back to `claude-sonnet-4-5` for Stage 1/2; log degradation event |
| Complete LLM failure | All retries exhausted | Use canonical headline and first 2 sentences of article as fallback; mark item as `llm_fallback = true`; include in email with "(Auto-summary unavailable)" notice |
| Token limit exceeded | claude-opus-4-5 max context | Truncate `body_text` to 2,500 tokens and retry |
| Delivery deadline risk | Pipeline running >3.5h | Skip Stage 2 speculative items; reduce to top 8 items per audience; send with best available content |

---

## 8. Delivery Architecture

### 8.1 Postmark Integration

**API endpoint:** `POST https://api.postmarkapp.com/email`

**Approach:** Raw HTML (not Postmark templates) — full control over layout, tracking injection, and feedback controls.

**Request structure:**
```json
{
  "From": "OCI Briefing <briefing@yourorg.com>",
  "To": "{audience_email}",
  "Subject": "OCI Daily Briefing — {briefing_date} | {top_headline_teaser}",
  "HtmlBody": "{full_rendered_html}",
  "TrackOpens": false,
  "TrackLinks": "None",
  "MessageStream": "outbound",
  "Metadata": {
    "briefing_date": "{date}",
    "audience_id": "{audience_id}"
  }
}
```

Note: Postmark's built-in open and link tracking is disabled (`TrackOpens: false`, `TrackLinks: None`) because we implement custom tracking for richer analytics metadata. Postmark's tracking would strip our custom redirect URLs.

**Bounce handling:** Configure Postmark webhook to `POST /webhooks/postmark/bounce`. On hard bounce: mark audience as `is_active = false` and alert. On soft bounce: retry next day.

**Idempotency:** Before sending, check `delivered_items` for `(briefing_date, audience_id)` with `delivery_status = 'sent'`. Do not re-send on retry if already delivered.

### 8.2 Open Tracking Pixel

Injected as the last `<img>` tag in the HTML body:

```html
<img src="https://tracking.briefing.yourorg.com/pixel/{briefing_date}/{audience_id}.gif"
     width="1" height="1" alt="" style="display:none;" />
```

**Tracking endpoint behavior:**
```
GET /pixel/{briefing_date}/{audience_id}.gif
→ Return: 1×1 transparent GIF (Content-Type: image/gif)
→ Log: INSERT INTO tracking_events (event_type='open', briefing_date, audience_id, occurred_at)
→ Headers: Cache-Control: no-cache, no-store (prevent caching from hiding opens)
```

**Caveats:** Apple Mail Privacy Protection pre-fetches pixels; record only the first open per audience per day. Flag opens occurring within 10 seconds of delivery as likely pre-fetch.

### 8.3 Click Tracking Redirect Service

**Endpoint:** `GET /click/{briefing_date}/{audience_id}/{cluster_id}`

**Implementation:** OCI Function (Python) backed by a Postgres connection pool.

**Handler logic:**
```python
def handler(ctx, data):
    path_parts = ctx.path.split('/')
    briefing_date, audience_id, cluster_id = path_parts[2], path_parts[3], path_parts[4]

    # Lookup canonical URL (no Postgres hit on hot path if Redis cache available)
    link = db.query(TrackingLink).filter_by(
        briefing_date=briefing_date,
        audience_id=audience_id,
        cluster_id=cluster_id
    ).first()

    if not link:
        return Response(status=404)

    # Async write to tracking_events (fire-and-forget, don't block redirect)
    db.execute(INSERT_TRACKING_EVENT, {
        'event_type': 'click',
        'briefing_date': briefing_date,
        'audience_id': audience_id,
        'cluster_id': cluster_id,
        'tracking_link_id': link.id,
        'section': link.section,
        'position_in_section': link.position_in_section,
        'position_global': link.position_global,
        'source_name': link.source_name,
        'ip_address': ctx.request.remote_addr,
        'user_agent': ctx.request.headers.get('User-Agent')
    })

    return Response(status=302, headers={'Location': link.canonical_url})
```

**Performance:** Target P99 redirect latency < 200ms. Cache `tracking_links` in Redis with 24h TTL.

### 8.4 OCI Object Storage

**Bucket structure:**
```
bucket: oci-briefing-archive
  briefings/
    2026-03-10/
      karan.html
      nathan.html
      greg.html
      mahesh.html
    2026-03-09/
      ...
  assets/
    style.css           (shared stylesheet, CDN-cacheable)
    logo.png
```

**Naming convention:** `briefings/{YYYY-MM-DD}/{audience_id}.html`

**Access:** Bucket is private. Generate Pre-Authenticated Requests (PAR) with 365-day expiry per file for archive links. PARs are stored in `delivered_items.archive_url`.

**Lifecycle policy:** Retain all briefings indefinitely (storage cost is negligible at this scale). At 50+ recipient scale, consider 2-year retention policy.

### 8.5 Scheduling and Retry Logic

**OCI Scheduler cron expression:** `0 4 * * *` (04:00 UTC daily = ~8–9 PM US Pacific, emails land before 6 AM Pacific)

**Pipeline stage sequence with retry:**
```
1. Ingestion (all sources)        → timeout: 30min, retries: 3
2. Normalization & Enrichment     → timeout: 20min, retries: 3
3. Story Intelligence             → timeout: 15min, retries: 2
4. Audience Ranking               → timeout: 5min,  retries: 2
5. LLM Generation (parallelized)  → timeout: 30min, retries: 3
6. Rendering                      → timeout: 10min, retries: 2
7. Delivery                       → timeout: 10min, retries: 3
─────────────────────────────────────────────────────────────
Total pipeline SLA: < 2 hours (deliver by 06:00 UTC)
```

**Failure alerting:**
- Any stage failure after all retries: OCI Notifications → email alert to engineering on-call
- Pipeline total runtime > 90 minutes: warning alert
- Delivery failure for any audience: individual alert with audience_id and postmark error

**Manual recovery:** Each stage can be re-run independently by passing `--stage {stage_name} --date {date}` arguments to the orchestrator script. Stages are idempotent.

---

## 9. Telemetry & Feedback Loop

### 9.1 Tracking Link Structure

Every in-email story link is replaced with a tracking redirect URL:

```
https://tracking.briefing.yourorg.com/click/{briefing_date}/{audience_id}/{cluster_id}
```

Example:
```
https://tracking.briefing.yourorg.com/click/2026-03-10/karan/3f7a2b1c-...
```

The redirect handler resolves the canonical URL from `tracking_links` and logs the event.

### 9.2 Data Captured Per Click

```
audience_id         Who clicked
briefing_date       Which day's briefing
cluster_id          Which story
section             Which section the story appeared in
position_in_section 1-indexed position within section (first, second, third item?)
position_global     1-indexed position in the entire email
source_name         Publication name (e.g., "Reuters")
source_tier         1–4
occurred_at         Timestamp
ip_address          For deduplication only; purged after 24h (see Section 12)
user_agent          Browser/email client detection
```

### 9.3 Feedback Endpoint

Feedback buttons are rendered as plain `<a>` tags (image fallback for email clients) pointing to:

```
https://tracking.briefing.yourorg.com/feedback?
    audience_id={audience_id}&
    cluster_id={cluster_id}&
    date={briefing_date}&
    type={feedback_type}&
    sig={hmac_signature}
```

The `sig` parameter is an HMAC-SHA256 signature over `{audience_id}:{cluster_id}:{date}:{type}` using a server-side secret — prevents spoofed feedback submissions.

**Endpoint handler:**
```
GET /feedback (parameters as above, to work in email clients that don't support POST)
→ Validate HMAC signature
→ INSERT INTO feedback_events (...)
→ Return: 200 OK with HTML body "Thank you for your feedback." (no redirect, avoids client loading external page)
```

**Feedback types exposed in email:**

Per-story controls (small text links below each article):
- "More like this" → `type=more_like_this`
- "Less like this" → `type=less_like_this`
- "👍" → `type=thumbs_up`
- "👎" → `type=thumbs_down`

Section-level control (bottom of each section):
- "Too repetitive in this section" → `type=too_repetitive`

### 9.4 Feedback Integration into Profile Weights

**Phase 1 (MVP — manual review):**
- `feedback_events` records accumulate with `review_status = 'pending'`
- Weekly: engineering review of feedback summary query:
```sql
SELECT audience_id, cluster_id, feedback_type, COUNT(*) as count
FROM feedback_events
WHERE review_status = 'pending'
GROUP BY audience_id, cluster_id, feedback_type
ORDER BY audience_id, count DESC;
```
- Manual update to `audience_profiles.section_weights` or `topics_of_interest` based on patterns
- Mark feedback records as `review_status = 'applied'`

**Phase 2 (automated, post-MVP):**
- `more_like_this` / `thumbs_up` → +0.05 weight for cluster's `primary_topic` in `learned_topic_weights`
- `less_like_this` / `thumbs_down` → -0.05 weight for cluster's `primary_topic`
- `too_repetitive` → increase `duplication_penalty` threshold for this audience
- Weights are capped: section weights bounded [0.05, 0.60], sum normalized to 1.0
- `learned_topic_weights` blended with static `section_weights` at 30%/70% ratio initially, increasing toward 50%/50% as confidence builds
- Changes applied on Sunday night for the coming week; retained in `audience_profiles.learned_topic_weights`

### 9.5 Analytics Queries

**Email engagement summary (daily):**
```sql
SELECT
    te.audience_id,
    te.briefing_date,
    COUNT(*) FILTER (WHERE te.event_type = 'open') AS opens,
    COUNT(*) FILTER (WHERE te.event_type = 'click') AS clicks,
    COUNT(DISTINCT te.cluster_id) FILTER (WHERE te.event_type = 'click') AS unique_stories_clicked
FROM tracking_events te
GROUP BY te.audience_id, te.briefing_date
ORDER BY te.briefing_date DESC;
```

**Top clicked section by audience:**
```sql
SELECT audience_id, section, COUNT(*) AS clicks
FROM tracking_events
WHERE event_type = 'click'
  AND briefing_date >= CURRENT_DATE - 30
GROUP BY audience_id, section
ORDER BY audience_id, clicks DESC;
```

---

## 10. API Contracts

All internal services communicate via JSON over HTTP or via direct function call within the pipeline process. At MVP scale, these are in-process Python interfaces. At production scale, they become HTTP microservice contracts.

### 10.1 Ingestion → Normalization

**Message on `raw_article_queue`:**
```json
{
  "ingestion_source": "rss | newsapi | bing | gdelt | hn | reddit | github | crawler | newsletter",
  "fetched_at": "2026-03-10T04:12:33Z",
  "raw_url": "https://example.com/original-url",
  "title": "String: article title or RSS entry title",
  "raw_body": "String: raw HTML or plain text as fetched",
  "published_at": "2026-03-10T02:00:00Z | null",
  "author": "String | null",
  "source_name": "Reuters",
  "source_tier": 2,
  "raw_payload": {}
}
```

### 10.2 Story Intelligence → Audience Ranking

**Ranked item schema (output of Global Scorer):**
```json
{
  "cluster_id": "uuid",
  "canonical_headline": "String",
  "neutral_summary": "String",
  "key_facts": ["String", "String"],
  "relevance_to_cloud_infra": "String",
  "primary_topic": "financial | power | datacenter | compete | ai | deals | community | security",
  "topic_tags": ["String"],
  "entities": {
    "companies": ["String"],
    "products": ["String"],
    "people": ["String"],
    "regions": ["String"]
  },
  "event_type": "launched | partnered | ...",
  "confidence_tag": "confirmed | credible_report | weak_signal | follow_up",
  "novelty_status": "new | follow_up | candidate_duplicate",
  "parent_cluster_id": "uuid | null",
  "prior_delivery_date": "2026-03-07 | null",
  "delta_fields": ["deal_size", "customer_name"],
  "source_name": "Reuters",
  "source_tier": 2,
  "published_at": "2026-03-10T02:00:00Z",
  "canonical_url": "https://example.com/article",
  "article_count": 4,
  "scores": {
    "source_credibility": 25.0,
    "momentum": 15.0,
    "strategic_impact": 18.0,
    "timeliness": 14.0,
    "novelty": 12.0,
    "duplication_penalty": 0.0,
    "global_score": 84.0
  }
}
```

### 10.3 Audience Ranking → LLM Generator

**Generation request schema:**
```json
{
  "audience_id": "karan",
  "display_name": "Karan Batta",
  "title": "SVP of Product Management, OCI",
  "preferred_tone": "concise, high signal, strategic, implication-heavy",
  "topics_of_interest": ["financial analysis", "cloud infrastructure", "competitive strategy"],
  "companies_of_interest": ["AWS", "Azure", "Google Cloud", "NVIDIA", "AMD"],
  "include_speculative_analysis": false,
  "max_words_per_item": 200,
  "items": [
    {
      "cluster_id": "uuid",
      "section": "financial",
      "position_global": 1,
      "position_in_section": 1,
      "canonical_headline": "String",
      "neutral_summary": "String",
      "key_facts": ["String"],
      "confidence_tag": "confirmed",
      "novelty_status": "new",
      "prior_delivery_date": null,
      "delta_fields": [],
      "source_name": "Reuters",
      "source_tier": 2,
      "article_body": "String (first 3000 chars)"
    }
  ]
}
```

### 10.4 LLM Generator → Renderer

**Rendered item schema:**
```json
{
  "audience_id": "karan",
  "briefing_date": "2026-03-10",
  "items": [
    {
      "cluster_id": "uuid",
      "section": "financial",
      "position_global": 1,
      "position_in_section": 1,
      "audience_headline": "String (audience-specific)",
      "neutral_summary": "String",
      "oci_implication": "String",
      "watch_item": "String | null",
      "key_facts": ["String"],
      "confidence_tag": "confirmed",
      "novelty_status": "new",
      "novelty_badge": null,
      "source_name": "Reuters",
      "source_tier": 2,
      "published_at": "2026-03-10T02:00:00Z",
      "canonical_url": "https://example.com/article",
      "tracking_path": "/click/2026-03-10/karan/uuid",
      "llm_fallback": false
    }
  ]
}
```

### 10.5 Click Tracking Redirect Endpoint

**Request:**
```
GET /click/{briefing_date}/{audience_id}/{cluster_id}
Headers: User-Agent, X-Forwarded-For
```

**Response (success):**
```
HTTP 302 Found
Location: https://canonical-article-url.com/...
Cache-Control: no-store
```

**Response (not found):**
```
HTTP 404 Not Found
Body: {"error": "tracking link not found"}
```

### 10.6 Open Pixel Endpoint

**Request:**
```
GET /pixel/{briefing_date}/{audience_id}.gif
```

**Response:**
```
HTTP 200 OK
Content-Type: image/gif
Content-Length: 35
Cache-Control: no-cache, no-store, must-revalidate
Pragma: no-cache
Body: [1x1 transparent GIF binary]
```

### 10.7 Feedback Endpoint

**Request:**
```
GET /feedback?audience_id=karan&cluster_id={uuid}&date=2026-03-10&type=more_like_this&sig={hmac}
```

**Response (success):**
```
HTTP 200 OK
Content-Type: text/html
Body: <html><body><p>Thank you for your feedback.</p></body></html>
```

**Response (invalid signature):**
```
HTTP 403 Forbidden
Body: {"error": "invalid signature"}
```

**Response (invalid feedback type):**
```
HTTP 400 Bad Request
Body: {"error": "unknown feedback type"}
```

---

## 11. Deployment Topology on OCI

### 11.1 MVP: Single VM Architecture

For the initial deployment with 4 recipients, a single OCI Compute VM is sufficient and dramatically reduces operational complexity.

```
OCI Tenancy: briefing-prod
├── Compartment: briefing
│   ├── Compute Instance (VM.Standard.E4.Flex, 2 OCPU, 16GB RAM)
│   │   ├── Python pipeline application (all stages, sequential)
│   │   ├── FastAPI tracking service (Gunicorn, 4 workers)
│   │   └── Qdrant (Docker, port 6333, local volume)
│   │
│   ├── OCI Database System: PostgreSQL 15
│   │   └── db.Standard.E4.Flex.1.16GB (1 OCPU, 16GB)
│   │
│   ├── OCI Object Storage
│   │   └── Bucket: oci-briefing-archive (private, PAR-enabled)
│   │
│   ├── OCI Vault
│   │   └── Secret bundle: API keys (see Section 12)
│   │
│   ├── OCI Notifications
│   │   └── Topic: briefing-alerts → email subscriptions
│   │
│   └── OCI Scheduler
│       └── Cron job: 04:00 UTC daily → HTTP call to pipeline trigger endpoint
│
└── VCN: briefing-vcn
    ├── Public subnet: tracking service (HTTPS 443 inbound)
    └── Private subnet: compute VM ↔ Postgres (no public IP on DB)
```

**OCI Scheduler configuration:**
- Trigger: HTTP action → `POST http://localhost:8080/trigger/run-pipeline` (internal VM endpoint)
- Alternative: OCI Scheduler → OCI Function (triggers pipeline via OCI SDK call to VM)

### 11.2 Target Production: Microservices Architecture (Post-MVP)

When scaling to 50+ recipients or multiple organizations:

```
OCI Tenancy: briefing-prod
├── OCI Container Registry
│   ├── briefing/ingestion:latest
│   ├── briefing/normalization:latest
│   ├── briefing/story-intelligence:latest
│   ├── briefing/audience-ranking:latest
│   ├── briefing/llm-generation:latest
│   ├── briefing/renderer:latest
│   └── briefing/tracking-service:latest
│
├── OCI Container Instances or OKE (Kubernetes)
│   └── One container per service, scaled independently
│
├── OCI Queue (managed message queue)
│   ├── raw-articles-queue
│   ├── normalized-articles-queue
│   └── generation-requests-queue
│
├── OCI Autonomous Database (PostgreSQL-compatible)
│   └── Auto-scaling, managed backups
│
├── OCI Functions (serverless)
│   ├── click-tracker
│   └── open-tracker
│
└── OCI API Gateway
    └── Routes: /click/*, /pixel/*, /feedback → Functions
```

### 11.3 Network and Security

```
VCN: 10.0.0.0/16
├── Public Subnet: 10.0.1.0/24
│   ├── Load Balancer (HTTPS termination, SSL cert via OCI Certificates)
│   └── NAT Gateway (for VM outbound internet access)
│
└── Private Subnet: 10.0.2.0/24
    ├── Compute VM (pipeline + tracking service)
    └── PostgreSQL DB System
        └── Security List: allows TCP 5432 from 10.0.2.0/24 only

Internet Gateway → Public Subnet → Load Balancer → Compute VM:8443
```

**Security List rules:**
- Inbound 443: from 0.0.0.0/0 to Load Balancer
- Inbound 5432: from private subnet CIDR to DB only
- Outbound 443: from VM to internet (API calls to NewsAPI, Anthropic, Postmark, etc.)
- No direct inbound to VM from internet

---

## 12. Security Considerations

### 12.1 API Key Management

All secrets stored in OCI Vault as Secret bundles. Never in environment variables, config files, or source code.

| Secret name | Contents | Rotation policy |
|-------------|----------|-----------------|
| `newsapi-key` | NewsAPI API key | Quarterly |
| `bing-news-key` | Azure Cognitive Services key | Quarterly |
| `anthropic-key` | Anthropic API key | Quarterly |
| `postmark-server-token` | Postmark server API token | Quarterly |
| `reddit-credentials` | Reddit app client_id + secret | Quarterly |
| `github-token` | GitHub personal access token (read-only) | Quarterly |
| `postgres-credentials` | DB username + password | Monthly |
| `feedback-hmac-secret` | HMAC secret for feedback URL signing | Quarterly |
| `oci-object-storage-par-key` | PAR signing key | As needed |

**Access pattern:** Pipeline application retrieves secrets at startup via OCI SDK using Instance Principal authentication (no credentials stored on VM). Secrets cached in-memory for the pipeline run duration only.

### 12.2 Recipient Email Addresses

- Email addresses stored in `audience_profiles.email_address` column
- Column encrypted at the Postgres column level using `pgcrypto` (`pgp_sym_encrypt`)
- Decrypted only at delivery time in the Delivery Service module
- Email addresses never written to logs, tracking events, or Object Storage
- `audience_id` (opaque slug: 'karan', 'nathan', etc.) is used in all tracking tables instead of email

### 12.3 Click Tracking Data — Retention Policy

- `tracking_events.ip_address`: purged via scheduled job after 24 hours (not needed for analytics, only for deduplication of click events within the same session)
- `tracking_events.user_agent`: retained for 90 days (email client analytics), then anonymized
- All other tracking event fields: retained indefinitely for longitudinal analytics
- `feedback_events`: retained indefinitely; no PII present
- Tracking URLs do not contain any PII; `audience_id` is an opaque identifier

### 12.4 OCI IAM Least Privilege

**Instance Principal Dynamic Group:** `briefing-pipeline-instances` (matches Compute VM OCID)

**IAM Policy:**
```
Allow dynamic-group briefing-pipeline-instances to read secret-bundle in compartment briefing
  where target.secret.name in ('newsapi-key', 'bing-news-key', 'anthropic-key', 'postmark-server-token', 'reddit-credentials', 'github-token', 'postgres-credentials', 'feedback-hmac-secret')

Allow dynamic-group briefing-pipeline-instances to manage objects in compartment briefing
  where target.bucket.name = 'oci-briefing-archive'

Allow dynamic-group briefing-pipeline-instances to use ons-topics in compartment briefing
  where target.topic.name = 'briefing-alerts'
```

**Database user:**
```sql
-- Application DB user: briefing_app
-- Permissions: SELECT, INSERT, UPDATE on all briefing tables
-- No: DROP, CREATE, TRUNCATE, pg_dump
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO briefing_app;
REVOKE DELETE ON feedback_events FROM briefing_app;  -- feedback is append-only
REVOKE DELETE ON tracking_events FROM briefing_app;  -- events are append-only
```

### 12.5 Additional Security Controls

- **HTTPS only:** All tracking endpoints served over TLS 1.3; HSTS enforced
- **Input validation:** All ingest content is treated as untrusted; HTML is sanitized before storage with `bleach`; no eval or exec of ingested content
- **SQL injection:** All database queries use parameterized statements (SQLAlchemy ORM or psycopg2 with `%s` params)
- **Dependency scanning:** `pip-audit` in CI/CD pipeline
- **Secret scanning:** `detect-secrets` pre-commit hook

---

## 13. Scalability Notes

### 13.1 Current Scale (MVP)

| Dimension | Current | Approach |
|-----------|---------|----------|
| Recipients | 4 | Single Postgres rows, no sharding needed |
| Articles/day | 40–80 | Single-VM pipeline, sequential processing |
| Story clusters | 20–40 active | Qdrant single-node (< 1M vectors) |
| LLM generation calls | ~125/day | Within Anthropic rate limits, no queue needed |
| Object storage | ~4 HTML files/day | Negligible cost and complexity |
| Tracking events | < 200/day | Postgres handles easily without partitioning |

### 13.2 Future Scale (50+ Recipients, Multiple Organizations)

| Dimension | Future | Required change |
|-----------|--------|----------------|
| Recipients | 50–500 | Shard `audience_profiles` and `delivered_items` by `org_id`; parallelize LLM generation across recipient cohorts |
| Articles/day | 200–500 | Async ingestion workers (OCI Queue + consumer workers); parallel normalization |
| Story clusters | 50–150 active | Qdrant cluster mode (3 nodes); or migrate to pgvector on Autonomous DB for operational simplicity |
| LLM generation | 1,000+/day | Request batching; Anthropic Batch API for Stage 1 (shared) generation; Stage 2 parallelized by audience |
| Tracking events | 2,000–10,000/day | Partition `tracking_events` by `briefing_date` (monthly partitions); consider TimescaleDB |
| HTML delivery | 50+ files/day | OCI Object Storage scales automatically; consider CloudFront-equivalent CDN (OCI CDN) for public archive URLs |

### 13.3 Specific Architectural Changes at Scale

**Multi-tenancy:** Add `org_id` to `audience_profiles`, `delivered_items`, `tracking_links`, `tracking_events`, and `feedback_events`. Row-level security in Postgres to isolate organizations.

**Async pipeline:** Replace synchronous pipeline script with Prefect or Temporal DAG. Ingestion, normalization, and enrichment become async tasks consuming from OCI Queue. LLM generation requests are enqueued and consumed by a worker pool.

**Vector store:** At >5M vectors (multiple orgs, months of history), evaluate pgvector on Autonomous DB (simpler operational model) versus Qdrant cluster mode (higher performance). At 50M+ vectors: Qdrant cluster mode with replication is the clear choice.

**CDN for archives:** At 50+ recipients, use OCI CDN (or Cloudflare) in front of Object Storage for archive HTML serving. Reduces OCI Object Storage egress costs and improves load times for web archive views.

**LLM cost control at scale:** With 500 recipients, Stage 1 (shared generation) remains fixed at ~25 LLM calls/day regardless of recipient count. Only Stage 2 scales linearly with recipients. At 500 recipients, consider batching Stage 2 by audience persona cluster (e.g., all "concise/strategic" personas share a prompt variant) to reduce generation calls by 80%.

**Database connection pooling:** At 50+ recipients with parallel pipeline workers, use PgBouncer in transaction mode in front of PostgreSQL to manage connection limits. OCI DB System PostgreSQL supports up to 500 connections; pipeline workers should not exceed 20 concurrent connections.

---

*This document reflects the system design as of 2026-03-10. It should be treated as the authoritative reference for MVP implementation. Sections marked "Post-MVP" or describing "Phase 2" behavior are forward-looking design notes and should not block the initial implementation.*

*Engineers implementing this system should start with Section 4 (Data Models), Section 5 (Deduplication), and Section 8 (Delivery) as the highest-priority implementation targets.*
