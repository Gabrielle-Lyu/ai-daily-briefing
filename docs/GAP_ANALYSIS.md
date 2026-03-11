# Gap Analysis: AI Daily Executive Briefing

**Date:** 2026-03-11
**Baseline:** PRD v1.0 (2026-03-10), Section 11 P0 Feature List
**Codebase assessed:** Phase 1 commit (1a627b7) on main branch

---

## 1. P0 Feature Gap Table

| P0 Feature | Status | Current Location | Gap Description |
|---|---|---|---|
| **Ingestion pipeline** | Partial | `briefing/ingest.py` | RSS feed polling works with concurrent fetching across 15 sources (Tiers 1-4). However, PRD requires source crawlers for Tier 1-3 beyond RSS, plus HN Algolia API and Reddit API fetchers. Current implementation only uses `feedparser` for RSS -- no dedicated community API integration, no web search API (Exa/Brave) for gap-filling, no SEC EDGAR or regulatory filing ingestion. |
| **Normalization** | Partial | `briefing/process.py` | Keyword-based section tagging exists (`_infer_sections`). Missing: NER entity extraction (spaCy or similar), canonical URL resolution, publisher metadata enrichment, headline/summary embeddings, `fact_signature` hash generation. Current normalization is keyword regex only -- no structured entity output. |
| **7-day deduplication (5-step pipeline)** | Missing | `briefing/process.py` | Only 2 of 5 pipeline steps are implemented: (1) URL exact-match dedup and (2) Jaccard title-word overlap at 80% threshold. Missing entirely: Step 1 embedding-based normalize, Step 2 story clustering into canonical clusters, Step 3 comparison against 7-day sent history (requires persistent storage), Step 4 fact-delta detection for follow-ups, Step 5 follow-up rendering with `[UPDATE]` labels. No vector search (Qdrant/PgVector). No 7-day memory -- everything is in-memory per run. No `StoryCluster` or `FactDelta` data model. No suppression log. |
| **Scoring engine (7 dimensions)** | Partial | `briefing/score.py` | 4 of 7 dimensions implemented: source credibility (static tier lookup), timeliness (age-based), section relevance (audience weight matching), keyword bonus (OCI keyword scan). Missing 3 dimensions: **audience_relevance** (PRD specifies company name match 35%, topic taxonomy 30%, embedding similarity 25%, geo focus 10% -- current impl uses only section weight overlap), **novelty** (requires 7-day cluster comparison with embeddings), **momentum** (multi-source coverage detection, HN/Reddit/GitHub velocity signals), **strategic_impact** (LLM-scored rubric for OCI threat/opportunity), **duplication_penalty** (requires novelty score). Also: scores are not normalized to 0-10 scale as PRD requires (current ranges: credibility 0-30, timeliness 0-15, relevance 0-40, keyword 0-10). No section diversity constraint (max 40% per section). |
| **Audience profiles** | Partial | `briefing/config.py` | All 4 executives defined (Karan, Nathan, Greg, Mahesh) with name, title, email, tone, section_weights, accent_color. Missing 7 of 10 PRD schema fields: `topics_of_interest`, `negative_topics`, `companies_of_interest`, `geo_focus`, `time_horizon`, `max_length`, `include_community_signals`, `include_speculative_analysis`. Profiles use a simplified schema that does not conform to the PRD `AudienceProfile` interface. |
| **Profile schema validation** | Missing | -- | No validation logic exists. PRD requires all 10 schema fields validated at load time with explicit error messages (weight sum = 1.0, min/max cardinality checks, enum validation, cross-field consistency warnings). |
| **8 briefing sections** | Partial | `briefing/render.py`, `briefing/config.py` | Section metadata defined in `render.py` for 12 section keys (ai, compete, financial, datacenter, power, deals, security, multicloud, oss, partnerships, community, infrastructure). However, the PRD specifies 8 canonical sections: Executive Summary, Financial, Power & Datacenter, Competitive Moves, AI Platform, Deals, Community Signal, OCI Implications. Current code does not enforce the canonical 8-section structure. Missing: per-audience length budgets per section, OCI Implications as a dedicated synthesized section (currently OCI implications are inline per-article, not a standalone section with `[THREAT]`/`[OPPORTUNITY]`/`[WATCH]`/`[ACTION]` labels). |
| **LLM generation** | Implemented | `briefing/llm.py` | Classification (Haiku) and per-audience summary generation (Sonnet) both work. Generates headline, summary, and OCI implication per article per audience. Executive summary generation with bullets and OCI implication of the day also works. Caching via JSON files. Retry logic with backoff. Uses `claude -p` subprocess invocation. This is the most complete P0 feature. |
| **Confidence tags** | Partial | `briefing/llm.py`, `briefing/render.py` | LLM classification returns `confidence: high/medium/low`. Render displays confidence pills with color coding. However, PRD specifies 4 tags: `confirmed`, `credible_report`, `weak_signal`, `follow_up` -- not high/medium/low. Tag assignment rules (Tier 1 source always at least `credible_report`, community always `weak_signal`) are not implemented. Speculative analysis filtering by audience (`include_speculative_analysis`) is not implemented. |
| **Source labels** | Implemented | `briefing/render.py` | Every rendered item displays source name, tier badge (color-coded), publication date, and relative time. Original article URL is linked from the headline. Meets PRD requirement. |
| **Editorial rules enforcement** | Missing | -- | 0 of 9 hardcoded rules are programmatically enforced. (1) Source labels exist but no validation gate. (2) No check preventing community posts as top story. (3) No 7-day dedup enforcement. (4) No gate requiring OCI implication (items render even without one). (5) No max word count enforcement per audience. (6) Cross-audience distinct wording is handled by separate LLM calls but not validated. (7) No suppression log. (8) No social buzz overfitting cap. (9) No primary source preference logic. |
| **HTML email delivery** | Missing | -- | No email delivery system. No Postmark integration. No email template (current HTML is web-optimized, not email-client compatible). No open/click tracking pixels. No plain-text fallback. No subject line or preheader generation. No unsubscribe link. |
| **Web archive copy** | Partial | `briefing/render.py`, `serve.py` | Static HTML files are saved to `output/{date}/` directory with per-audience and combined index files. `serve.py` provides a local HTTP server. However, PRD requires storage in OCI Object Storage with signed URLs and access control. Current storage is local filesystem only. Naming convention differs from PRD spec (`briefings/{audience_id}/{YYYY-MM-DD}/index.html`). |
| **Tracked links** | Missing | -- | No link tracking infrastructure. PRD requires per-audience, per-story tracking URLs (`https://track.oci-intel.oracle.com/c/{tracking_id}`), a redirect endpoint, and click event logging with full attribution (audience_id, briefing_date, section, story_id, source, position). |
| **Suppression log** | Missing | -- | No suppression log. PRD requires every scored-but-not-rendered article to be logged with reason (`duplicate_no_delta`, `below_score_threshold`, `section_budget_exceeded`), matched prior cluster ID, and similarity scores. No data model, no storage, no logging. |
| **Daily cron schedule** | Missing | -- | No scheduling mechanism. Pipeline runs manually via `python3 main.py`. PRD requires daily cron at 5:00 AM with delivery by 6:00 AM, error handling for pipeline failures, and configurable fallback to prior-day briefing. |
| **Basic feedback controls** | Missing | -- | No feedback mechanism. PRD requires at minimum thumbs up/thumbs down per story in the rendered output, with feedback events stored in a database. No feedback data model, no tracking endpoints, no feedback UI elements in rendered HTML. |
| **Email metrics** | Missing | -- | No metrics tracking. PRD requires open, click, CTR tracked via Postmark and stored per `(audience_id, briefing_date)`. No Postmark integration, no metrics storage, no reporting. |

---

## 2. Summary Scorecard

| Category | Implemented | Partial | Missing | Total |
|---|---|---|---|---|
| P0 Features | 2 | 7 | 8 | 17 |

**Fully implemented:** LLM generation, Source labels
**Partially implemented:** Ingestion pipeline, Normalization, Scoring engine, Audience profiles, Confidence tags, 8 briefing sections, Web archive copy
**Completely missing:** 7-day deduplication pipeline, Profile schema validation, Editorial rules enforcement, HTML email delivery, Tracked links, Suppression log, Daily cron schedule, Basic feedback controls, Email metrics

---

## 3. Critical Fixes Before Executive Use

These items must be resolved before the briefing can be shown to any executive. They are ordered by risk severity.

### 3.1 Scoring Engine Must Use All 7 Dimensions (Currently 4 of 7)

**Risk:** Articles are ranked incorrectly. Without novelty, momentum, and strategic impact scoring, the briefing surfaces low-value content and misses high-value content.

**What to fix:**
- Normalize all scores to 0-10 scale (current ranges are inconsistent: 0-30, 0-15, 0-40, 0-10)
- Implement audience relevance with company name matching, topic matching, and geo focus
- Add strategic impact scoring via LLM call during classification
- Add momentum detection (multi-source coverage counting)
- Novelty and duplication penalty require persistent storage (see 3.2)
- Add section diversity constraint: no section > 40% of bundle

### 3.2 Persistent Storage Required (Currently All In-Memory)

**Risk:** Without a database, there is no 7-day dedup window, no suppression log, no feedback storage, no email metrics. The system forgets everything between runs.

**What to fix:**
- Add PostgreSQL (or SQLite for MVP) with tables for: articles, story_clusters, delivered_items, suppression_log, feedback_events, email_events
- Store canonical bundle and delivery records per run
- Enable 7-day lookback for dedup comparisons
- Store LLM cache in database instead of filesystem JSON (more reliable)

### 3.3 Deduplication Pipeline Is Non-Functional (2 of 5 Steps)

**Risk:** Executives will see the same story repeated across days. This is the single biggest trust-destroyer identified in the PRD. Current Jaccard title overlap is a trivial heuristic that will miss most real-world duplicates (same event, different headline wording).

**What to fix:**
- Implement embedding-based similarity (headline + summary vectors)
- Build story cluster model with persistent storage
- Implement 7-day sent-item comparison
- Add fact-delta detection for follow-up identification
- Add follow-up rendering with `[UPDATE]` labels
- Log all suppressed items with reasons

### 3.4 Audience Profiles Must Match PRD Schema (7 of 10 Fields Missing)

**Risk:** Without `topics_of_interest`, `negative_topics`, `companies_of_interest`, and `include_community_signals`, personalization is superficial. All executives get nearly the same content with slightly different ordering.

**What to fix:**
- Add all 10 PRD schema fields to each profile in config.py
- Implement schema validation at load time
- Wire `topics_of_interest` and `companies_of_interest` into scoring
- Wire `include_community_signals` and `include_speculative_analysis` into rendering filters
- Enforce `max_length` word budgets in render pipeline

### 3.5 Confidence Tags Must Use PRD Vocabulary

**Risk:** Current `high/medium/low` tags do not communicate the editorial meaning the PRD intends. Executives need to know if something is `confirmed` (official source) vs. `weak_signal` (speculation) -- not just a generic confidence level.

**What to fix:**
- Change classification to output `confirmed`, `credible_report`, `weak_signal`, `follow_up`
- Implement source-tier-based tag floor (Tier 1 = at least `credible_report`)
- Filter `weak_signal` items for audiences with `include_speculative_analysis: none/limited`

### 3.6 OCI Implications Section Missing as Standalone Section

**Risk:** The PRD's most differentiated feature -- a dedicated section synthesizing OCI-specific threats, opportunities, and actions -- does not exist. Per-article OCI implications exist inline, but the standalone synthesized section with `[THREAT]`/`[OPPORTUNITY]`/`[WATCH]`/`[ACTION]` labels is not rendered.

**What to fix:**
- Add LLM prompt to generate 2-4 OCI implication items with labels
- Render as a dedicated end-of-briefing section
- Ensure every body item maps to at least one OCI implication (tracked internally)

### 3.7 Editorial Rules Not Enforced

**Risk:** Without programmatic enforcement of the 9 editorial rules, the briefing will produce output that violates the content governance contract. Community posts could appear as top stories. Items without OCI implications could render. Word budgets could be blown.

**What to fix:**
- Add a validation pass before rendering that checks all 9 rules
- Gate rendering on: source label present, OCI implication present, word budget met
- Implement community post demotion (no Tier 4 in exec summary or as section lead)
- Add primary source preference when multiple articles cover same story

---

## 4. Phase 2 Backlog

### P1 Features (Target: 30-60 Days Post-Launch)

| Feature | Description | Dependencies |
|---|---|---|
| Full feedback controls | Five-option feedback (Useful / Not useful / Too repetitive / More like this / Less like this) per story | Requires: feedback tracking endpoints, database |
| Feedback-driven profile updates | Explicit feedback adjusts audience scoring weights automatically | Requires: feedback storage, profile update logic |
| Personalization metrics dashboard | Topic affinity, source affinity, article length preference per audience | Requires: database, analytics queries, web UI |
| Slack/Chat delivery | Condensed executive summary for Slack channels via Block Kit | Requires: Slack API integration, pluggable render layer |
| Source registry management UI | Admin interface to classify new sources and set tier scores | Requires: web admin UI, source registry in database |
| Newsletter email parser | Ingest paid newsletters (e.g., SemiAnalysis) via email forwarding | Requires: Postmark inbound email webhook, parser |
| Content metrics reporting | Top sections, top stories, reading depth proxy | Requires: click tracking, database, reporting UI |
| No-click streak alerting | Alert if an audience member has >5 consecutive no-click briefings | Requires: email metrics storage, alerting system |
| A/B section ordering | Test different section orders per audience to optimize CTR | Requires: experiment framework, metrics |
| Section diversity enforcement | Automated check preventing single section from >40% of bundle | Can be built now as a scoring constraint |

### P2 Features (Target: 60-90 Days Post-Launch)

| Feature | Description | Dependencies |
|---|---|---|
| Optimal send-time per audience | Correlate open times to find ideal delivery window | Requires: 30+ days of open-time data |
| SemiAnalysis integration | Paid source ingestion and ROI evaluation | Requires: newsletter parser (P1) |
| LinkedIn post monitoring | C-suite executive signal tracking | Requires: LinkedIn API access |
| Audience profile self-service | Executives adjust own topic preferences via web UI | Requires: web UI, profile storage in database |
| Briefing web archive search | Search past briefings by topic, company, date | Requires: full-text index over archive |
| Multiple audience support | Add executives beyond initial four | Requires: schema validation, scalable pipeline |
| Learned topic affinity model | ML-derived weights from click history | Requires: 60+ days click data, ML pipeline |
| Multi-language source support | Ingest non-English sources | Requires: translation/multilingual NLP |
| Executive Summary audio version | TTS audio briefing as email attachment | Requires: TTS API integration |
| Source reliability tracking | Track prediction accuracy of sources over time | Requires: outcome tracking, long-term storage |

---

## 5. Recommended Implementation Order for Remaining P0 Work

Based on dependency chains and risk reduction:

1. **Persistent storage** (PostgreSQL/SQLite) -- unblocks dedup, suppression log, feedback, metrics
2. **Audience profile schema completion** -- unblocks proper personalization scoring
3. **Profile schema validation** -- catches config errors early
4. **Scoring engine completion** (7 dimensions, 0-10 normalization) -- unblocks correct article ranking
5. **Confidence tag vocabulary change** -- aligns classification output with PRD
6. **5-step deduplication pipeline** -- requires storage + embeddings; highest editorial risk
7. **OCI Implications standalone section** -- high-value differentiation
8. **Editorial rules enforcement** -- validation gate before render
9. **Suppression log** -- required for auditing and calibration
10. **Email delivery via Postmark** -- required for actual executive delivery
11. **Tracked links** -- required for any engagement measurement
12. **Basic feedback controls** -- minimum viable inline feedback
13. **Email metrics** -- open/click/CTR tracking
14. **Daily cron schedule** -- operational automation

---

*Analysis performed against PRD v1.0 and codebase at commit 1a627b7.*
