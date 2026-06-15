---
name: instagram-influencer-auditor
description: "Audits an Instagram creator for bot inflation and fake engagement — analysing engagement rate (likes+comments / followers), comment authenticity, like-to-comment and follow ratios, and engagement spikes to produce a 0–100 Authenticity Score with a clear Verdict. Use whenever you need to vet an Instagram creator or KOL before a partnership, sponsorship, or paid collaboration. Trigger on: 'audit this Instagram', 'is this IG account real', 'are their followers real', 'bot check instagram', 'vet this creator', 'should we partner with', or any instagram.com profile URL shared with intent to assess creator credibility."
---

# Instagram Influencer Auditor

## Purpose

Vet an Instagram creator before paying for a sponsored post or story. Fast signal: are this account's numbers real, or padded with bots? Output is a structured **Authenticity Report** with a numeric score and a go/no-go verdict.

Scoring is **deterministic** — it lives in `scripts/scoring.py`, the shared engine used by all four platform auditors. Instagram engagement rate is computed as **(likes + comments) / followers**, the standard public-ER definition. Same account always returns the same score.

---

## Step 0: Parse the input

- `instagram.com/handle` URL or a bare handle → profile audit (default)
- If unclear, ask one quick question.

## ⚠️ Cost warning — confirm before running

Instagram data comes via Apify, which costs real money per run. Before running, tell the user:

> "Ready to run the Instagram scrape via Apify — this costs roughly $0.20–0.60. Go ahead?"

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
APIFY_API_TOKEN=<token> python3 scripts/instagram_auditor.py \
  --handle "<@handle_or_url>" \
  --max-posts 24 \
  --max-comments 100 \
  > /tmp/ig_audit.json
```

It fetches profile + recent posts, then comments on the top posts; normalises them; and runs the scorer. Output JSON contains `profile`, `signals`, and a fully computed `report`.

## Step 4: Present the report

Read `/tmp/ig_audit.json` and present the `report` block. **Do not recompute the score.**

| Score | Verdict |
|-------|---------|
| 80–100 | ✅ Looks Legit |
| 60–79 | ⚠️ Mixed Signals |
| 40–59 | 🚩 Suspicious |
| 0–39 | ❌ Likely Bot-Inflated |

Report structure (chat, plus a saved markdown file or Notion page if wanted):

```
# Instagram Audit: @handle  —  [emoji] [verdict] ([score]/100)
URL: [profile URL]   ·   Date: [today]

## Signal breakdown
| Signal | Finding | Deduction |   (from report.deductions + green flags)

## Red flags        (report.red_flags)
## Green flags      (report.green_flags)
## Caveats          (report.caveats)

## Recommendation
One paragraph: partner or not? At what budget? Conditions?

## Raw summary
Followers / Following · posts analysed · avg ER% · like:comment · comments sampled
```

## Step 5: Report back

Verdict + score inline, the 2–3 biggest flags, one recommendation sentence, any caveats. Keep it short.

---

## Known limitation — follower sampling

Instagram follower lists aren't cheaply sampleable, so the **audience-quality** signal (bot followers) is skipped and surfaced as a caveat. IG detection therefore leans on engagement rate (vs follower count), comment quality, the like-to-comment ratio, and spikes. A pod/bot-inflated account typically shows a low ER against its follower count and a skewed like:comment ratio — both caught here.

## Error handling

- **Private account:** limited data; flagged in `caveats` — a private account pitching paid deals is itself a yellow flag.
- **Apify actor fails:** retry once after 30s; check apify.com/runs. Override the actor via `APIFY_IG_PROFILE_ACTOR` / `APIFY_IG_COMMENTS_ACTOR` env vars if your account uses different ones.
- **Small account:** low sample sizes reduce confidence — `caveats` will flag it.
