# Feedback Synthesis -- 2026-03-11 Briefing
**Sources:** Karan Batta (SVP Product), Nathan Thomas (SVP Product), Greg Pavlik (EVP Data & AI), Mahesh Thiagarajan (EVP Security & Developer Platform)

---

## (A) Content / Data Changes

### A1. Story Deduplication Is Broken
- **Priority:** P0
- **Raised by:** Nathan, Greg, Mahesh
- **Problem:** The Meta/Moltbook acquisition appears up to 5 times across sections (Greg counted 5 placements from 4 outlets). The Thinking Machines Lab / Nvidia deal appears twice in Nathan's briefing (SiliconAngle + TechCrunch). This wastes 3-4 card slots per briefing that should carry distinct stories.
- **What must change:** Implement event-level deduplication. Cluster articles covering the same underlying event. Keep the highest-scoring source in one section. Optionally show "Also covered by: [outlet, outlet]" as a one-line attribution. Reclaim freed slots for underserved sections.
- **Files to modify:**
  - Classifier/dedup logic (likely in `briefing/classifier.py` or `briefing/pipeline.py` -- wherever article clustering happens)
  - If dedup is done at the LLM classification step, the prompt must instruct the model to detect same-event overlap

### A2. Section Classification Ignores Audience-Specific Taxonomy
- **Priority:** P0
- **Raised by:** Karan, Nathan, Greg, Mahesh (all four)
- **Problem:** The pipeline classifies stories into a generic set of sections (AI, Deals & Partnerships, Financial & Markets, Security & Compliance) regardless of the audience profile's `section_weights` keys. This causes: Karan gets no "compete" or "datacenter" section. Nathan gets no "multicloud" section. Greg gets no "oss", "partnerships", or "community" sections. Mahesh gets no "security" or "power" section. Stories that belong in these audience-specific sections are either dropped or misrouted into generic buckets.
- **What must change:** The classification step must use the audience profile's `section_weights` keys as the target taxonomy. Each audience's stories should be classified against that audience's section list, not a shared generic list. If no stories qualify for a weighted section, render a one-line notice ("No stories met threshold for [section]") rather than silently omitting the section.
- **Files to modify:**
  - `briefing/classifier.py` or equivalent -- classification prompt must accept per-audience section list
  - `briefing/pipeline.py` -- must pass audience section_weights keys to classifier
  - `briefing/renderer.py` or template files -- must handle empty-section placeholder rendering

### A3. Story Count Per Section Does Not Reflect Weights
- **Priority:** P1
- **Raised by:** Karan, Nathan, Greg, Mahesh (all four)
- **Problem:** Sections weighted at 0.25-0.35 get 0-1 stories while sections weighted at 0.10-0.15 get 4-5 stories. Examples: Karan's "compete" at 0.25 gets 0 stories, "deals" at 0.10 gets 4. Mahesh's "datacenter" at 0.25 gets 1 story, "ai" at 0.20 gets 5.
- **What must change:** Story allocation per section should be roughly proportional to section weight. For a 12-story briefing with weights [0.35, 0.25, 0.15, 0.15, 0.10], target allocation is approximately [4, 3, 2, 2, 1]. If insufficient stories exist for a high-weight section, either: (a) lower the threshold to surface more candidates, or (b) deepen the top story with additional data points instead of leaving the section thin.
- **Files to modify:**
  - `briefing/pipeline.py` -- story selection/allocation logic
  - `briefing/config.py` -- consider adding `TOP_ARTICLES_PER_AUDIENCE` as a per-audience setting or adding min-per-section logic

### A4. Source Diversity Is Inadequate
- **Priority:** P1
- **Raised by:** Karan, Greg (partial)
- **Problem:** Karan's briefing sourced every story from SiliconAngle. A single-source briefing undermines credibility as an intelligence product. Greg noted adequate diversity (5 outlets) but this appears inconsistent across audiences.
- **What must change:** (a) Add RSS feeds for Reuters, Bloomberg, The Information, Stratechery, analyst note aggregators, VentureBeat, and energy-sector sources (Utility Dive, S&P Global Platts, EIA). (b) Add a source-diversity constraint: no more than 40% of stories from any single outlet. (c) If only one source is publishing on a topic, flag it explicitly in the briefing.
- **Files to modify:**
  - `briefing/config.py` -- `RSS_SOURCES` list (add feeds)
  - `briefing/pipeline.py` -- add source diversity constraint to selection logic

### A5. Missing RSS Sources for Key Sections
- **Priority:** P1
- **Raised by:** Greg, Mahesh
- **Problem:** Several audience-critical sections have no dedicated RSS sources: Open source (Greg needs HuggingFace trending, GitHub activity, model release trackers). Power & Energy (Mahesh needs EIA, Utility Dive, S&P Global Platts). Security (Mahesh needs threat intel feeds, NIST, vendor security blogs). Regulatory/Compliance (Mahesh needs Federal Register, EUR-Lex, FedRAMP updates).
- **What must change:** Expand the RSS source list to cover these domains. Consider adding non-RSS ingestion for HuggingFace trending models and GitHub activity signals.
- **Files to modify:**
  - `briefing/config.py` -- `RSS_SOURCES` list
  - Possibly new ingestion adapters for HuggingFace API and GitHub trending

### A6. Relevance Filtering Is Too Loose
- **Priority:** P2
- **Raised by:** Karan
- **Problem:** Stories like Anchr ($5.8M seed, food supply chain) and Meta deepfake moderation are not relevant at SVP Product altitude. Seed-stage startups in unrelated verticals and content-policy stories with tenuous OCI angles are noise.
- **What must change:** Add a relevance floor: exclude sub-$50M deals and seed rounds unless directly OCI-relevant. Require a minimum OCI-relevance score before a story enters any briefing. Karan specifically requests 8-10 stories max, not 12.
- **Files to modify:**
  - `briefing/config.py` -- `TOP_ARTICLES_PER_AUDIENCE` (make per-audience or lower default)
  - `briefing/scorer.py` or equivalent -- add relevance floor logic
  - Classification prompt -- instruct model to flag low-relevance stories

### A7. Financial Section Needs Enrichment on Earnings Days
- **Priority:** P2
- **Raised by:** Karan
- **Problem:** On Oracle's earnings day, the Financial section had only 2 stories. Missing: analyst upgrades/target changes, after-hours price action, peer comps (AWS/Azure growth rates), RPO/backlog data, margin commentary.
- **What must change:** When an Oracle earnings story is detected, the system should attempt to enrich it with supplementary data points (analyst reactions, peer context). Consider adding financial data API integration or analyst note sources.
- **Files to modify:**
  - `briefing/pipeline.py` -- earnings enrichment logic
  - `briefing/config.py` -- add financial data sources

---

## (B) Layout / UX Changes

### B1. Placeholder Images Undermine Credibility
- **Priority:** P1
- **Raised by:** Karan
- **Problem:** Hero card images use picsum.photos placeholder stock photos. Random photos add no information and make the product look unfinished.
- **What must change:** Either pull real article thumbnail images (from og:image meta tags in source articles) or remove images entirely. No placeholders.
- **Files to modify:**
  - `briefing/renderer.py` or HTML template files
  - Ingestion pipeline -- extract og:image from article URLs

### B2. Nav Bar Is Empty on Load (Client-Side JS Dependency)
- **Priority:** P1
- **Raised by:** Karan
- **Problem:** Section navigation links are injected via JavaScript from a data attribute. If JS fails or loads slowly, the nav bar is empty.
- **What must change:** Server-render the nav links directly into the HTML. Remove the JS dependency for navigation.
- **Files to modify:**
  - HTML template file (likely in `web/` or `briefing/templates/`)
  - `briefing/renderer.py` -- generate nav links at render time

### B3. CSS Line-Clamp Hides Generated Summary Text
- **Priority:** P2
- **Raised by:** Karan
- **Problem:** Story card summaries are generated as 3-4 sentences, but CSS `line-clamp` truncates them to ~1 visible line. The system generates text the user never sees.
- **What must change:** Either: (a) generate shorter summaries (1-2 sentences for non-hero cards), or (b) expand the visible area to show the full summary. Option (a) is preferred -- it also reduces LLM token cost.
- **Files to modify:**
  - LLM summary generation prompt -- instruct 1-2 sentence max for non-hero cards
  - Alternatively, CSS in template files to expand visible area

### B4. Executive Summary Bullets Are Too Long
- **Priority:** P2
- **Raised by:** Karan
- **Problem:** Each exec summary bullet is 2-3 sentences. At 5am scan speed, this is too dense. Target: 1 sentence, max 20 words per bullet.
- **What must change:** Update the exec summary generation prompt to enforce single-sentence bullets with a word limit.
- **Files to modify:**
  - LLM prompt for executive summary generation
  - Possibly `briefing/renderer.py` if there is a post-processing step

### B5. OCI Implication of the Day Is a Wall of Text
- **Priority:** P2
- **Raised by:** Karan
- **Problem:** The right-panel OCI Implication block is ~100 words with no line breaks, covering 3-4 topics in one paragraph.
- **What must change:** Restructure as 3 bullet points max, or cut to the single most important implication. Break into scannable format.
- **Files to modify:**
  - LLM prompt for OCI Implication generation
  - HTML template -- ensure bullet-list rendering support in the implication panel

---

## (C) Per-Audience Tuning

### C1. Karan -- Tone: Shorten Everything, Cut Jargon
- **Priority:** P1
- **Raised by:** Karan
- **Problem:** Writing is too verbose for a 5am scan. Takes 4 minutes instead of target 90 seconds. Specific jargon to cut: "bear thesis," "winner-take-most dynamic," "beachhead," "sentiment shift in the analytics software space where profitability discipline now commands a premium."
- **What must change:** Update `tone_guidance` to be more explicit about brevity constraints. Add: "Maximum 20 words per executive summary bullet. One sentence per non-hero story summary. Replace financial jargon with plain language. Target total read time under 90 seconds."
- **Files to modify:**
  - `config/audiences.py` and `briefing/config.py` -- update Karan's `tone_guidance`

### C2. Karan -- Remove Security Section, Reclassify to Compete
- **Priority:** P1
- **Raised by:** Karan
- **Problem:** Security is not in Karan's weight map but appears as a section. The AWS Security Hub story belongs in "compete" for Karan's briefing.
- **What must change:** Covered by A2 above (section taxonomy must match profile weights). No config change needed -- Karan's weights already exclude security. The classifier must respect this.
- **Files to modify:**
  - Classifier logic (see A2)

### C3. Nathan -- Shift OCI Language from Observational to Action-Oriented
- **Priority:** P2
- **Raised by:** Nathan
- **Problem:** Summaries use passive framing ("For OCI, this validates...") instead of action-oriented framing ("This creates an opening for OCI to..." or "OCI product should evaluate...").
- **What must change:** Update `tone_guidance` to add: "Use action-oriented framing for OCI implications. Lead with what OCI should do, not what the news validates. Example: 'OCI should evaluate...' not 'For OCI, this validates...'"
- **Files to modify:**
  - `config/audiences.py` and `briefing/config.py` -- update Nathan's `tone_guidance`

### C4. Nathan -- Name Specific ISVs, GSIs, and Portfolio Companies
- **Priority:** P2
- **Raised by:** Nathan
- **Problem:** Story summaries reference ISV/GSI opportunities generically ("peers like it," "a potential partner worth tracking") without naming specific companies. Nathan needs actionable names his team can follow up on.
- **What must change:** Update `tone_guidance` to add: "When referencing ISV, GSI, or partner opportunities, name at least 1-2 specific companies. Avoid vague references like 'peers' or 'potential partners.'"
- **Files to modify:**
  - `config/audiences.py` and `briefing/config.py` -- update Nathan's `tone_guidance`
  - LLM summary prompt -- add instruction to include named entities for partner signals

### C5. Greg -- Shift Tone from Business-Strategic to Technical-First
- **Priority:** P1
- **Raised by:** Greg
- **Problem:** Briefing reads like a strategic business briefing, not a technical executive briefing. No parameter counts, benchmark scores, latency figures, tokens-per-second metrics, or pricing data anywhere. Uses MBA language ("escape velocity," "commands premium multiples," "weaponizing data gravity").
- **What must change:** Update `tone_guidance` to add: "Lead every AI story with what was built and how (architecture, model size, benchmark scores, inference metrics), then derive strategic implications. Include specific numbers: parameter counts, tokens/sec, latency, pricing. Never use MBA jargon -- replace with technical specifics. Example: instead of 'escape velocity' say '30 tokens/sec on-device inference at 7B parameters.'"
- **Files to modify:**
  - `config/audiences.py` and `briefing/config.py` -- update Greg's `tone_guidance`

### C6. Greg -- Expand Competitive Intel Depth
- **Priority:** P1
- **Raised by:** Greg
- **Problem:** Compete is weighted 0.35 but delivered only 1 story. Greg needs hyperscaler AI service launches, pricing moves, benchmark comparisons, and database/data platform competition (Snowflake Cortex, Databricks DBRX, MongoDB Atlas Vector Search).
- **What must change:** Covered by A2 and A3 (section taxonomy and allocation). Additionally, expand RSS sources with data platform vendor blogs (Snowflake, Databricks, MongoDB engineering blogs).
- **Files to modify:**
  - `briefing/config.py` -- add data platform RSS sources
  - Classifier and allocation logic (see A2, A3)

### C7. Mahesh -- Add Regulatory/Compliance Tracking
- **Priority:** P2
- **Raised by:** Mahesh
- **Problem:** Zero regulatory content despite tone guidance explicitly saying "Note regulatory, compliance, and supply-chain risks." No EU AI Act, FedRAMP, DISA IL, data residency, or export control coverage.
- **What must change:** Consider adding a "regulatory" key to Mahesh's section_weights (reduce another weight slightly to maintain sum of 1.0). Add regulatory-focused RSS sources. Alternatively, treat regulatory as a tag that surfaces within existing sections.
- **Files to modify:**
  - `config/audiences.py` and `briefing/config.py` -- consider adding regulatory weight or updating tone_guidance
  - `briefing/config.py` -- add regulatory RSS sources (Federal Register, EUR-Lex, NIST)

---

## Priority Summary

| Priority | Count | Items |
|----------|-------|-------|
| P0 | 2 | A1 (dedup broken), A2 (section taxonomy ignores audience profiles) |
| P1 | 8 | A3 (allocation vs. weights), A4 (source diversity), A5 (missing RSS sources), B1 (placeholder images), B2 (nav bar JS), C1 (Karan verbosity), C5 (Greg technical tone), C6 (Greg compete depth) |
| P2 | 7 | A6 (relevance filtering), A7 (earnings enrichment), B3 (line-clamp waste), B4 (exec summary length), B5 (OCI implication wall of text), C3 (Nathan action-oriented tone), C4 (Nathan named partners), C7 (Mahesh regulatory) |

## Cross-Cutting Themes

1. **The classifier is the root cause of most P0/P1 issues.** It uses a generic section taxonomy instead of per-audience section keys. Fixing A2 will cascade improvements to all four audiences.
2. **Deduplication is the second systemic issue.** All four executives reported duplicate stories. Event-level clustering must happen before section assignment.
3. **Tone guidance in config is not being enforced strongly enough by the LLM prompts.** The guidance strings exist but the generation output does not reflect them (Greg gets business framing, Karan gets verbose text). The prompts need tighter constraints and examples.
4. **The RSS source list has major gaps** for open-source, power/energy, security, and regulatory coverage. This structurally prevents the system from populating those sections regardless of classifier quality.

---

*Synthesized: 2026-03-11*
