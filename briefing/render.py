"""
render.py — HTML briefing generation.

Design: Unified header bar, 60/40 exec summary with amber OCI callout,
hero cards with images, compact text-only story rows. Steel-blue/teal + white + charcoal.
"""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

from briefing.config import AUDIENCE_PROFILES, AUDIENCE_ORDER

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Section metadata
# ---------------------------------------------------------------------------
SECTION_META: dict[str, dict] = {
    "ai":             {"label": "Artificial Intelligence"},
    "compete":        {"label": "Competitive Intel"},
    "financial":      {"label": "Financial & Markets"},
    "datacenter":     {"label": "Datacenter & Infrastructure"},
    "power":          {"label": "Power & Energy"},
    "deals":          {"label": "Deals & Partnerships"},
    "security":       {"label": "Security & Compliance"},
    "multicloud":     {"label": "Multi-Cloud & Ecosystem"},
    "oss":            {"label": "Open Source"},
    "partnerships":   {"label": "Strategic Partnerships"},
    "community":      {"label": "Community Signal"},
    "infrastructure": {"label": "Infrastructure"},
    "other":          {"label": "Technology"},
}

TIER_LABELS = {1: "Tier 1", 2: "Tier 2", 3: "Vendor", 4: "Community"}
TIER_COLORS = {1: "#C0392B", 2: "#2980B9", 3: "#27AE60", 4: "#8E44AD"}

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
BASE_CSS = """
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    /* Primary palette */
    --teal:        #5B9DB5;
    --teal-dark:   #3D7A96;
    --teal-light:  #D6EAF2;
    --teal-pale:   #EBF5FA;
    --charcoal:    #2C3E50;
    --charcoal2:   #34495E;

    /* Grays */
    --gray-dark:   #7F8C8D;
    --gray-mid:    #BDC3C7;
    --gray-light:  #ECF0F1;
    --gray-bg:     #F4F6F8;
    --white:       #FFFFFF;

    /* Text */
    --text:        #2C3E50;
    --text-mid:    #555E68;
    --text-muted:  #95A5A6;

    /* Borders and Shadows */
    --border:      #D5DDE3;
    --shadow:      0 2px 8px rgba(44,62,80,0.10);
    --shadow-sm:   0 1px 3px rgba(44,62,80,0.06);

    /* OCI callout — amber/gold accent */
    --oci-accent:      #D4880F;
    --oci-bg:          #FFF8EE;
    --oci-text:        #7A5200;
    --oci-label:       #B8730C;

    /* Freshness indicator */
    --new-badge-bg:    #E8F5E9;
    --new-badge-text:  #2E7D32;
    --new-border:      var(--teal);

    /* Misc */
    --radius:      4px;
    --serif:       Georgia, 'Times New Roman', serif;
  }

  html { font-size: 13px; scroll-behavior: smooth; }

  body {
    background: var(--gray-bg);
    color: var(--text);
    font-family: 'Helvetica Neue', Arial, sans-serif;
    line-height: 1.5;
  }

  a { color: var(--teal-dark); text-decoration: none; }
  a:hover { text-decoration: underline; }

  a:focus-visible,
  button:focus-visible {
    outline: 2px solid var(--teal);
    outline-offset: 2px;
  }

  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
      transition-duration: 0.01ms !important;
    }
    html { scroll-behavior: auto; }
  }

  /* -- Unified Header Bar (40px) ---------------------- */
  .unified-header {
    background: var(--charcoal);
    border-bottom: 3px solid var(--teal);
  }

  .unified-header-inner {
    max-width: 1100px;
    margin: 0 auto;
    padding: 0 24px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
  }

  .header-title {
    font-family: var(--serif);
    font-size: 18px;
    font-weight: 700;
    color: var(--white);
    letter-spacing: -0.5px;
    line-height: 1;
    text-transform: uppercase;
    white-space: nowrap;
    flex-shrink: 0;
  }

  .header-title span {
    color: var(--teal);
    font-style: italic;
    font-size: 14px;
    vertical-align: middle;
    margin-right: 3px;
  }

  .header-date {
    font-size: 9px;
    font-weight: 400;
    letter-spacing: 0.06em;
    color: rgba(255,255,255,0.55);
    white-space: nowrap;
    flex-shrink: 0;
  }

  .header-nav {
    display: flex;
    align-items: center;
    gap: 0;
    overflow-x: auto;
    flex-shrink: 1;
    min-width: 0;
  }

  .header-nav-link {
    padding: 11px 9px;
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: rgba(255,255,255,0.60);
    white-space: nowrap;
    border-bottom: 2px solid transparent;
    transition: all 0.1s;
    display: block;
    text-decoration: none;
    line-height: 1;
  }

  .header-nav-link:hover {
    color: white;
    border-bottom-color: var(--teal);
    text-decoration: none;
  }

  /* -- NEW badge ------------------------------------- */
  .new-badge {
    font-size: 7.5px;
    font-weight: 800;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--new-badge-text);
    background: var(--new-badge-bg);
    padding: 1px 4px;
    border-radius: 3px;
    flex-shrink: 0;
    display: inline-block;
    line-height: 1.4;
  }

  /* -- Audience panel -------------------------------- */
  .audience-panel { display: none; }
  .audience-panel.active { display: block; }

  /* -- Page wrapper ---------------------------------- */
  .page-wrap {
    max-width: 1100px;
    margin: 0 auto;
    padding: 14px 24px 32px;
  }

  /* -- Executive summary ----------------------------- */
  .cover-block {
    display: grid;
    grid-template-columns: 3fr 2fr;
    gap: 0;
    background: var(--white);
    border: 1px solid var(--border);
    box-shadow: var(--shadow-sm);
    margin-bottom: 14px;
    border-radius: var(--radius);
    overflow: hidden;
  }

  .cover-left {
    background: var(--charcoal);
    color: white;
    padding: 14px 16px;
  }

  .cover-overline {
    font-size: 8.5px;
    font-weight: 700;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--teal);
    margin-bottom: 6px;
  }

  .cover-bullets {
    list-style: none;
    padding: 0;
    margin: 0;
  }

  .cover-bullets li {
    display: flex;
    gap: 7px;
    align-items: flex-start;
    padding: 4px 0;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    font-size: 11.5px;
    color: rgba(255,255,255,0.88);
    line-height: 1.4;
  }

  .cover-bullets li:last-child { border-bottom: none; }

  .bullet-num {
    width: 16px;
    height: 16px;
    background: var(--teal);
    color: white;
    font-size: 9px;
    font-weight: 700;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    margin-top: 1px;
  }

  .cover-right {
    background: var(--oci-bg);
    border-left: 4px solid var(--oci-accent);
    padding: 14px 16px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 8px;
  }

  .oci-badge-strip {
    display: flex;
    align-items: center;
    gap: 5px;
  }

  .oci-badge-icon {
    color: var(--oci-accent);
    font-size: 10px;
  }

  .oci-callout-label {
    font-size: 8px;
    font-weight: 800;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--oci-label);
  }

  .oci-callout-text {
    font-size: 11.5px;
    color: var(--oci-text);
    line-height: 1.5;
  }

  /* -- Section header -------------------------------- */
  .section-block { margin-bottom: 14px; }

  .section-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
  }

  .section-label-bar {
    background: var(--teal);
    color: white;
    font-size: 8.5px;
    font-weight: 800;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    padding: 3px 10px;
    border-radius: 2px;
    white-space: nowrap;
  }

  .section-rule {
    flex: 1;
    height: 1px;
    background: var(--teal-light);
  }

  .section-count {
    font-size: 9px;
    color: var(--text-muted);
    font-weight: 600;
    white-space: nowrap;
  }

  /* -- Hero card ------------------------------------- */
  .hero-card {
    display: grid;
    grid-template-columns: 180px 1fr;
    background: var(--white);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
    box-shadow: var(--shadow-sm);
    margin-bottom: 6px;
    transition: box-shadow 0.12s;
  }

  .hero-card:hover { box-shadow: var(--shadow); }

  .hero-img {
    height: 100%;
    min-height: 120px;
    overflow: hidden;
    position: relative;
    background: var(--gray-light);
  }

  .hero-img img { width: 100%; height: 100%; object-fit: cover; display: block; }

  .hero-img-badge {
    position: absolute;
    top: 5px; left: 5px;
    font-size: 7.5px;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 2px 6px;
    border-radius: 2px;
    color: white;
  }

  .hero-body {
    padding: 10px 12px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .hero-meta {
    display: flex;
    align-items: center;
    gap: 4px;
    flex-wrap: wrap;
  }

  .hero-headline {
    font-family: var(--serif);
    font-size: 15px;
    font-weight: 700;
    color: var(--charcoal);
    line-height: 1.28;
  }

  .hero-headline a { color: var(--charcoal); }
  .hero-headline a:hover { color: var(--teal-dark); text-decoration: underline; }

  .hero-summary {
    font-size: 11px;
    color: var(--text-mid);
    line-height: 1.5;
    flex: 1;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .hero-oci {
    font-size: 10px;
    color: var(--oci-text);
    background: var(--oci-bg);
    border-left: 3px solid var(--oci-accent);
    padding: 4px 8px;
    border-radius: 2px;
    line-height: 1.4;
  }

  .hero-footer {
    font-size: 9px;
    color: var(--text-muted);
    border-top: 1px solid var(--gray-light);
    padding-top: 4px;
    margin-top: 2px;
  }

  /* -- Compact story rows ---------------------------- */
  .story-list { display: flex; flex-direction: column; gap: 1px; }

  .story-row {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 8px;
    align-items: start;
    background: var(--white);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 7px 10px;
    transition: background 0.1s;
  }

  .story-row:hover { background: var(--teal-pale); }

  .story-row.is-fresh {
    border-left: 3px solid var(--new-border);
    padding-left: 7px;
  }

  .row-left { display: flex; flex-direction: column; gap: 2px; min-width: 0; }

  .row-meta {
    display: flex;
    align-items: center;
    gap: 4px;
    flex-wrap: wrap;
  }

  .src-dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
    display: inline-block;
  }

  .src-name {
    font-size: 8.5px;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--text-muted);
  }

  .topic-pill {
    font-size: 8px;
    font-weight: 600;
    color: var(--teal-dark);
    background: var(--teal-light);
    padding: 1px 5px;
    border-radius: 8px;
  }

  .conf-pill {
    font-size: 8px;
    font-weight: 600;
    padding: 1px 5px;
    border-radius: 8px;
  }

  .conf-high   { background: #D5EFE0; color: #1A7A3C; }
  .conf-medium { background: #FEF3CD; color: #856404; }
  .conf-low    { background: #E9ECEF; color: #6C757D; }

  .row-headline {
    font-family: var(--serif);
    font-size: 12.5px;
    font-weight: 700;
    color: var(--charcoal);
    line-height: 1.28;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .row-headline a { color: var(--charcoal); }
  .row-headline a:hover { color: var(--teal-dark); text-decoration: underline; }

  .row-summary {
    font-size: 10.5px;
    color: var(--text-mid);
    line-height: 1.45;
    display: -webkit-box;
    -webkit-line-clamp: 1;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  /* row-oci: REMOVED in v2.2. Safety net to hide if accidentally emitted. */
  .row-oci {
    display: none;
  }

  .row-right {
    text-align: right;
    flex-shrink: 0;
    font-size: 8.5px;
    color: var(--text-muted);
    line-height: 1.8;
    white-space: nowrap;
  }

  /* -- Divider & footer ------------------------------ */
  .divider { height: 1px; background: var(--border); margin: 14px 0; }

  .page-footer {
    text-align: center;
    font-size: 9px;
    color: var(--text-muted);
    letter-spacing: 0.04em;
    line-height: 2;
  }

  .page-footer a { color: var(--teal-dark); }

  .footer-briefings {
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid var(--border);
  }

  .footer-briefings-label {
    font-size: 8.5px;
    font-weight: 700;
    letter-spacing: 0.10em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 4px;
  }

  .footer-briefing-link {
    font-size: 10px;
    font-weight: 600;
    color: var(--teal-dark);
    text-decoration: none;
    padding: 2px 8px;
    border-radius: 3px;
    transition: background 0.1s;
  }

  .footer-briefing-link:hover {
    background: var(--teal-pale);
    text-decoration: none;
  }

  .footer-briefing-link.current {
    color: var(--text-muted);
    pointer-events: none;
    font-weight: 400;
  }

  /* -- Responsive ------------------------------------ */
  @media (max-width: 680px) {
    .unified-header-inner {
      flex-wrap: wrap;
      height: auto;
      padding: 8px 16px;
      gap: 4px;
    }

    .header-nav {
      width: 100%;
      overflow-x: auto;
    }

    .header-date {
      display: none;
    }

    .cover-block { grid-template-columns: 1fr; }

    .cover-right {
      border-left: none;
      border-top: 4px solid var(--oci-accent);
    }

    .hero-card { grid-template-columns: 1fr; }
    .hero-img { min-height: 120px; max-height: 160px; }

    .row-headline {
      -webkit-line-clamp: 3;
    }
  }

  /* -- Scrollbar ------------------------------------- */
  ::-webkit-scrollbar { width: 5px; height: 5px; }
  ::-webkit-scrollbar-track { background: var(--gray-bg); }
  ::-webkit-scrollbar-thumb { background: var(--gray-mid); border-radius: 3px; }
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _relative_time(dt: datetime) -> str:
    now  = datetime.now(tz=timezone.utc)
    diff = now - dt
    h    = diff.total_seconds() / 3600
    if h < 1:   return f"{int(diff.total_seconds()/60)}m ago"
    if h < 24:  return f"{int(h)}h ago"
    return f"{int(h/24)}d ago"

def _esc(text: str) -> str:
    return (text or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

def _image_seed(url: str) -> int:
    return int(hashlib.md5(url.encode()).hexdigest()[:8], 16) % 1000

def _tier_color(tier: int) -> str:
    return TIER_COLORS.get(tier, "#7F8C8D")

def _section_meta(section: str) -> dict:
    return SECTION_META.get(section, SECTION_META["other"])

def _conf_class(conf: str | None) -> str:
    return {"high": "conf-high", "medium": "conf-medium"}.get(conf or "", "conf-low")

def _group_by_section(articles: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for a in articles:
        sec = a.get("classified_section") or (a["sections"][0] if a.get("sections") else "other")
        groups.setdefault(sec, []).append(a)
    return groups

def _is_fresh(pub: datetime | None, threshold_hours: int = 6) -> bool:
    """Return True if the story was published within threshold_hours."""
    if pub is None:
        return False
    return (datetime.now(tz=timezone.utc) - pub).total_seconds() / 3600 < threshold_hours

# ---------------------------------------------------------------------------
# Hero card (first article -- has image)
# ---------------------------------------------------------------------------

def _render_hero_card(article: dict, audience_id: str) -> str:
    per   = article.get("per_audience_summaries", {}).get(audience_id, {})
    head  = _esc(per.get("headline", article["title"]))
    summ  = _esc(per.get("summary",  article.get("summary","")[:250]))
    impl  = _esc(per.get("oci_implication",""))
    conf  = article.get("confidence","medium")
    topics= article.get("topics",[])[:2]
    pub   = article.get("published_at")
    rel   = _relative_time(pub) if pub else ""
    abs_t = pub.strftime("%b %d, %H:%M") if pub else ""
    tcol  = _tier_color(article["tier"])
    src   = _esc(article["source"])
    url   = _esc(article["url"])
    seed  = _image_seed(article["url"])
    pills = "".join(f'<span class="topic-pill">{_esc(t)}</span>' for t in topics)

    oci = f'<div class="hero-oci">{impl}</div>' if impl else ""

    new_badge = ""
    if _is_fresh(pub):
        new_badge = ' <span class="new-badge" aria-label="Published within the last 6 hours">NEW</span>'

    return f"""<article class="hero-card">
      <div class="hero-img">
        <img src="https://picsum.photos/seed/{seed}/400/260" alt="" loading="lazy">
        <span class="hero-img-badge" style="background:{tcol}">{src}</span>
      </div>
      <div class="hero-body">
        <div class="hero-meta">
          {pills}
          <span class="conf-pill {_conf_class(conf)}">{conf}</span>
          {new_badge}
        </div>
        <div class="hero-headline"><a href="{url}" target="_blank" rel="noopener">{head}</a></div>
        <div class="hero-summary">{summ}</div>
        {oci}
        <div class="hero-footer">{src} &nbsp;·&nbsp; {abs_t} &nbsp;·&nbsp; {rel}</div>
      </div>
    </article>"""


# ---------------------------------------------------------------------------
# Compact list row (non-hero articles -- no image, no OCI)
# ---------------------------------------------------------------------------

def _render_story_row(article: dict, audience_id: str) -> str:
    per   = article.get("per_audience_summaries", {}).get(audience_id, {})
    head  = _esc(per.get("headline", article["title"]))
    summ  = _esc(per.get("summary",  article.get("summary","")[:180]))
    impl  = _esc(per.get("oci_implication",""))
    conf  = article.get("confidence","medium")
    topics= article.get("topics",[])[:1]
    pub   = article.get("published_at")
    rel   = _relative_time(pub) if pub else ""
    abs_t = pub.strftime("%b %d") if pub else ""
    tcol  = _tier_color(article["tier"])
    src   = _esc(article["source"])
    url   = _esc(article["url"])
    pills = "".join(f'<span class="topic-pill">{_esc(t)}</span>' for t in topics)

    # Freshness indicators
    fresh = _is_fresh(pub)
    fresh_class = " is-fresh" if fresh else ""
    new_badge = ""
    if fresh:
        new_badge = '<span class="new-badge" aria-label="Published within the last 6 hours">NEW</span>'

    return f"""<article class="story-row{fresh_class}">
      <div class="row-left">
        <div class="row-meta">
          <span class="src-dot" style="background:{tcol}"></span>
          <span class="src-name">{src}</span>
          {new_badge}
          {pills}
          <span class="conf-pill {_conf_class(conf)}">{conf}</span>
        </div>
        <div class="row-headline"><a href="{url}" target="_blank" rel="noopener">{head}</a></div>
        <div class="row-summary">{summ}</div>
      </div>
      <div class="row-right">{abs_t}<br>{rel}</div>
    </article>"""


# ---------------------------------------------------------------------------
# Section
# ---------------------------------------------------------------------------

def _render_section(section: str, articles: list[dict], audience_id: str) -> str:
    meta   = _section_meta(section)
    sec_id = f"{audience_id}-{section}"
    n      = len(articles)

    hero_html = _render_hero_card(articles[0], audience_id) if articles else ""
    rows_html = "".join(_render_story_row(a, audience_id) for a in articles[1:])
    rows_block = f'<div class="story-list">{rows_html}</div>' if articles[1:] else ""

    return f"""<section class="section-block" id="{sec_id}" aria-label="{_esc(meta['label'])}">
      <div class="section-header">
        <span class="section-label-bar">{_esc(meta['label'])}</span>
        <div class="section-rule"></div>
        <span class="section-count">{n} {"story" if n==1 else "stories"}</span>
      </div>
      {hero_html}
      {rows_block}
    </section>"""

# ---------------------------------------------------------------------------
# Section nav (now renders header-nav-link items for the unified header)
# ---------------------------------------------------------------------------

def _render_section_nav(sections: list[tuple[str,int]], audience_id: str) -> str:
    return "".join(
        f'<a class="header-nav-link" href="#{audience_id}-{s}">{_esc(_section_meta(s)["label"])}</a>'
        for s, c in sections
    )

# ---------------------------------------------------------------------------
# Executive summary (cover-page block)
# ---------------------------------------------------------------------------

def _render_exec_summary(exec_data: dict, audience_id: str, articles: list[dict]) -> str:
    bullets = exec_data.get("bullets", [])
    impl    = _esc(exec_data.get("oci_implication_of_day", ""))

    bullet_items = "".join(
        f'<li><span class="bullet-num">{i+1}</span> {_esc(b)}</li>'
        for i, b in enumerate(bullets)
    )

    oci_box = ""
    if impl:
        oci_box = f"""<div class="oci-badge-strip">
          <span class="oci-badge-icon">&#9670;</span>
          <span class="oci-callout-label">OCI Implication of the Day</span>
        </div>
        <div class="oci-callout-text">{impl}</div>"""

    return f"""<div class="cover-block" id="{audience_id}-exec" aria-label="Executive Summary">
      <div class="cover-left">
        <div class="cover-overline">Executive Summary</div>
        <ul class="cover-bullets">{bullet_items}</ul>
      </div>
      <div class="cover-right" aria-label="OCI Implication of the Day">
        {oci_box}
      </div>
    </div>"""

# ---------------------------------------------------------------------------
# Audience panel
# ---------------------------------------------------------------------------

def _render_audience_panel(
    audience_id: str,
    articles: list[dict],
    exec_summary: dict,
    generation_time: datetime,
) -> str:
    profile = AUDIENCE_PROFILES[audience_id]
    groups  = _group_by_section(articles)

    # order sections by audience weights
    ordered: list[tuple[str, list[dict]]] = []
    seen: set[str] = set()
    for sec in profile["section_weights"]:
        if sec in groups:
            ordered.append((sec, groups[sec]))
            seen.add(sec)
    for sec, arts in groups.items():
        if sec not in seen:
            ordered.append((sec, arts))

    sec_with_counts = [(s, len(a)) for s, a in ordered]
    sec_nav   = _render_section_nav(sec_with_counts, audience_id)
    exec_html = _render_exec_summary(exec_summary, audience_id, articles)
    secs_html = "\n".join(_render_section(s, a, audience_id) for s, a in ordered)
    gen_str   = generation_time.strftime("%Y-%m-%d %H:%M UTC")

    # Footer briefing links
    briefing_links = ""
    for aud_id in AUDIENCE_ORDER:
        p = AUDIENCE_PROFILES[aud_id]
        current_cls = " current" if aud_id == audience_id else ""
        aria_current = ' aria-current="page"' if aud_id == audience_id else ""
        briefing_links += f'<a class="footer-briefing-link{current_cls}" href="?audience={aud_id}"{aria_current}>{_esc(p["name"])}</a>\n'

    return f"""<div class="audience-panel" data-audience="{audience_id}" data-sec-nav="{_esc(sec_nav)}">
      <main>
        <div class="page-wrap">
          {exec_html}
          {secs_html}
          <div class="divider"></div>
          <footer class="page-footer">
            <div>{_esc(profile['name'])} &middot; {gen_str} &middot; {len(articles)} stories &middot;
            Powered by <a href="https://claude.ai">Claude</a></div>
            <div class="footer-briefings">
              <div class="footer-briefings-label">View other briefings</div>
              {briefing_links}
            </div>
          </footer>
        </div>
      </main>
    </div>"""

# ---------------------------------------------------------------------------
# Unified header bar
# ---------------------------------------------------------------------------

def _render_masthead(generation_time: datetime) -> str:
    date_str = generation_time.strftime("%a %b %d, %Y")
    return f"""<header class="unified-header">
      <div class="unified-header-inner">
        <div class="header-title"><span>AI</span> Daily Briefing</div>
        <div class="header-date">{date_str}</div>
        <nav class="header-nav" aria-label="Section navigation" id="header-nav">
        </nav>
      </div>
    </header>"""

def _render_audience_tabs() -> str:
    tabs = ""
    for aud_id in AUDIENCE_ORDER:
        p = AUDIENCE_PROFILES[aud_id]
        accent = _esc(p.get('accent_color', '#FFFFFF'))
        tabs += f"""<button class="audience-tab" data-switch="{aud_id}" data-accent="{accent}" onclick="switchAudience('{aud_id}')" style="display:none">
          {_esc(p['name'])}
        </button>"""
    return f"""<div style="display:none">
      {tabs}
    </div>"""

# ---------------------------------------------------------------------------
# JS switcher
# ---------------------------------------------------------------------------
SWITCHER_JS = """
  function switchAudience(id) {
    document.querySelectorAll('.audience-panel').forEach(el => el.classList.remove('active'));
    const p = document.querySelector('.audience-panel[data-audience="'+id+'"]');
    if (p) {
      p.classList.add('active');
      // Populate header nav from the active panel's section nav data
      var nav = document.getElementById('header-nav');
      if (nav && p.dataset.secNav) {
        nav.innerHTML = p.dataset.secNav;
      }
    }
    document.querySelectorAll('.audience-tab').forEach(b => {
      b.classList.toggle('active', b.dataset.switch===id);
    });
    try { localStorage.setItem('oci-aud', id); } catch(e) {}
  }
  (function(){
    // Check URL parameter first
    var params = new URLSearchParams(window.location.search);
    var urlAud = params.get('audience') || '';
    var last=''; try { last=localStorage.getItem('oci-aud')||''; } catch(e) {}
    var ids=Array.from(document.querySelectorAll('.audience-panel')).map(function(p){return p.dataset.audience});
    var pick = ids.includes(urlAud) ? urlAud : (ids.includes(last) ? last : (ids[0]||''));
    switchAudience(pick);
  })();
"""

# ---------------------------------------------------------------------------
# Page assembly
# ---------------------------------------------------------------------------

def _page_html(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
{BASE_CSS}
  .mt {{ margin-top: 16px; }}
  </style>
</head>
<body>
{body}
</body>
</html>"""


def render_combined_html(
    all_audience_data: dict[str, dict],
    generation_time: datetime | None = None,
) -> str:
    if generation_time is None:
        generation_time = datetime.now(tz=timezone.utc)

    date_str   = generation_time.strftime("%Y-%m-%d")
    panels     = ""
    for aud_id in AUDIENCE_ORDER:
        data   = all_audience_data.get(aud_id, {})
        panels += _render_audience_panel(
            aud_id,
            data.get("articles", []),
            data.get("exec_summary", {"bullets":[], "oci_implication_of_day":""}),
            generation_time,
        )

    body = f"""
    {_render_masthead(generation_time)}
    {_render_audience_tabs()}
    {panels}
    <script>{SWITCHER_JS}</script>"""

    return _page_html(f"OCI AI Intelligence — {date_str}", body)


def render_single_audience_html(
    audience_id: str,
    articles: list[dict],
    exec_summary: dict,
    generation_time: datetime | None = None,
) -> str:
    if generation_time is None:
        generation_time = datetime.now(tz=timezone.utc)

    profile  = AUDIENCE_PROFILES[audience_id]
    date_str = generation_time.strftime("%Y-%m-%d")
    panel    = _render_audience_panel(audience_id, articles, exec_summary, generation_time)

    # make the single panel always visible
    panel = panel.replace('class="audience-panel"', 'class="audience-panel active"', 1)

    # Extract section nav from the panel's data attribute and inject into header
    body = f"""
    {_render_masthead(generation_time)}
    {panel}
    <script>
    (function(){{
      var panel = document.querySelector('.audience-panel.active');
      var nav = document.getElementById('header-nav');
      if (panel && nav && panel.dataset.secNav) {{
        nav.innerHTML = panel.dataset.secNav;
      }}
    }})();
    </script>"""

    return _page_html(f"OCI AI Intelligence — {_esc(profile['name'])} — {date_str}", body)


# ---------------------------------------------------------------------------
# File output
# ---------------------------------------------------------------------------

def save_briefings(
    all_audience_data: dict[str, dict],
    output_dir: Path,
    generation_time: datetime | None = None,
) -> dict[str, Path]:
    if generation_time is None:
        generation_time = datetime.now(tz=timezone.utc)

    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    for aud_id in AUDIENCE_ORDER:
        if aud_id not in all_audience_data:
            continue
        data     = all_audience_data[aud_id]
        articles = data.get("articles", [])
        html     = render_single_audience_html(aud_id, articles, data.get("exec_summary", {}), generation_time)
        p        = output_dir / f"{aud_id}.html"
        p.write_text(html, encoding="utf-8")
        paths[aud_id] = p
        logger.info("Wrote %s (%d bytes)", p, len(html))

    combined   = render_combined_html(all_audience_data, generation_time)
    index_path = output_dir / "index.html"
    index_path.write_text(combined, encoding="utf-8")
    paths["index"] = index_path
    logger.info("Wrote %s (%d bytes)", index_path, len(combined))

    return paths
