#!/usr/bin/env python3
"""
main.py — OCI AI Daily Executive Briefing Pipeline

Usage:
  python3 main.py                     # full run (with LLM)
  python3 main.py --dry-run           # skip LLM, use placeholder text
  python3 main.py --audience karan    # run for a single audience
  python3 main.py --no-cache          # force regeneration (ignore cache)
  python3 main.py --dry-run --audience greg
"""

import argparse
import asyncio
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

# ── Project imports ──────────────────────────────────────────────────────────
from briefing.config import (
    AUDIENCE_PROFILES,
    AUDIENCE_ORDER,
    MAX_ARTICLES_TO_CLASSIFY,
    MAX_CONCURRENT_LLM,
    TOP_ARTICLES_PER_AUDIENCE,
)
from briefing.ingest  import ingest_feeds
from briefing.score   import score_all_articles, get_top_articles_for_audience, get_top_articles_global
from briefing.process import normalize_articles
from briefing.render  import save_briefings

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Output root ──────────────────────────────────────────────────────────────
OUTPUT_ROOT = Path(__file__).parent / "output"


# ---------------------------------------------------------------------------
# Dry-run placeholders
# ---------------------------------------------------------------------------

DRY_RUN_CLASSIFICATION = {
    "topics":    ["cloud computing", "AI infrastructure"],
    "entities":  ["Oracle", "OCI", "NVIDIA"],
    "section":   "ai",
    "confidence": "high",
}

def _dry_run_summary(article: dict, audience_id: str) -> dict:
    return {
        "headline":        f"[DRY RUN] {article['title'][:80]}",
        "summary":         (
            f"This is a placeholder summary for '{article['title'][:60]}'. "
            "In production, Claude Sonnet generates a personalised 2-3 sentence summary "
            "tailored to this executive's role and priorities."
        ),
        "oci_implication": (
            "OCI implication placeholder: Claude Sonnet would generate a concrete, "
            "strategic implication for OCI leadership here."
        ),
    }

def _dry_run_exec_summary(top_articles: list[dict], audience_id: str) -> dict:
    profile = AUDIENCE_PROFILES[audience_id]
    headlines = [a["title"][:70] for a in top_articles[:5]]
    bullets = [f"{h}..." for h in headlines] or ["No articles available for this period."]
    return {
        "bullets": bullets,
        "oci_implication_of_day": (
            f"[DRY RUN] Executive summary for {profile['name']} ({profile['title']}). "
            "Claude Sonnet would synthesise today's top signals into a concrete strategic "
            "implication for OCI leadership — covering competitive moves, AI advancements, "
            "and infrastructure developments most relevant to this executive's priorities."
        ),
    }


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

def step_ingest() -> list[dict]:
    print("\n[1/7] Ingesting RSS feeds...")
    articles = ingest_feeds()
    print(f"      → {len(articles)} articles ingested")
    return articles


def step_score(articles: list[dict]) -> list[dict]:
    print("\n[2/7] Scoring articles across all audiences...")
    articles = score_all_articles(articles)
    print(f"      → Scored {len(articles)} articles")
    return articles


def step_normalize(articles: list[dict]) -> list[dict]:
    print("\n[3/7] Normalizing and deduplicating...")
    articles = normalize_articles(articles)
    print(f"      → {len(articles)} articles in canonical bundle")
    return articles


def step_classify(articles: list[dict], dry_run: bool, no_cache: bool) -> list[dict]:
    """Classify top-N articles with Haiku (or use placeholders in dry-run mode)."""
    print(f"\n[4/7] Classifying top {MAX_ARTICLES_TO_CLASSIFY} articles...")

    to_classify = get_top_articles_global(articles, n=MAX_ARTICLES_TO_CLASSIFY)

    if dry_run:
        for a in to_classify:
            a.update(DRY_RUN_CLASSIFICATION)
            if a.get("sections"):
                a["classified_section"] = a["sections"][0]
            else:
                a["classified_section"] = DRY_RUN_CLASSIFICATION["section"]
        print(f"      → [DRY RUN] Skipped LLM — applied placeholder classification to {len(to_classify)} articles")
        return articles

    from briefing.llm import classify_article, CACHE_DIR

    if no_cache:
        # Remove existing cache files (only classification ones)
        for f in CACHE_DIR.glob("*.json"):
            if f.name.startswith("classify_"):
                f.unlink()

    classified_count = 0
    cache_hits = 0

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_LLM) as pool:
        future_to_article = {
            pool.submit(classify_article, a): a for a in to_classify
        }
        for i, future in enumerate(as_completed(future_to_article), 1):
            article = future_to_article[future]
            try:
                result = future.result()
                article["topics"]    = result.get("topics", [])
                article["entities"]  = result.get("entities", [])
                article["classified_section"] = result.get("section") or (
                    article["sections"][0] if article["sections"] else "other"
                )
                article["confidence"] = result.get("confidence", "medium")
                classified_count += 1
                print(f"      [{i}/{len(to_classify)}] {article['source']}: {article['title'][:60]}...")
            except Exception as exc:
                logger.warning("Classification failed for %s: %s", article["url"][:50], exc)
                article["classified_section"] = article["sections"][0] if article["sections"] else "other"
                article["confidence"] = "low"

    print(f"      → Classified {classified_count} articles ({cache_hits} cache hits)")
    return articles


def step_generate_summaries(
    articles: list[dict],
    audience_ids: list[str],
    dry_run: bool,
    no_cache: bool,
) -> list[dict]:
    """Generate per-audience summaries for top articles."""
    print(f"\n[5/7] Generating article summaries (audiences: {', '.join(audience_ids)})...")

    if not dry_run:
        from briefing.llm import generate_summary, CACHE_DIR
        if no_cache:
            for f in CACHE_DIR.glob("*.json"):
                if not f.name.startswith("classify_"):
                    f.unlink()

    total_generated = 0
    total_cached = 0

    for aud_id in audience_ids:
        profile   = AUDIENCE_PROFILES[aud_id]
        top_arts  = get_top_articles_for_audience(articles, aud_id, n=TOP_ARTICLES_PER_AUDIENCE)
        print(f"\n      Audience: {profile['name']} — {len(top_arts)} articles")

        for i, article in enumerate(top_arts, 1):
            if dry_run:
                summary = _dry_run_summary(article, aud_id)
                total_generated += 1
            else:
                try:
                    summary = generate_summary(article, profile)
                    total_generated += 1
                    print(f"        [{i}/{len(top_arts)}] {article['title'][:55]}...")
                except Exception as exc:
                    logger.warning("Summary failed for %s / %s: %s", aud_id, article["url"][:40], exc)
                    summary = _dry_run_summary(article, aud_id)

            article.setdefault("per_audience_summaries", {})[aud_id] = summary

    if dry_run:
        print(f"      → [DRY RUN] Placeholder summaries for {total_generated} article×audience pairs")
    else:
        print(f"      → Generated {total_generated} summaries ({total_cached} cache hits)")
    return articles


def step_executive_summaries(
    articles: list[dict],
    audience_ids: list[str],
    dry_run: bool,
) -> dict[str, dict]:
    """Generate executive summary per audience."""
    print(f"\n[6/7] Generating executive summaries...")
    exec_summaries: dict[str, dict] = {}

    for aud_id in audience_ids:
        profile  = AUDIENCE_PROFILES[aud_id]
        top_arts = get_top_articles_for_audience(articles, aud_id, n=TOP_ARTICLES_PER_AUDIENCE)

        if dry_run:
            exec_summaries[aud_id] = _dry_run_exec_summary(top_arts, aud_id)
            print(f"      [{aud_id}] [DRY RUN] placeholder executive summary")
        else:
            from briefing.llm import generate_executive_summary
            try:
                exec_summaries[aud_id] = generate_executive_summary(top_arts, profile)
                print(f"      [{aud_id}] Executive summary generated")
            except Exception as exc:
                logger.warning("exec_summary failed for %s: %s", aud_id, exc)
                exec_summaries[aud_id] = _dry_run_exec_summary(top_arts, aud_id)

    return exec_summaries


def step_render(
    articles: list[dict],
    audience_ids: list[str],
    exec_summaries: dict[str, dict],
    output_dir: Path,
    generation_time: datetime,
) -> dict[str, Path]:
    """Render HTML files."""
    print(f"\n[7/7] Rendering HTML briefings...")

    all_audience_data: dict[str, dict] = {}
    for aud_id in audience_ids:
        top_arts = get_top_articles_for_audience(articles, aud_id, n=TOP_ARTICLES_PER_AUDIENCE)
        all_audience_data[aud_id] = {
            "articles":     top_arts,
            "exec_summary": exec_summaries.get(aud_id, {}),
            "nav_links":    "",  # populated by save_briefings
        }

    paths = save_briefings(all_audience_data, output_dir, generation_time)

    for key, path in paths.items():
        size_kb = path.stat().st_size // 1024
        print(f"      [{key}] {path}  ({size_kb} KB)")

    return paths


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="OCI AI Daily Executive Briefing Pipeline"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Skip LLM calls and use placeholder text (fast pipeline test)"
    )
    parser.add_argument(
        "--audience", metavar="AUDIENCE_ID",
        choices=list(AUDIENCE_PROFILES.keys()),
        help="Run for a single audience only (e.g. karan, nathan, greg, mahesh)"
    )
    parser.add_argument(
        "--no-cache", action="store_true",
        help="Force LLM regeneration (ignore existing cache)"
    )
    args = parser.parse_args()

    dry_run  = args.dry_run
    no_cache = args.no_cache
    audience_ids = [args.audience] if args.audience else AUDIENCE_ORDER

    generation_time = datetime.now(tz=timezone.utc)
    date_str = generation_time.strftime("%Y-%m-%d")
    output_dir = OUTPUT_ROOT / date_str

    print("=" * 60)
    print(f"  OCI AI Daily Executive Briefing — {date_str}")
    print(f"  Audiences : {', '.join(audience_ids)}")
    print(f"  Dry run   : {'YES (no LLM calls)' if dry_run else 'NO'}")
    print(f"  Output    : {output_dir}")
    print("=" * 60)

    # ── 1. Ingest ──────────────────────────────────────────────────────────
    articles = step_ingest()

    if not articles:
        print("\nWARNING: No articles ingested. Feeds may be down or all articles are older than 48h.")
        print("         Using synthetic demo articles for dry-run mode...")
        articles = _synthetic_articles(generation_time)

    # ── 2. Score ───────────────────────────────────────────────────────────
    articles = step_score(articles)

    # ── 3. Normalize ───────────────────────────────────────────────────────
    articles = step_normalize(articles)

    if not articles:
        print("ERROR: No articles after normalization. Exiting.")
        sys.exit(1)

    # ── 4. Classify ────────────────────────────────────────────────────────
    articles = step_classify(articles, dry_run=dry_run, no_cache=no_cache)

    # ── 5. Generate summaries ──────────────────────────────────────────────
    articles = step_generate_summaries(articles, audience_ids, dry_run=dry_run, no_cache=no_cache)

    # ── 6. Executive summaries ─────────────────────────────────────────────
    exec_summaries = step_executive_summaries(articles, audience_ids, dry_run=dry_run)

    # ── 7. Render ──────────────────────────────────────────────────────────
    paths = step_render(articles, audience_ids, exec_summaries, output_dir, generation_time)

    # ── Done ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  DONE")
    print(f"  Open: http://localhost:8000/{date_str}/index.html")
    print("  Run:  python3 serve.py")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Synthetic fallback articles (for when feeds are down)
# ---------------------------------------------------------------------------

def _synthetic_articles(generation_time: datetime) -> list[dict]:
    """Return a set of realistic synthetic articles for dry-run / demo mode."""
    from datetime import timedelta
    import hashlib

    def make(title, source, tier, sections, summary, hours_ago=2):
        url = f"https://example.com/{hashlib.md5(title.encode()).hexdigest()[:8]}"
        return {
            "id":           hashlib.sha256(url.encode()).hexdigest()[:16],
            "title":        title,
            "url":          url,
            "summary":      summary,
            "published_at": generation_time - timedelta(hours=hours_ago),
            "source":       source,
            "tier":         tier,
            "sections":     sections,
            "topics":       [],
            "entities":     [],
            "classified_section": sections[0] if sections else "other",
            "confidence":   "high",
            "scores":       {},
            "per_audience_summaries": {},
        }

    return [
        make(
            "NVIDIA Announces H200 Ultra GPU with 2x Training Throughput for Enterprise AI",
            "Reuters Tech", 1, ["ai", "compete", "financial"],
            "NVIDIA unveiled the H200 Ultra GPU claiming 2x training throughput over H100, "
            "targeting hyperscaler and enterprise AI workloads. The chip enters volume production "
            "in Q3 2026. AWS, Azure, and Google Cloud have all pre-ordered. OCI has not yet "
            "commented publicly on H200 Ultra availability.",
            hours_ago=3,
        ),
        make(
            "Microsoft Azure Signs $2.1B Multi-Year AI Infrastructure Deal with Saudi Aramco",
            "Reuters Business", 1, ["deals", "financial", "compete"],
            "Microsoft announced a $2.1 billion, 5-year agreement with Saudi Aramco to build "
            "AI-powered operations across the energy giant's global infrastructure. The deal "
            "includes sovereign cloud deployment in the Kingdom. OCI has an existing presence "
            "in the Gulf region and competes directly for energy-sector cloud contracts.",
            hours_ago=5,
        ),
        make(
            "OpenAI Releases GPT-5 with Native Multimodal Reasoning — Benchmarks Crush All Rivals",
            "TechCrunch", 2, ["ai", "compete"],
            "OpenAI released GPT-5, which it claims achieves state-of-the-art on 47 of 50 "
            "benchmarks including MMLU, HumanEval, and MATH. The model runs on Microsoft Azure "
            "exclusively at launch. Google DeepMind said Gemini Ultra 2 will respond next month.",
            hours_ago=1,
        ),
        make(
            "AWS Re:Invent Preview: Amazon to Announce New Graviton5 Chips and 25% Price Cuts",
            "Ars Technica", 2, ["compete", "financial", "ai"],
            "Sources close to Amazon indicate AWS will announce Graviton5 ARM-based compute chips "
            "and across-the-board price reductions averaging 25% on EC2 instances ahead of re:Invent. "
            "The move is seen as a direct response to OCI's aggressive pricing strategy.",
            hours_ago=6,
        ),
        make(
            "Google Deepens Partnership with SAP: All S/4HANA Workloads Can Run on GCP by 2027",
            "CloudWars", 2, ["compete", "deals", "multicloud"],
            "Google Cloud and SAP announced a deepened partnership under which all SAP S/4HANA "
            "workloads will be certified and optimised for Google Cloud Platform by Q4 2027. "
            "Oracle runs a significant portion of SAP competitor workloads and this deal "
            "could redirect ERP migration projects away from OCI.",
            hours_ago=8,
        ),
        make(
            "Data Center Power Crunch Worsens: Utilities Warn of 18-Month Wait for New Grid Connections",
            "Data Center Dynamics", 2, ["datacenter", "power"],
            "Multiple US utilities are imposing 12-18 month queues for new large-scale power "
            "interconnections as hyperscaler and AI lab demand outpaces grid capacity. "
            "Virginia, Texas, and Arizona are seeing the most severe bottlenecks. "
            "Operators with existing power agreements are at a significant advantage.",
            hours_ago=10,
        ),
        make(
            "Oracle's Ellison Commits $20B to US AI Infrastructure in WH Meeting",
            "Reuters Business", 1, ["financial", "ai", "datacenter"],
            "Larry Ellison joined other tech CEOs at the White House to announce over $20 billion "
            "in planned US AI infrastructure investment over the next 3 years, including new "
            "OCI datacenter capacity and partnerships with national labs. The announcement "
            "positions OCI as a key AI sovereign-cloud player in the US.",
            hours_ago=2,
        ),
        make(
            "Anthropic Claude 4 Achieves AGI-Level Coding: Solves 72% of SWE-Bench Verified",
            "VentureBeat AI", 2, ["ai", "compete"],
            "Anthropic released Claude 4 with a 72% solve rate on SWE-Bench Verified, the highest "
            "score ever recorded and what Anthropic calls 'AGI-level software engineering'. "
            "Claude 4 is available via API. Amazon Bedrock will carry the model; OCI Generative AI "
            "availability has not been announced.",
            hours_ago=4,
        ),
        make(
            "Kubernetes 1.32 Drops Docker Runtime Support — Enterprise Upgrade Wave Expected",
            "Ars Technica", 2, ["oss", "infrastructure", "compete"],
            "The Kubernetes project officially removed the dockershim compatibility layer in v1.32, "
            "forcing all clusters still using Docker as a runtime to migrate to containerd or CRI-O. "
            "Analysts estimate 40% of enterprise clusters are affected. Cloud providers will see "
            "a wave of re-platforming projects.",
            hours_ago=14,
        ),
        make(
            "Zero-Day in Linux Kernel Affects All Major Cloud Providers — Patch Available",
            "Reuters Tech", 1, ["security", "compete", "infrastructure"],
            "A critical zero-day vulnerability (CVE-2026-1337) in the Linux kernel affects bare-metal "
            "and virtualised environments across AWS, Azure, GCP, and OCI. A patch was released "
            "today. Cloud providers have begun rolling out emergency mitigations. OCI's security "
            "team confirmed patching is underway across all regions.",
            hours_ago=1,
        ),
        make(
            "Meta Llama 4 Released as Open Source: 400B Parameter Model Free to Download",
            "TechCrunch", 2, ["ai", "oss", "compete"],
            "Meta released Llama 4, a 400-billion parameter open-source model, under a permissive "
            "commercial licence. Early benchmarks show performance approaching GPT-4 on many tasks. "
            "The release could reshape the enterprise AI market, favouring cloud providers who "
            "can offer cost-efficient Llama 4 inference at scale.",
            hours_ago=7,
        ),
        make(
            "Show HN: I Built a Self-Hosted Kubernetes Cluster on OCI Always-Free Tier",
            "Hacker News", 4, ["community", "oss", "infrastructure"],
            "A developer shared a detailed tutorial on running a 4-node Kubernetes cluster entirely "
            "on OCI's Always-Free tier, attracting 1,200+ upvotes and 340 comments. The post is "
            "driving significant developer interest in OCI's free-tier offerings.",
            hours_ago=12,
        ),
        make(
            "Microsoft and Oracle Extend Multi-Cloud Database Partnership to 10 New Regions",
            "OCI Blog", 3, ["partnerships", "multicloud", "deals"],
            "Oracle and Microsoft announced the expansion of Oracle Database@Azure to 10 additional "
            "Azure regions, including Southeast Asia, Brazil, and Canada. The partnership now covers "
            "25 regions globally. Revenue sharing terms were not disclosed.",
            hours_ago=9,
        ),
        make(
            "EU AI Act Enforcement Begins: Cloud Providers Must Certify High-Risk AI Systems",
            "Reuters Tech", 1, ["security", "financial", "ai"],
            "The EU AI Act entered its first enforcement phase, requiring cloud providers to certify "
            "high-risk AI systems deployed in Europe. Non-compliance fines can reach 3% of global "
            "revenue. AWS and Azure have published compliance roadmaps; OCI's European compliance "
            "documentation is pending.",
            hours_ago=11,
        ),
        make(
            "xAI Raises $6B Series D at $80B Valuation to Build Colossus-2 Supercluster",
            "TechCrunch", 2, ["financial", "ai", "datacenter"],
            "Elon Musk's xAI closed a $6 billion round at an $80 billion valuation to fund "
            "Colossus-2, a 1-million GPU training cluster. The facility will require 4 gigawatts "
            "of power. Investors include sovereign wealth funds from the Gulf region, a geography "
            "where OCI is actively expanding.",
            hours_ago=16,
        ),
    ]


if __name__ == "__main__":
    main()
