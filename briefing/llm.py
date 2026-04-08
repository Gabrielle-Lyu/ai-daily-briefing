"""
llm.py — Claude LLM integration via subprocess.

Uses `claude -p` via subprocess with CLAUDECODE env var unset to bypass
nested-session checks. Supports classify_article (Haiku) and
generate_summary / generate_executive_summary (Sonnet).

Results are cached to output/.cache/ as JSON files keyed by content hash.
"""

import hashlib
import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CACHE_DIR = Path(__file__).parent.parent / "output" / ".cache"
HAIKU_MODEL  = "claude-haiku-4-5"
SONNET_MODEL = "claude-sonnet-4-6"
MAX_RETRIES  = 3
RETRY_BACKOFF = 2.0  # seconds


# ---------------------------------------------------------------------------
# Core subprocess wrapper
# ---------------------------------------------------------------------------

def call_claude(prompt: str, model: str = SONNET_MODEL, timeout: int = 120) -> str:
    """
    Invoke `claude -p` as a subprocess with CLAUDECODE unset.
    Raises RuntimeError on non-zero exit after MAX_RETRIES attempts.
    """
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    for attempt in range(1, MAX_RETRIES + 1):
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
                attempt, MAX_RETRIES, result.returncode, result.stderr[:200]
            )
        except subprocess.TimeoutExpired:
            logger.warning("Claude attempt %d/%d timed out", attempt, MAX_RETRIES)
        except Exception as exc:
            logger.warning("Claude attempt %d/%d error: %s", attempt, MAX_RETRIES, exc)

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_BACKOFF * attempt)

    raise RuntimeError(f"Claude failed after {MAX_RETRIES} attempts")


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


# ---------------------------------------------------------------------------
# Article classification  (Haiku)
# ---------------------------------------------------------------------------

def classify_article(article: dict) -> dict:
    """
    Classify an article's topics, entities, primary section, and confidence
    using claude-haiku-4-5.  Returns cached result if available.
    """
    cache_key = _cache_key(f"classify:{article['url']}")
    cached = _cache_get(cache_key)
    if cached:
        return cached

    prompt = f"""You are an editorial classifier for an executive technology briefing.

Classify this article and respond ONLY with valid JSON (no markdown, no code fences).

Article title: {article['title']}
Source: {article['source']}
Summary: {article.get('full_text', '')[:1500] or article.get('summary', '')[:800]}

Return this exact JSON structure:
{{
  "topics": ["topic1", "topic2"],
  "entities": ["entity1", "entity2"],
  "section": "one of: financial, compete, ai, datacenter, power, deals, security, multicloud, oss, partnerships, community, infrastructure",
  "confidence": "one of: high, medium, low"
}}

Rules:
- topics: 2-4 short topic tags (e.g. "cloud computing", "GPU shortage", "M&A")
- entities: company names, people, products mentioned (max 5)
- section: pick the SINGLE best match from the allowed list
- confidence: high if clearly relevant to cloud/AI/tech enterprise, medium if tangential, low if unclear"""

    try:
        raw = call_claude(prompt, model=HAIKU_MODEL, timeout=60)
        # Strip markdown code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        result = json.loads(raw)
    except (json.JSONDecodeError, RuntimeError) as exc:
        logger.warning("classify_article failed for %s: %s", article["url"][:60], exc)
        result = {
            "topics": [],
            "entities": [],
            "section": article["sections"][0] if article["sections"] else "compete",
            "confidence": "low",
        }

    _cache_set(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# Per-article summary  (Sonnet)
# ---------------------------------------------------------------------------

def generate_summary(article: dict, audience_profile: dict) -> dict:
    """
    Generate a personalised headline, 2-3 sentence summary, and OCI implication
    for one article using claude-sonnet-4-6.  Returns cached result if available.
    """
    cache_key = _cache_key(f"summary:{article['url']}:{audience_profile['id']}")
    cached = _cache_get(cache_key)
    if cached:
        return cached

    prompt = f"""You are the editorial AI for an executive intelligence briefing delivered to OCI (Oracle Cloud Infrastructure) senior leadership.

Your audience: {audience_profile['name']}, {audience_profile['title']}
Tone: {audience_profile['tone_guidance']}

Write a personalised briefing item for this article. Respond ONLY with valid JSON (no markdown, no code fences).

Article title: {article['title']}
Source: {article['source']} (published: {article['published_at'].strftime('%Y-%m-%d %H:%M UTC') if hasattr(article['published_at'], 'strftime') else str(article['published_at'])})
Summary: {article.get('full_text', '')[:2000] or article.get('summary', '')[:1200]}

Return this exact JSON structure:
{{
  "headline": "A rewritten, punchy 10-15 word headline optimised for this executive",
  "summary": "2-3 sentences. Lead with the most important fact. Add one layer of context. End with the strategic implication.",
  "oci_implication": "1-2 sentences specifically addressing what this means for OCI's strategy, competitive position, or operations."
}}"""

    try:
        raw = call_claude(prompt, model=SONNET_MODEL, timeout=90)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        result = json.loads(raw)
    except (json.JSONDecodeError, RuntimeError) as exc:
        logger.warning("generate_summary failed for %s (%s): %s", article["url"][:60], audience_profile["id"], exc)
        result = {
            "headline": article["title"],
            "summary": article.get("summary", "")[:300],
            "oci_implication": "Assess impact on OCI strategy.",
        }

    _cache_set(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# Executive summary  (Sonnet)
# ---------------------------------------------------------------------------

def generate_executive_summary(top_articles: list[dict], audience_profile: dict) -> dict:
    """
    Generate a 3-5 bullet executive summary and an 'OCI Implication of the Day'
    paragraph from the top articles for an audience using claude-sonnet-4-6.
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

    prompt = f"""You are the chief editorial AI for an executive intelligence briefing for OCI (Oracle Cloud Infrastructure) senior leadership.

Your audience: {audience_profile['name']}, {audience_profile['title']}
Tone: {audience_profile['tone_guidance']}

Based on today's top stories below, write an executive briefing summary. Respond ONLY with valid JSON (no markdown, no code fences).

TOP STORIES:
{articles_text}

Return this exact JSON structure:
{{
  "bullets": [
    "Bullet 1: the single most important development today and why it matters",
    "Bullet 2: second key development",
    "Bullet 3: third key development",
    "Bullet 4: fourth development (if warranted)",
    "Bullet 5: fifth development (if warranted)"
  ],
  "oci_implication_of_day": "2-3 sentences. The single most important strategic implication for OCI leadership today. Be direct and specific."
}}

Rules:
- 3-5 bullets only (remove 4th/5th if not warranted)
- Each bullet must be a complete, standalone insight (not a title — a sentence with context)
- The OCI implication must be concrete and actionable, not generic"""

    try:
        raw = call_claude(prompt, model=SONNET_MODEL, timeout=120)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        result = json.loads(raw)
        # Ensure bullets is a list
        if not isinstance(result.get("bullets"), list):
            result["bullets"] = [str(result.get("bullets", ""))]
    except (json.JSONDecodeError, RuntimeError) as exc:
        logger.warning("generate_executive_summary failed for %s: %s", audience_profile["id"], exc)
        result = {
            "bullets": [
                "Multiple significant developments across cloud, AI, and infrastructure today.",
                "Competitive landscape continues to shift — see individual stories for detail.",
            ],
            "oci_implication_of_day": "Review top stories for strategic implications relevant to OCI.",
        }

    _cache_set(cache_key, result)
    return result


