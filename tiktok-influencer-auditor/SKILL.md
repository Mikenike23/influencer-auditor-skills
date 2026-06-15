---
name: tiktok-influencer-auditor
description: "Audits a TikTok creator for bot inflation and fake engagement — analysing engagement rate (likes+comments+shares / views), comment authenticity, like-to-comment and follow ratios, and view spikes to produce a 0–100 Authenticity Score with a clear Verdict. Use whenever you need to vet a TikTok creator or KOL before a partnership, sponsorship, or paid collaboration. Trigger on: 'audit this TikTok', 'is this TikTok account real', 'are their views real', 'bot check tiktok', 'vet this creator', 'should we partner with', or any tiktok.com profile URL shared with intent to assess creator credibility."
---

# TikTok Influencer Auditor

## Purpose

Vet a TikTok creator before paying for a sponsored video. Fast signal: are this account's numbers real, or inflated? Output is a structured **Authenticity Report** with a numeric score and a go/no-go verdict.

Scoring is **deterministic** — it lives in `scripts/scoring.py`, the shared engine used by all four platform auditors. TikTok engagement rate is computed as **(likes + comments + shares) / views**, the standard TikTok ER definition. Same account always returns the same score.

---

## Step 0: Parse the input

- `tiktok.com/@handle` URL or a bare handle → profile audit (default)
- If unclear, ask one quick question.

## ⚠️ Cost warning — confirm before running

TikTok data comes via Apify, which costs real money per run. Before running, tell the user:

> "Ready to run the TikTok scrape via Apify — this costs roughly $0.20–0.60. Go ahead?"

Only proceed after they confirm.

## Step 1: Get the Apify API token

```bash
grep APIFY_API_TOKEN .env 2>/dev/null | head -1
```

If missing, ask the user for it (apify.com → Settings → API & Integrations → Personal API token), then:

```bash
echo "APIFY_API_TOKEN=<token>" >> .env
```

## Step 2: Install dependencies

```bash
pip install requests --break-system-packages -q
```

## Step 3: Run the auditor

```bash
APIFY_API_TOKEN=<token> python3 scripts/tiktok_auditor.py \
  --handle "<@handle_or_url>" \
  --max-videos 30 \
  --max-comments 100 \
  > /tmp/tt_audit.json
```

It fetches profile + recent videos, then comments on the top videos; normalises them; and runs the scorer. Output JSON contains `profile`, `signals`, and a fully computed `report`.

## Step 4: Present the report

Read `/tmp/tt_audit.json` and present the `report` block. **Do not recompute the score.**

| Score | Verdict |
|-------|---------|
| 80–100 | ✅ Looks Legit |
| 60–79 | ⚠️ Mixed Signals |
| 40–59 | 🚩 Suspicious |
| 0–39 | ❌ Likely Bot-Inflated |

Report structure (chat, plus a saved markdown file or Notion page if wanted):

```
# TikTok Audit: @handle  —  [emoji] [verdict] ([score]/100)
URL: [profile URL]   ·   Date: [today]

## Signal breakdown
| Signal | Finding | Deduction |   (from report.deductions + green flags)

## Red flags        (report.red_flags)
## Green flags      (report.green_flags)
## Caveats          (report.caveats)

## Recommendation
One paragraph: partner or not? At what budget? Conditions?

## Raw summary
Followers / Following · videos analysed · avg ER% · like:comment · comments sampled
```

## Step 5: Report back

Verdict + score inline, the 2–3 biggest flags, one recommendation sentence, any caveats. Keep it short.

---

## Known limitation — follower sampling

TikTok follower lists aren't cheaply sampleable, so the **audience-quality** signal (bot followers) is skipped and surfaced as a caveat. TikTok detection therefore leans on engagement rate, comment quality, ratios, and spikes — strong signals on TikTok, where bought views usually crater the ER. If you have an actor that can sample followers, the engine will use it; otherwise treat a clean score as "no inflation detected in the signals we could see," not a guarantee.

## Error handling

- **Apify actor fails:** retry once after 30s; check apify.com/runs. Override the actor via `APIFY_TIKTOK_SCRAPER_ACTOR` / `APIFY_TIKTOK_COMMENTS_ACTOR` env vars if your account uses different ones.
- **Comments unavailable / disabled:** the script proceeds on remaining signals; `caveats` notes the gap.
- **Small account:** low sample sizes reduce confidence — `caveats` will flag it.
