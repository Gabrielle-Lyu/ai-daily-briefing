"""
routes.py — FastAPI admin API endpoints.

Endpoints:
  GET /admin/articles          — Paginated articles list
  GET /admin/sources           — All sources
  GET /admin/processing-log    — Processing log entries
  GET /admin/suppression-log   — Suppression log entries
  POST /run-pipeline           — Trigger pipeline run
  GET /briefings/{date}        — Get briefing for a date
  GET /health                  — Health check
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse

from app.db.models import (
    Article, Source, ProcessingLog, SuppressionLog,
    AudienceBriefing, StoryCluster,
    get_engine, get_session, init_db,
)
from config.settings import OUTPUT_ROOT

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Daily Briefing Admin API",
    version="1.0.0",
    description="Admin API for the AI Daily Executive Briefing system",
)

# CORS for admin dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health_check():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------------------
# Admin: Articles
# ---------------------------------------------------------------------------

@app.get("/admin/articles")
def get_articles(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    tier: Optional[int] = None,
    source: Optional[str] = None,
):
    """List articles with pagination and optional filtering."""
    try:
        engine = init_db()
        session = get_session(engine)

        query = session.query(Article).order_by(Article.ingest_at.desc())

        if tier is not None:
            query = query.filter(Article.tier == tier)
        if source is not None:
            query = query.filter(Article.source_id == source)

        total = query.count()
        articles = query.offset((page - 1) * per_page).limit(per_page).all()

        result = {
            "total": total,
            "page": page,
            "per_page": per_page,
            "articles": [
                {
                    "id": a.id,
                    "title": a.title,
                    "url": a.url,
                    "source_id": a.source_id,
                    "tier": a.tier,
                    "raw_score": a.raw_score,
                    "published_at": a.published_at.isoformat() if a.published_at else None,
                    "ingest_at": a.ingest_at.isoformat() if a.ingest_at else None,
                    "summary": (a.summary or "")[:200],
                }
                for a in articles
            ],
        }
        session.close()
        return result
    except Exception as exc:
        logger.error("Error fetching articles: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Admin: Sources
# ---------------------------------------------------------------------------

@app.get("/admin/sources")
def get_sources():
    """List all configured sources."""
    try:
        engine = init_db()
        session = get_session(engine)

        sources = session.query(Source).order_by(Source.tier, Source.display_name).all()

        result = {
            "total": len(sources),
            "sources": [
                {
                    "id": s.id,
                    "domain": s.domain,
                    "display_name": s.display_name,
                    "tier": s.tier,
                    "credibility_score": s.credibility_score,
                    "rss_url": s.rss_url,
                    "crawl_freq_mins": s.crawl_freq_mins,
                    "active": s.active,
                }
                for s in sources
            ],
        }
        session.close()
        return result
    except Exception as exc:
        logger.error("Error fetching sources: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Admin: Processing Log
# ---------------------------------------------------------------------------

@app.get("/admin/processing-log")
def get_processing_log(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    stage: Optional[str] = None,
):
    """List processing log entries."""
    try:
        engine = init_db()
        session = get_session(engine)

        query = session.query(ProcessingLog).order_by(ProcessingLog.created_at.desc())

        if stage is not None:
            query = query.filter(ProcessingLog.stage == stage)

        total = query.count()
        logs = query.offset((page - 1) * per_page).limit(per_page).all()

        result = {
            "total": total,
            "page": page,
            "per_page": per_page,
            "logs": [
                {
                    "id": log.id,
                    "article_id": log.article_id,
                    "stage": log.stage,
                    "input_snapshot": log.input_snapshot,
                    "output_snapshot": log.output_snapshot,
                    "score_breakdown": log.score_breakdown,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                }
                for log in logs
            ],
        }
        session.close()
        return result
    except Exception as exc:
        logger.error("Error fetching processing log: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Admin: Suppression Log
# ---------------------------------------------------------------------------

@app.get("/admin/suppression-log")
def get_suppression_log(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """List suppression log entries."""
    try:
        engine = init_db()
        session = get_session(engine)

        query = session.query(SuppressionLog).order_by(SuppressionLog.suppressed_at.desc())
        total = query.count()
        logs = query.offset((page - 1) * per_page).limit(per_page).all()

        result = {
            "total": total,
            "page": page,
            "per_page": per_page,
            "logs": [
                {
                    "id": log.id,
                    "article_id": log.article_id,
                    "reason": log.reason,
                    "similarity_score": log.similarity_score,
                    "matched_cluster_id": log.matched_cluster_id,
                    "suppressed_at": log.suppressed_at.isoformat() if log.suppressed_at else None,
                }
                for log in logs
            ],
        }
        session.close()
        return result
    except Exception as exc:
        logger.error("Error fetching suppression log: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Pipeline trigger
# ---------------------------------------------------------------------------

@app.post("/run-pipeline")
def trigger_pipeline(
    dry_run: bool = Query(False),
    audience: Optional[str] = None,
):
    """Trigger a pipeline run (returns immediately with status)."""
    return {
        "status": "accepted",
        "message": "Pipeline run queued. Use scripts/pipeline.py for synchronous execution.",
        "dry_run": dry_run,
        "audience": audience,
    }


# ---------------------------------------------------------------------------
# Briefings
# ---------------------------------------------------------------------------

@app.get("/briefings/{date}")
def get_briefing(date: str):
    """Get generated briefing files for a date."""
    briefing_dir = OUTPUT_ROOT / date
    if not briefing_dir.exists():
        raise HTTPException(status_code=404, detail=f"No briefing found for {date}")

    files = {}
    for f in briefing_dir.glob("*.html"):
        files[f.stem] = f.name

    return {
        "date": date,
        "files": files,
        "path": str(briefing_dir),
    }


# ---------------------------------------------------------------------------
# Admin dashboard
# ---------------------------------------------------------------------------

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard():
    """Serve the admin dashboard HTML."""
    admin_path = Path(__file__).parent.parent.parent / "web" / "admin.html"
    if admin_path.exists():
        return HTMLResponse(content=admin_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Admin dashboard not found</h1>", status_code=404)
