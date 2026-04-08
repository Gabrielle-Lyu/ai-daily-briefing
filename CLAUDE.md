# AI Daily Briefing — Claude Instructions

## Dev Team Orchestrator

The dev team lives at `/home/ubuntu/dev-team/team.py`.
Invoke it with: `env -u CLAUDECODE python3 /home/ubuntu/dev-team/team.py --cwd /home/ubuntu/projects/ai-daily-briefing "TASK"`

**Automatically use the orchestrator (without waiting to be asked) for:**
- Any UI/UX design or layout changes → spawn designer + reader/critic agents to agree first, then frontend to implement
- New features or significant architecture changes → run the full PM → architect → backend/frontend cycle
- Code review requests → spawn architect + backend/frontend + QA agents
- Bug fixes that touch multiple files → use backend or frontend agent

**Do NOT use the orchestrator for:**
- Small CSS tweaks or wording changes — just edit directly
- Reading files or answering questions
- Running the pipeline (`python3 main.py`)

## Pipeline (9 steps)

```
[1] Fetch              — 31 RSS feeds (Tier 1-4) via feedparser + Trafilatura full-text extraction
[2] Pre-score          — source credibility + timeliness (lightweight, for dedup tie-breaking)
[3] In-Run Dedup       — Jaccard word overlap within same batch (app/dedup/pipeline.py)
[4] Cross-Day Dedup    — nomic-embed-text-v1.5 embeddings (256d Matryoshka) vs 7-day cluster history in SQLite
                         fact-delta scoring (6 signals) to distinguish updates from repeats
[5] Classify           — Claude Haiku via subprocess for topic/entity/section tagging
[6] Full Audience Score — per-executive relevance scoring informed by classification
[7] Summarize          — Claude Sonnet via subprocess for per-audience summaries (top 12/audience)
[8] Executive Summaries — Claude Sonnet synthesizes top stories per audience
[9] Render + Deliver   — HTML briefings to output/YYYY-MM-DD/
```

## Tech Stack

- **Embeddings**: nomic-embed-text-v1.5 (768d → 256d Matryoshka, 8K context, local CPU)
- **NER**: SpaCy en_core_web_sm (replaces regex for entity extraction)
- **Full text**: Trafilatura + httpx (browser headers) for article body extraction
- **LLM**: Claude Haiku (classify) + Sonnet (summarize) via `claude -p` subprocess
- **Database**: SQLite (output/briefing.db) — articles, story_clusters, suppression_log, etc.
- **Admin**: FastAPI API (port 8002) + dark-themed admin dashboard (web/admin.html)
- **Visualization**: Plotly.js 3D scatter plot with UMAP + HDBSCAN clustering
- **Server**: nginx reverse proxy → ainews.oci-incubations.com

## Project Structure

```
briefing/
  config.py     — 31 RSS sources, 4 audience profiles, scoring weights
  ingest.py     — RSS fetching + Trafilatura full-text extraction
  score.py      — 4-dimension scoring (credibility, timeliness, relevance, keywords)
  process.py    — legacy in-run dedup (still exists, not called by main.py)
  llm.py        — Claude subprocess calls (classify, summarize, exec summary)
  render.py     — HTML/CSS generation (pure Python string templates)
app/
  dedup/
    pipeline.py     — 5-stage in-run dedup (normalize, cluster, compare, followup, suppress)
    cross_day.py    — 7-day cluster lookup, suppress/followup/new decisions, cluster persistence
    embeddings.py   — nomic-embed-text-v1.5 model loading + batch encoding (256d)
    fingerprint.py  — SpaCy NER + regex fact extraction + 6-signal fact-delta scoring
  db/
    models.py       — SQLAlchemy ORM (Article, StoryCluster, SuppressionLog, etc.)
  api/
    routes.py       — FastAPI admin endpoints (articles, clusters, rankings, 3D viz, dedup stats)
web/
  admin.html        — admin dashboard (Articles, Sources, Clusters, Dedup Stats, Rankings, Clusters 3D)
config/
  settings.py       — DATABASE_URL, paths, LLM model names
main.py             — 9-step pipeline orchestrator
serve.py            — local HTTP server for briefing output
scripts/
  daily_run.sh      — cron wrapper
output/
  YYYY-MM-DD/       — generated HTML briefings
  briefing.db       — SQLite database
  .cache/           — LLM result cache (JSON files)
```

## Running

```bash
python3 main.py --dry-run           # fast test, no LLM
python3 main.py                     # full run with Claude
python3 main.py --audience karan    # single audience
python3 serve.py --no-browser       # briefing server on :8000
```

## Deployment

- **Systemd services**: `ai-briefing` (port 8000), `ai-briefing-admin` (port 8002)
- **Nginx**: reverse proxy at ainews.oci-incubations.com
- **Cron**: daily at 5:00 AM UTC (`scripts/daily_run.sh`)
- **Restart**: `sudo systemctl restart ai-briefing ai-briefing-admin`

## 4 Audiences

| ID | Name | Title | Focus |
|---|---|---|---|
| karan | Karan Batta | SVP Product | Financial signals, competitive positioning, capex |
| nathan | Nathan Thomas | SVP Product | Multi-cloud ecosystem, partnerships, deals |
| greg | Greg Pavlik | EVP Data & AI | Technical competitive moves, AI infrastructure |
| mahesh | Mahesh Thiagarajan | EVP Security | Power/datacenter, security, developer platform |

## Key Conventions

- LLM calls use `claude -p` subprocess with `CLAUDECODE` unset (handled in `llm.py`)
- Embeddings are 256d (Matryoshka truncation from 768d) stored as JSON in SQLite
- Cross-day dedup thresholds: cosine ≥ 0.75 + fact-delta < 0.20 → suppress; fact-delta ≥ 0.30 → followup
- In-run dedup thresholds: Jaccard ≥ 0.50 for clustering, ≥ 0.65 for cross-source suppression
- After any render.py change, verify with `python3 main.py --dry-run`
