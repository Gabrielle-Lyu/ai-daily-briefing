# QA Verification Report -- 2026-03-11 Regenerated Briefings

**Date:** 2026-03-11
**Scope:** Verify that regenerated briefings address feedback from audience simulation
**Files reviewed:** karan.html, nathan.html, greg.html, mahesh.html, config/audiences.py, app/rendering/render.py, feedback_synthesis.md, all 4 individual feedback files

---

## P0 Issues

### A1: Story Deduplication -- PARTIAL FAIL

**Exact URL deduplication: PASS**
The renderer now includes URL-level deduplication logic (render.py lines 846-857). No briefing contains the same URL twice. This is confirmed across all four HTML files.

**Event-level (same story, different outlets) deduplication: FAIL**
The Meta/Moltbook acquisition still appears from multiple outlets within individual briefings:

| Audience | Moltbook articles | Sources |
|----------|-------------------|---------|
| Karan    | 1                 | SiliconAngle only -- PASS |
| Nathan   | 2                 | SiliconAngle (Deals hero) + TechCrunch (AI section) |
| Greg     | 3                 | TechCrunch (AI), SiliconAngle (Deals hero), The Register (Deals grid) |
| Mahesh   | 3                 | TechCrunch (AI), SiliconAngle (Deals hero), The Register (Deals grid) |

Greg's original feedback specifically cited 5 Moltbook appearances. Now it is down to 3, which is an improvement but still wastes 2 card slots per briefing on the same acquisition story from different outlets.

Additional same-event duplicates found:
- **Greg**: Gemini Workspace integration appears twice (SiliconAngle + Ars Technica), both in the AI section, covering the same product announcement.
- **Mahesh**: Thinking Machines/Nvidia deal appears twice (TechCrunch + SiliconAngle), both in the Deals section.

**Root cause:** The renderer deduplicates by exact URL only. Event-level clustering (grouping articles about the same underlying event from different outlets) has not been implemented. This remains a pipeline/classifier issue as noted in the synthesis.

**Verdict:** URL dedup works. Event-level dedup remains broken. The original P0 was specifically about event-level dedup. **FAIL (partial improvement).**

---

### A2: Section Classification -- PARTIAL FAIL

The pipeline still classifies stories into generic sections rather than per-audience taxonomy. Evidence:

| Audience | Profile section_weights keys | Sections rendered | Missing weighted sections |
|----------|------------------------------|-------------------|--------------------------|
| Karan    | financial, compete, datacenter, ai, deals | financial, ai, deals, security | **compete** (0.25), **datacenter** (0.15); unwanted **security** present |
| Nathan   | multicloud, ai, deals, compete, financial | ai, deals, financial, security | **multicloud** (0.30), **compete** (0.10); unwanted **security** present |
| Greg     | compete, ai, oss, partnerships, community | compete, ai, deals, datacenter, financial, security | **oss** (0.15), **partnerships** (0.10), **community** (0.05); unwanted deals, datacenter, financial, security present |
| Mahesh   | datacenter, power, ai, deals, security | ai, deals, security, financial | **datacenter** (0.25), **power** (0.20); unwanted **financial** present |

Key observations:
- Greg does now have a Competitive Intel section (PASS for that specific section).
- However, the system still delivers sections not in the audience's weight map (e.g., security for Karan/Nathan, financial for Greg/Mahesh) while omitting sections that ARE in the weight map.
- No "empty section" placeholder is rendered when no stories match a weighted section.

**Verdict:** Classification still uses a largely generic taxonomy. Some sections now match (Greg's compete), but most audience-specific sections remain missing. **FAIL (minor improvement for Greg).**

---

## P1 Issues

### B2: Nav Bar Server-Rendered -- PASS

The `render_single_audience_html` function (render.py lines 1017-1036) now server-renders nav links directly into the `<nav>` element in the HTML header. Evidence from all four HTML files:

**karan.html line 607:**
```
<nav class="header-nav" aria-label="Section navigation" id="header-nav">
  <a class="header-nav-link" href="#karan-financial">Financial &amp; Markets</a>...
</nav>
```

All four briefings have nav links present directly in the HTML source, not injected via JavaScript. The combined index.html still uses JS injection for multi-audience switching, which is acceptable since the individual files work without JS.

**Verdict: PASS.**

---

### C1: Karan Tone Guidance Updated -- PASS

audiences.py Karan `tone_guidance` (lines 14-21) now includes:
- "Maximum 20 words per executive summary bullet." -- Present
- "One crisp sentence per non-hero story summary." -- Present (as "One crisp sentence per non-hero story summary.")
- "Use plain language -- no financial jargon (avoid: 'bear thesis,' 'sentiment shift,' 'beachhead')." -- Present
- "Target total briefing read time under 90 seconds." -- Present

**Verdict: PASS** (config updated as requested).

**Note:** The actual briefing content does NOT fully comply with the guidance. Executive summary bullets are still 1-3 sentences and exceed 20 words. For example, bullet 1: "Oracle cloud revenue +44%: Q3 earnings beat ($1.79 vs $1.70 EPS) and raised full-year guidance silence AI disruption fears." is ~22 words but one sentence, which is close. However, bullet 5 is 31 words. This is a pipeline/LLM enforcement issue, not a config issue.

---

### C3: Nathan Tone Guidance (Action-Oriented Framing) -- PASS

audiences.py Nathan `tone_guidance` (lines 38-43) now includes:
- "Use action-oriented framing: 'OCI should evaluate...' not 'For OCI, this validates...'" -- Present
- "Name specific ISVs, GSIs, and portfolio companies -- avoid vague references like 'peers' or 'potential partners.'" -- Present

The briefing content shows evidence of compliance: Nathan's OCI implications use "OCI should evaluate" language (e.g., "OCI should evaluate fast-tracking co-sell agreements with ISVs like Databricks, Snowflake, and Palantir"). Named companies appear throughout (Wiz, Orca Security, Accenture, Deloitte, etc.).

**Verdict: PASS.**

---

### C5: Greg Tone Guidance (Technical-First) -- PASS

audiences.py Greg `tone_guidance` (lines 60-66) now includes:
- "Prioritize technical depth over strategic framing." -- Present
- "Lead AI stories with architecture, model size, benchmark scores, and inference metrics." -- Present
- "Include specific numbers: parameter counts, tokens/sec, latency, pricing." -- Present
- "Never use MBA jargon ('escape velocity,' 'commands premium multiples')." -- Present
- "Be direct about implications for OCI's AI and data strategy with technical specifics." -- Present

The briefing content shows partial compliance. The Excel/Copilot story and Anthropic story have more technical framing. However, some stories still lack the specific numerical metrics requested (e.g., no parameter counts, no tokens/sec figures in the Gemini or Legora stories). This is a pipeline/LLM enforcement issue.

**Verdict: PASS** (config updated correctly; content partially improved).

---

### CSS Line-Clamp (.card-summary) -- PASS (also covers P2 B3)

In render.py, `.card-summary` CSS (lines 532-540) specifies:
```css
-webkit-line-clamp: 3;
```

This is confirmed in all four HTML files (e.g., karan.html line 499). The value is 3, not 1 as was the original problem.

Additionally, `.hero-summary` also uses `-webkit-line-clamp: 3` (line 442 in render.py).

**Verdict: PASS.**

---

## P2 Issues (Spot Checks)

### B3: CSS Line-Clamp -- PASS
Already covered above. `.card-summary` uses `line-clamp: 3`.

---

## Summary

| Issue ID | Priority | Description | Verdict | Notes |
|----------|----------|-------------|---------|-------|
| A1 | P0 | Story deduplication | **PARTIAL FAIL** | URL dedup works. Event-level dedup (same story, different outlets) still broken. Greg has 3 Moltbook articles, Mahesh has 3 Moltbook + 2 Thinking Machines, Nathan has 2 Moltbook. |
| A2 | P0 | Section classification matches audience taxonomy | **FAIL** | Most audience-specific sections still missing (Karan: no compete/datacenter; Nathan: no multicloud/compete; Greg: no oss/partnerships/community; Mahesh: no datacenter/power). Unwanted sections still rendered. |
| B2 | P1 | Nav bar server-rendered | **PASS** | Nav links present in HTML source for all single-audience files. |
| C1 | P1 | Karan tone guidance updated | **PASS** | Config reflects all requested brevity/jargon constraints. |
| C3 | P1 | Nathan action-oriented framing | **PASS** | Config updated; content shows "OCI should evaluate" patterns and named companies. |
| C5 | P1 | Greg technical-first tone | **PASS** | Config updated; content partially improved but still lacks specific metrics in some stories. |
| B3/CSS | P2 | .card-summary line-clamp 3 | **PASS** | Confirmed at 3 lines in CSS. |

---

## Remaining Risks

1. **Event-level deduplication (A1) is the most impactful remaining defect.** The renderer deduplicates by URL, but the pipeline feeds multiple URLs covering the same event into the same briefing. This wastes 2-4 card slots per briefing and was the most common complaint across all four executives.

2. **Section taxonomy mismatch (A2) is the root cause of most content complaints.** Stories are still classified into a generic section set. The renderer orders sections by audience weights (which is correct), but if the classifier never assigns stories to audience-specific keys like "multicloud," "compete," "oss," "power," or "datacenter," those sections never appear. This requires pipeline/classifier changes, not rendering changes.

3. **Content tone enforcement** is partially addressed by config updates but ultimately depends on the LLM prompt system honoring the tone_guidance strings at generation time. The config changes are necessary but not sufficient.

---

*QA verification completed: 2026-03-11*
*Verified by: QA Engineering*
