"""
ingest.py — RSS feed ingestion with concurrent fetching.

Fetches all configured RSS sources concurrently using a ThreadPoolExecutor
(feedparser is sync-only), normalizes dates to UTC, strips HTML from
summaries, and returns a flat list of Article dicts filtered to the last
INGEST_WINDOW_HOURS hours.
"""

import hashlib
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from typing import Any

import feedparser
from bs4 import BeautifulSoup
from dateutil import parser as dateutil_parser

from briefing.config import RSS_SOURCES, INGEST_WINDOW_HOURS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_html(raw: str) -> str:
    """Remove HTML tags and normalise whitespace."""
    if not raw:
        return ""
    soup = BeautifulSoup(raw, "html.parser")
    text = soup.get_text(separator=" ")
    # collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_date(entry: Any) -> datetime | None:
    """
    Try multiple feedparser date fields and return a UTC-aware datetime,
    or None if parsing fails completely.
    """
    # feedparser provides parsed time tuples as `published_parsed` / `updated_parsed`
    for field in ("published_parsed", "updated_parsed", "created_parsed"):
        val = getattr(entry, field, None)
        if val is not None:
            try:
                ts = time.mktime(val)
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            except (OverflowError, ValueError, OSError):
                pass

    # Fallback: raw string fields
    for field in ("published", "updated", "created"):
        raw = getattr(entry, field, None) or entry.get(field)
        if raw:
            try:
                dt = dateutil_parser.parse(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except (ValueError, OverflowError):
                pass

    return None


def _make_article_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _fetch_feed(source: dict, cutoff: datetime) -> list[dict]:
    """
    Fetch a single RSS source and return a list of Article dicts.
    Errors are caught and logged; an empty list is returned on failure.
    """
    articles: list[dict] = []
    try:
        feed = feedparser.parse(source["url"])
        if feed.bozo and not feed.entries:
            logger.warning("Feed %s is malformed and has no entries — skipping", source["name"])
            return articles

        for entry in feed.entries:
            url = getattr(entry, "link", None) or entry.get("link", "")
            if not url:
                continue

            title = _strip_html(getattr(entry, "title", "") or entry.get("title", ""))
            if not title:
                continue

            published_at = _parse_date(entry)
            if published_at is None:
                # If we can't determine the date, use now (generous fallback)
                published_at = datetime.now(tz=timezone.utc)

            # Filter to ingest window
            if published_at < cutoff:
                continue

            # Prefer `summary` → `content` → empty
            raw_summary = (
                getattr(entry, "summary", None)
                or entry.get("summary", "")
                or (entry.content[0].value if getattr(entry, "content", None) else "")
            )
            summary = _strip_html(raw_summary)[:1500]  # cap length

            articles.append({
                "id":           _make_article_id(url),
                "title":        title,
                "url":          url,
                "summary":      summary,
                "published_at": published_at,
                "source":       source["name"],
                "tier":         source["tier"],
                "sections":     list(source["sections"]),
                # These fields are populated later by score.py / process.py / llm.py
                "topics":       [],
                "entities":     [],
                "classified_section": None,
                "confidence":   None,
                "scores":       {},
                "per_audience_summaries": {},
            })

    except Exception as exc:
        logger.warning("Failed to fetch feed %s (%s): %s", source["name"], source["url"], exc)

    return articles


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ingest_feeds(sources: list[dict] | None = None, window_hours: int = INGEST_WINDOW_HOURS) -> list[dict]:
    """
    Fetch all RSS sources concurrently and return a flat deduplicated list
    of Article dicts published within the last `window_hours` hours.
    """
    if sources is None:
        sources = RSS_SOURCES

    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=window_hours)
    logger.info("Ingesting %d sources (cutoff: %s)", len(sources), cutoff.strftime("%Y-%m-%d %H:%M UTC"))

    all_articles: list[dict] = []
    seen_urls: set[str] = set()

    with ThreadPoolExecutor(max_workers=min(len(sources), 10)) as pool:
        futures = {pool.submit(_fetch_feed, src, cutoff): src for src in sources}
        for future in as_completed(futures):
            src = futures[future]
            try:
                batch = future.result()
                for article in batch:
                    if article["url"] not in seen_urls:
                        seen_urls.add(article["url"])
                        all_articles.append(article)
                logger.info("  [%s] fetched %d articles", src["name"], len(batch))
            except Exception as exc:
                logger.warning("  [%s] unexpected error: %s", src["name"], exc)

    logger.info("Total ingested: %d unique articles", len(all_articles))
    return all_articles
