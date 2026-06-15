---
name: youtube-influencer-auditor
description: "Audits a YouTube channel for bot inflation and fake engagement — analysing engagement-rate anomalies, comment authenticity, like-to-comment and subscriber-to-view ratios, and view spikes to produce a 0–100 Authenticity Score with a clear Verdict. Use whenever you need to vet a YouTube creator before a partnership, sponsorship, or paid collaboration. Trigger on: 'audit this YouTuber', 'is this channel real', 'are their views real', 'bot check YouTube', 'vet this creator', 'should we partner with', or any YouTube channel URL shared with intent to assess creator credibility."
---

# YouTube Influencer Auditor

## Purpose

Vet a YouTube influencer before spending money on a sponsored placement. Fast signal: are this channel's numbers real, or bot-inflated? Output is a structured **Authenticity Report** with a numeric score and a go/no-go verdict.

Scoring is **deterministic** — it lives in `scripts/scoring.py`, the shared engine used by all four platform auditors. YouTube has no public follower list, so its audience-quality weight is reallocated to comment quality + spikes. Same channel always returns the same score.

---

## Step 0: Parse the input

- `youtube.com/@handle` or `youtube.com/channel/UC...` → channel audit (default)
- A `watch?v=...` URL → resolve to its channel, then audit the channel
- A name with no URL → search, confirm with the user first

## Step 1: Get the YouTube Data API key

```bash
grep YOUTUBE_API_KEY .env 2>/dev/null | head -1
```

If missing, ask the user (console.cloud.google.com → APIs & Services → Credentials → create API key, enable **YouTube Data API v3** — free, 10K units/day), then:

```bash
echo "YOUTUBE_API_KEY=<key>" >> .env
```

This API is **free**, so there's no cost-confirmation step (unlike the X/TikTok/Instagram auditors which use paid Apify).

## Step 2: Install dependencies

```bash
pip install google-api-python-client --break-system-packages -q
```

## Step 3: Run the auditor

```bash
YOUTUBE_API_KEY=<key> python3 scripts/channel_auditor.py \
  --channel "<url_or_handle>" \
  --max-videos 20 \
  --max-comments 100 \
  > /tmp/yt_audit.json
```

Output JSON contains `metadata`, `signals`, and a fully computed `report` (`authenticity_score`, `verdict`, `deductions`, `red_flags`, `green_flags`, `caveats`).

## Step 4: Present the report

Read `/tmp/yt_audit.json` and present the `report` block. **Do not recompute the score.**

| Score | Verdict |
|-------|---------|
| 80–100 | ✅ Looks Legit |
| 60–79 | ⚠️ Mixed Signals |
| 40–59 | 🚩 Suspicious |
| 0–39 | ❌ Likely Bot-Inflated |

Report structure (chat, plus a saved markdown file or Notion page if wanted):

```
# YouTube Audit: [Channel Name]  —  [emoji] [verdict] ([score]/100)
URL: [channel URL]   ·   Date: [today]

## Signal breakdown
| Signal | Finding | Deduction |   (from report.deductions + green flags)

## Red flags        (report.red_flags)
## Green flags      (report.green_flags)
## Caveats          (report.caveats)

## Recommendation
One paragraph: partner or not? At what budget? Conditions?

## Raw summary
Subscribers · videos analysed · avg views · avg ER% · like:comment · sub:view% · comments sampled · channel age
```

## Step 5: Report back

Verdict + score inline, the 2–3 biggest flags, one recommendation sentence, any confidence-limiting caveats. Keep it short.

---

## Error handling

- **Comments disabled:** noted as a mild signal; the script proceeds on remaining signals.
- **Channel not found:** the script falls back to YouTube search; if still missing, tell the user.
- **API quota:** the free tier is 10K units/day; one audit uses ~300–500. If exhausted, suggest tomorrow or a second key.
- **Very new channel (<10 videos):** insufficient data — `caveats` will flag it; treat the score as low-confidence.
