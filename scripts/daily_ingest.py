#!/usr/bin/env python3
"""
daily_ingest.py -- Lightweight daily article ingestion (no LLM calls).

Fetches RSS feeds, computes embeddings, deduplicates within the batch
using cosine similarity, and saves new articles to the SQLite database.

Intended to run daily via cron (e.g. 5 AM UTC) so that articles are
captured before RSS feeds rotate them out.

Usage:
    python3 scripts/daily_ingest.py
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure the project root is on sys.path so that package imports work
# when this script is invoked directly (e.g. python3 scripts/daily_ingest.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from briefing.ingest import ingest_feeds
from app.dedup.embeddings import compute_embeddings, batch_cosine_similarity
from app.db.models import init_db, get_session, Article

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Embedding-based dedup (same logic as app.dedup.pipeline._embedding_dedup)
# ---------------------------------------------------------------------------

COSINE_THRESHOLD = 0.80


def _embedding_dedup(articles: list[dict], embeddings: list[list[float]]) -> tuple[list[dict], list[list[float]]]:
    """
    Remove near-duplicate articles within a single batch using cosine
    similarity of their embeddings.  Keeps the article with the higher
    pre-score when two articles exceed the threshold.

    Returns the filtered (articles, embeddings) lists in the same order.
    """
    if len(articles) < 2:
        return articles, embeddings

    import numpy as np

    emb_matrix = np.array(embeddings, dtype=np.float32)
    suppressed_indices: set[int] = set()

    for i in range(len(articles)):
        if i in suppressed_indices:
            continue
        vec = emb_matrix[i]
        sims = batch_cosine_similarity(vec, emb_matrix)

        for j in range(i + 1, len(articles)):
            if j in suppressed_indices:
                continue
            if sims[j] >= COSINE_THRESHOLD:
                # Keep the article with the higher score; break ties by index
                score_i = max(articles[i].get("scores", {}).values(), default=0)
                score_j = max(articles[j].get("scores", {}).values(), default=0)
                loser = j if score_i >= score_j else i
                suppressed_indices.add(loser)
                logger.info(
                    "Embedding dedup: suppressed '%s' (cosine=%.3f with '%s')",
                    articles[loser]["title"][:50],
                    sims[j],
                    articles[i if loser == j else j]["title"][:50],
                )

    kept_articles = [a for idx, a in enumerate(articles) if idx not in suppressed_indices]
    kept_embeddings = [e for idx, e in enumerate(embeddings) if idx not in suppressed_indices]

    logger.info(
        "Embedding dedup: %d -> %d (%d suppressed)",
        len(articles), len(kept_articles), len(suppressed_indices),
    )
    return kept_articles, kept_embeddings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"=== Daily Ingest — {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} ===")

    # 1. Fetch RSS feeds
    print("\n[1/4] Fetching RSS feeds...")
    articles = ingest_feeds()
    total_fetched = len(articles)
    print(f"      Fetched {total_fetched} articles from RSS feeds")

    if not articles:
        print("No articles fetched. Feeds may be down or empty. Exiting.")
        return

    # 2. Compute embeddings for all articles
    print("\n[2/4] Computing embeddings...")
    texts = [f"{a['title']} {a.get('full_text', '') or a.get('summary', '')}" for a in articles]
    embeddings = compute_embeddings(texts)
    print(f"      Computed {len(embeddings)} embeddings")

    # 3. Embedding dedup within today's batch
    print("\n[3/4] Deduplicating within batch (cosine >= {:.2f})...".format(COSINE_THRESHOLD))
    articles, embeddings = _embedding_dedup(articles, embeddings)
    dedup_removed = total_fetched - len(articles)
    print(f"      {len(articles)} articles after dedup ({dedup_removed} duplicates removed)")

    # 4. Save to database (skip if URL already exists)
    print("\n[4/4] Saving to database...")
    engine = init_db()
    session = get_session(engine)

    saved_count = 0
    skipped_count = 0
    now = datetime.now(tz=timezone.utc)

    for article, embedding in zip(articles, embeddings):
        # Check if this URL already exists in the DB
        existing = session.query(Article).filter_by(url=article["url"]).first()
        if existing:
            skipped_count += 1
            continue

        db_article = Article(
            url=article["url"],
            title=article["title"],
            summary=article.get("summary", ""),
            full_text=article.get("full_text", ""),
            source_name=article.get("source", ""),
            tier=article.get("tier", 2),
            published_at=article.get("published_at"),
            embedding_json=embedding,
            ingest_at=now,
        )
        session.add(db_article)
        saved_count += 1

    session.commit()
    session.close()

    print(f"\nIngested {saved_count} new articles ({total_fetched} total fetched, {skipped_count + dedup_removed} skipped as duplicates)")


if __name__ == "__main__":
    main()
