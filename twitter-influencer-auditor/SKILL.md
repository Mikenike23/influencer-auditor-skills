---
name: twitter-influencer-auditor
description: "Audits an X/Twitter influencer account for bot inflation and fake engagement — analysing follower quality, engagement-rate anomalies, reply authenticity, engagement spikes, and account history to produce a 0–100 Authenticity Score with a clear Verdict. Use whenever you need to vet an X/Twitter creator or KOL before a partnership, sponsorship, paid promotion, or collab. Trigger on: 'audit this Twitter account', 'is this X account real', 'are their followers real', 'bot check twitter', 'vet this KOL', 'verify this crypto influencer', or any x.com / twitter.com profile URL shared with intent to assess creator credibility."
---

# Twitter / X Influencer Auditor

## Purpose

Vet an X/Twitter influencer before spending money on a paid tweet or KOL promotion. Fast signal: are this account's numbers real, or padded with bots? Output is a structured **Authenticity Report** with a numeric score and a go/no-go verdict.

Scoring is **deterministic** — it lives in `scripts/scoring.py`, the shared engine used by all four platform auditors. The same account always returns the same score, so results are reproducible and comparable across a roster.

---

## Step 0: Parse the input

- `x.com/@handle` or `twitter.com/@handle` URL → account audit (default)
- A bare handle → prepend `x.com/`
- If unclear, ask one quick question.

## ⚠️ Cost warning — confirm before running

Apify (the scraping backend) costs real money per run. Before running, tell the user:

> "Ready to run the X scrape via Apify — this costs roughly $0.20–0.50. Go ahead?"

Only proceed after they confirm.

## Step 1: Get the Apify API token

```bash
grep APIFY_API_TOKEN .env 2>/dev/null | head -1
```

If missing, ask the user for it (apify.com → Settings → API & Integrations → Personal API token; new accounts get $5 free credit), then:

```bash
echo "APIFY_API_TOKEN=<token>" >> .env
```

## Step 2: Install dependencies

```bash
pip install requests --break-system-packages -q
```

## Step 3: Run the auditor

The script lives at `scripts/account_auditor.py` (with `scripts/scoring.py` beside it).

```bash
APIFY_API_TOKEN=<token> python3 scripts/account_auditor.py \
  --handle "<@handle_or_url>" \
  --max-tweets 100 \
  --max-follower-sample 200 \
  > /tmp/tw_audit.json
```

It fetches profile + recent tweets, a follower sample, and replies to the top tweets; normalises them; and runs the scorer. Output JSON contains `profile`, `signals`, and a fully computed `report` (`authenticity_score`, `verdict`, `deductions`, `red_flags`, `green_flags`, `caveats`).

## Step 4: Present the report

Read `/tmp/tw_audit.json` and present the `report` block. **Do not recompute the score** — the engine already did. Your job is to narrate it clearly.

| Score | Verdict |
|-------|---------|
| 80–100 | ✅ Looks Legit |
| 60–79 | ⚠️ Mixed Signals |
| 40–59 | 🚩 Suspicious |
| 0–39 | ❌ Likely Bot-Inflated |

Report structure (chat, and a saved markdown file or Notion page if the user wants one):

```
# X/Twitter Audit: @handle  —  [emoji] [verdict] ([score]/100)
URL: [profile URL]   ·   Date: [today]

## Signal breakdown
| Signal | Finding | Deduction |
(one row per item in report.deductions, plus the green flags)

## Red flags        (report.red_flags)
## Green flags      (report.green_flags)
## Caveats          (report.caveats — data gaps that limit confidence)

## Recommendation
One paragraph: partner or not? At what budget? Any conditions (e.g. price on CPE, not follower count)?

## Raw summary
Followers / Following · account age · tweets analysed · avg ER% · follower sample size (% suspicious) · replies sampled
```

## Step 5: Report back

1. Verdict + score inline (bold, one line)
2. The 2–3 biggest red or green flags
3. One clear recommendation sentence
4. Any caveats that materially limit confidence

Keep it short.

---

## Error handling

- **Protected/private account:** can't audit without following — a private account pitching paid deals is itself a yellow flag.
- **No impressions data:** X withholds impressions for non-owners; the script falls back to follower-based ER and notes it in `caveats`.
- **Apify actor fails:** retry once after 30s; if it fails again, check apify.com/runs. Common cause: anti-scraping.
- **Small account (<1K followers):** low sample sizes make detection unreliable — `caveats` will flag it; weight follower quality more heavily.
- **Different Apify actors:** override via `APIFY_TWITTER_SCRAPER_ACTOR` / `APIFY_TWITTER_FOLLOWERS_ACTOR` env vars if your account uses different actors.
