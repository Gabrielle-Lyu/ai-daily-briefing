# Briefing Feedback -- Karan Batta, SVP Product
**Date:** 2026-03-11
**Briefing reviewed:** karan.html (Wed Mar 11, 2026)

---

## Bottom Line

This briefing is about 60% of where it needs to be. The Oracle earnings story is the right lead and the OCI framing is useful. But the section mix does not reflect my priorities, the competitive intel I actually need is missing entirely, and the writing is too verbose for a 5am scan. I should be able to get the full picture in under 90 seconds. Today that took closer to four minutes.

---

## 1. Missing: Competitive Intelligence Section

My profile weights competitive intel at 0.25 -- second only to financial. There is no dedicated Competitive Intel section in this briefing. Zero.

The AWS Security Hub multicloud story is buried in "Security & Compliance." The Google Gemini Workspace story is filed under "Artificial Intelligence." Both of these are competitive moves that directly threaten OCI's positioning. They should be front and center under a "Competitive Landscape" or "Compete" header so I can see the full threat picture in one glance.

What I need in a Compete section:
- AWS, Azure, GCP product launches or pricing moves that affect OCI deal motion
- Hyperscaler capacity and region expansion announcements
- Enterprise wins/losses that signal share shifts
- Analyst report excerpts or consensus changes on cloud market share

This is the single biggest gap in the briefing.

---

## 2. Missing: Datacenter / Infrastructure Section

Datacenter is weighted 0.15 in my profile. There is no section for it. The Nexthop AI networking story touches infrastructure but is filed under Deals. If there were no datacenter stories today, say so explicitly -- a one-liner like "No material datacenter/infrastructure stories in the last 24 hours" is better than silence, because silence makes me wonder if the system is broken or if the category was just dropped.

---

## 3. Section Balance Is Off

| Section | My Weight | Stories | Verdict |
|---------|-----------|---------|---------|
| Financial & Markets | 0.35 | 2 | Underweight. This should be the deepest section. Need more: analyst reactions, peer comps, after-hours trading color on ORCL. |
| Compete | 0.25 | 0 (no section) | Missing entirely. Unacceptable. |
| Datacenter | 0.15 | 0 (no section) | Missing entirely. |
| AI | 0.15 | 4 | Over-represented. Legora and Rhoda are interesting but not 4-story interesting for my role. Two would suffice. |
| Deals & Partnerships | 0.10 | 4 | Way over-represented. The Anchr food supply chain story at $5.8M seed is noise at my altitude. Meta/Moltbook is speculative. Cut to 1-2 stories max. |
| Security & Compliance | not weighted | 2 | Not in my profile weights at all, yet gets its own section. The AWS story belongs in Compete. Armadin is interesting but secondary. |

The briefing is giving me 4 stories in sections I care least about and zero stories in my second-highest priority category. Fix the allocation logic.

---

## 4. Tone: Too Verbose, Too Much Jargon

My tone preference is "concise, high signal, strategic" with guidance to deliver "one crisp insight per item."

Problems:

**Executive Summary bullets are too long.** Each bullet is 2-3 sentences. They should be 1 sentence each, max 20 words. Example:

- Current: "Oracle cloud revenue +44%: Q3 earnings beat ($1.79 vs $1.70 EPS estimate) with raised full-year guidance signals AI infrastructure demand is accelerating Oracle's core business, not cannibalizing it -- a direct rebuttal to bear thesis and a strong platform for OCI product investment."
- Should be: "Oracle cloud +44%, beat EPS by $0.09, raised guidance -- AI demand accelerating core business, not cannibalizing it."

**OCI Implication of the Day is a wall of text.** That right-panel paragraph is roughly 100 words with no line breaks. It tries to cover Oracle earnings, AWS security, Google Workspace, and a partnership recommendation all in one block. Break it into 3 bullet points or cut it to the single most important implication. I do not need a strategy memo here -- I need a trigger for a conversation.

**Jargon that should be cut:**
- "bear thesis" -- say "skeptic narrative" or just drop it
- "sentiment shift in the analytics software space where profitability discipline now commands a premium" -- just say "investors rewarding margins over growth"
- "winner-take-most dynamic" -- unnecessary
- "beachhead" -- unnecessary

**Story summaries are 3 sentences when 1 would do.** The card summaries for non-hero stories are truncated to 1 line in the UI anyway (via CSS line-clamp). So the system is generating 3-4 sentences of summary text that the user never sees. Either show the full text or generate less.

---

## 5. Financial Section Needs More Depth

Financial is my top priority at 0.35. Two stories is not enough. On a day when Oracle reports earnings that beat by $0.09 and cloud revenue jumps 44%, I need:

- After-hours / pre-market price action
- Key analyst upgrades or target changes (Morgan Stanley, Goldman, etc.)
- Peer context: how does 44% cloud growth compare to AWS and Azure most recent quarters?
- Remaining performance obligations (RPO) or backlog figures if reported
- Any margin commentary from the call

The Domo story is fine as a secondary signal but it is not material to my job. If the system cannot find more financial stories, at least deepen the Oracle story with more data points instead of giving me one hero card and one card about a sub-$500M BI vendor.

---

## 6. Relevance Filtering

Some stories do not clear the bar for an SVP Product briefing:

- **Anchr ($5.8M seed, food supply chain):** This is a seed-stage startup in food logistics. Not relevant to my role unless it is running on OCI or competing for a workload we care about. Cut.
- **Meta deepfake moderation:** This is a content policy story. The OCI angle ("enterprise customers demanding governance controls") is a stretch. Move to a lower tier or cut.
- **Meta acquires Moltbook:** Interesting as a trend signal but the "OCI should assess multi-agent infrastructure" recommendation is too speculative to lead the Deals section. Demote to a secondary card.

---

## 7. Source Diversity

Every single story in today's briefing comes from SiliconAngle. Every one. That is a single-source briefing, not an intelligence product. I need signal from Reuters, The Information, Bloomberg, Stratechery, analyst notes, or at minimum TechCrunch/VentureBeat. If the RSS pipeline is only pulling from one source, that is a system bug. If SiliconAngle happened to be the only source publishing overnight, flag that explicitly so I know it is a coverage gap, not a design choice.

---

## 8. Layout Complaints

- **Nav bar is empty on load.** The section navigation links in the header are injected via JavaScript from a data attribute. If JS fails or is slow, I see an empty nav bar. Server-render those links.
- **Hero card images are placeholder stock photos** (picsum.photos). Either use real article thumbnails or drop images entirely. Random photos add no information and undermine credibility.
- **12 stories is too many for my profile.** At the weights I have set, 8-10 would be the right number with tighter relevance filtering. Quality over quantity.

---

## Summary of Requested Changes (Priority Order)

1. **Add a Competitive Intelligence section** mapped to my 0.25 "compete" weight. Populate with hyperscaler product moves, pricing, region launches, and enterprise win/loss signals.
2. **Add a Datacenter/Infrastructure section** or explicitly note when no stories qualify.
3. **Cut Deals to 1-2 stories, AI to 2 stories.** Reallocate those slots to Financial and Compete.
4. **Shorten everything.** Exec summary bullets: 1 sentence. OCI Implication: 3 bullets max. Story summaries: 1-2 sentences.
5. **Deepen the Oracle earnings story** with analyst reactions, price targets, peer comps, RPO data.
6. **Fix source diversity.** A single-source briefing is not acceptable.
7. **Remove Security section** from my briefing unless a story has direct OCI product implications. Fold the AWS Security Hub story into Compete.
8. **Drop placeholder images.** Use real thumbnails or no images.
9. **Remove sub-$50M deals and seed rounds** unless directly OCI-relevant.
10. **Server-render the nav links** instead of relying on client-side JS injection.

---

*Feedback submitted: 2026-03-11 ~05:45 UTC*
