"""
client.py — Claude LLM integration via subprocess.

Migrated from briefing/llm.py with DB logging integration.
Uses `claude -p` via subprocess with CLAUDECODE env var unset.
"""

import hashlib
import json
import logging
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import (
    CACHE_DIR, HAIKU_MODEL, SONNET_MODEL,
    LLM_MAX_RETRIES, LLM_RETRY_BACKOFF,
)
from app.db.models import ProcessingLog, Article, get_session, init_db

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core subprocess wrapper
# ---------------------------------------------------------------------------

def call_claude(prompt: str, model: str = SONNET_MODEL, timeout: int = 120) -> str:
    """
    Invoke `claude -p` as a subprocess with CLAUDECODE unset.
    Raises RuntimeError on non-zero exit after retries.
    """
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    for attempt in range(1, LLM_MAX_RETRIES + 1):
        try:
            result = subprocess.run(
                ["claude", "-p", "--model", model, "--output-format", "text"],
                input=prompt,
                capture_output=True,
                text=True,
                env=env,
                timeout=timeout,
            )
            if result.returncode == 0:
                return result.stdout.strip()

            logger.warning(
                "Claude attempt %d/%d failed (rc=%d): %s",
                attempt, LLM_MAX_RETRIES, result.returncode, result.stderr[:200]
            )
        except subprocess.TimeoutExpired:
            logger.warning("Claude attempt %d/%d timed out", attempt, LLM_MAX_RETRIES)
        except Exception as exc:
            logger.warning("Claude attempt %d/%d error: %s", attempt, LLM_MAX_RETRIES, exc)

        if attempt < LLM_MAX_RETRIES:
            time.sleep(LLM_RETRY_BACKOFF * attempt)

    raise RuntimeError(f"Claude failed after {LLM_MAX_RETRIES} attempts")


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:24]


def _cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{key}.json"


def _cache_get(key: str) -> Any | None:
    path = _cache_path(key)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            pass
    return None


def _cache_set(key: str, value: Any) -> None:
    _cache_path(key).write_text(json.dumps(value, indent=2, default=str))


def _strip_code_fences(raw: str) -> str:
    """Remove markdown code fences if present."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    return raw


# ---------------------------------------------------------------------------
# Article classification (Haiku)
# ---------------------------------------------------------------------------

def classify_article(article: dict) -> dict:
    """
    Classify an article's topics, entities, section, and confidence
    using claude-haiku-4-5. Returns cached result if available.
    """
    cache_key = _cache_key(f"classify:{article['url']}")
    cached = _cache_get(cache_key)
    if cached:
        return cached

    prompt = f"""You are an editorial classifier for an OCI executive technology briefing.

Classify this article and respond ONLY with valid JSON (no markdown, no code fences).

Article title: {article['title']}
Source: {article['source']}
Summary: {article.get('summary', '')[:800]}

Allowed sections: financial, compete, ai, datacenter, power, deals, security, multicloud, oss, partnerships, community, infrastructure

Return this exact JSON structure:
{{
  "topics": ["topic1", "topic2"],
  "entities": ["entity1", "entity2"],
  "sections": ["primary_section", "optional_secondary"],
  "section": "primary_section",
  "confidence": "one of: high, medium, low"
}}

Rules:
- topics: 2-4 short topic tags (e.g. "GPU supply chain", "cloud capex", "model release")
- entities: company names, people, products mentioned (max 5)
- sections: 1-3 sections this article belongs to, ordered by relevance. All must be from the allowed list.
- section: the single PRIMARY section (same as first entry of sections)
- confidence: high if clearly relevant to cloud/AI/tech enterprise, medium if tangential, low if unclear
- Be generous with multi-section assignment: AWS earnings → ["financial","compete"]; datacenter power deal → ["datacenter","power","deals"]"""

    try:
        raw = call_claude(prompt, model=HAIKU_MODEL, timeout=60)
        raw = _strip_code_fences(raw)
        result = json.loads(raw)
    except (json.JSONDecodeError, RuntimeError) as exc:
        logger.warning("classify_article failed for %s: %s", article["url"][:60], exc)
        result = {
            "topics": [],
            "entities": [],
            "section": article["sections"][0] if article.get("sections") else "compete",
            "confidence": "low",
        }

    _cache_set(cache_key, result)

    # Log to processing_log
    _log_processing(article, "classify", {}, result)

    return result


# ---------------------------------------------------------------------------
# Per-article summary (Sonnet)
# ---------------------------------------------------------------------------

def generate_summary(article: dict, audience_profile: dict) -> dict:
    """
    Generate a personalised headline, summary, and OCI implication
    for one article using claude-sonnet-4-6.
    """
    cache_key = _cache_key(f"summary:{article['url']}:{audience_profile['id']}")
    cached = _cache_get(cache_key)
    if cached:
        return cached

    pub_str = (
        article['published_at'].strftime('%Y-%m-%d %H:%M UTC')
        if hasattr(article['published_at'], 'strftime')
        else str(article['published_at'])
    )

    prompt = f"""You are the editorial AI for an executive intelligence briefing delivered to OCI senior leadership.

Your audience: {audience_profile['name']}, {audience_profile['title']}
Tone: {audience_profile['tone_guidance']}

Write a personalised briefing item. Respond ONLY with valid JSON (no markdown, no code fences).

Article title: {article['title']}
Source: {article['source']} (published: {pub_str})
Summary: {article.get('summary', '')[:1200]}

Return this exact JSON structure:
{{
  "headline": "A rewritten, punchy 10-15 word headline optimised for this executive",
  "summary": "2-3 sentences. Lead with the most important fact. Add context. End with strategic implication.",
  "oci_implication": "1-2 sentences on what this means for OCI's strategy or operations."
}}"""

    try:
        raw = call_claude(prompt, model=SONNET_MODEL, timeout=90)
        raw = _strip_code_fences(raw)
        result = json.loads(raw)
    except (json.JSONDecodeError, RuntimeError) as exc:
        logger.warning("generate_summary failed for %s (%s): %s",
                       article["url"][:60], audience_profile["id"], exc)
        result = {
            "headline": article["title"],
            "summary": article.get("summary", "")[:300],
            "oci_implication": "Assess impact on OCI strategy.",
        }

    _cache_set(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# Executive summary (Sonnet)
# ---------------------------------------------------------------------------

def generate_executive_summary(top_articles: list[dict], audience_profile: dict) -> dict:
    """
    Generate a 3-5 bullet executive summary and OCI Implication of the Day.
    """
    cache_key = _cache_key(
        f"exec_summary:{audience_profile['id']}:"
        + ":".join(a["url"] for a in top_articles[:12])
    )
    cached = _cache_get(cache_key)
    if cached:
        return cached

    articles_text = "\n\n".join(
        f"[{i+1}] {a['title']} ({a['source']})\n{a.get('summary', '')[:400]}"
        for i, a in enumerate(top_articles[:12])
    )

    prompt = f"""You are the chief editorial AI for an executive intelligence briefing for OCI senior leadership.

Your audience: {audience_profile['name']}, {audience_profile['title']}
Tone: {audience_profile['tone_guidance']}

Based on today's top stories, write an executive briefing summary. Respond ONLY with valid JSON (no markdown, no code fences).

TOP STORIES:
{articles_text}

Return this exact JSON structure:
{{
  "bullets": [
    "Bullet 1: the single most important development today",
    "Bullet 2: second key development",
    "Bullet 3: third key development"
  ],
  "oci_implication_of_day": "2-3 sentences. The single most important strategic implication for OCI leadership today."
}}

Rules:
- 3-5 bullets only
- Each bullet must be a complete, standalone insight
- The OCI implication must be concrete and actionable"""

    try:
        raw = call_claude(prompt, model=SONNET_MODEL, timeout=120)
        raw = _strip_code_fences(raw)
        result = json.loads(raw)
        if not isinstance(result.get("bullets"), list):
            result["bullets"] = [str(result.get("bullets", ""))]
    except (json.JSONDecodeError, RuntimeError) as exc:
        logger.warning("generate_executive_summary failed for %s: %s",
                       audience_profile["id"], exc)
        result = {
            "bullets": [
                "Multiple significant developments across cloud, AI, and infrastructure today.",
                "Competitive landscape continues to shift — see individual stories for detail.",
            ],
            "oci_implication_of_day": "Review top stories for strategic implications relevant to OCI.",
        }

    _cache_set(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# Processing log helper
# ---------------------------------------------------------------------------

def _log_processing(article: dict, stage: str, input_snap: dict, output_snap: dict) -> None:
    """Log a processing step to the database."""
    try:
        engine = init_db()
        session = get_session(engine)
        db_art = session.query(Article).filter_by(url=article["url"]).first()
        if db_art:
            log = ProcessingLog(
                article_id=db_art.id,
                stage=stage,
                input_snapshot=input_snap,
                output_snapshot=output_snap,
                score_breakdown={},
                created_at=datetime.now(timezone.utc),
            )
            session.add(log)
            session.commit()
        session.close()
    except Exception as exc:
        logger.debug("Failed to log processing: %s", exc)
