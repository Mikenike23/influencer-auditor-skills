---
name: youtube-influencer-auditor
description: "Audits a YouTube influencer's channel for bot inflation and fake engagement — analysing subscriber quality, engagement rate anomalies, comment authenticity, and growth patterns to produce a Authenticity Score (0–100) with a clear Verdict. Use this skill whenever you want to vet a YouTube creator before a partnership, sponsorship, or paid collaboration. Trigger on: 'audit this YouTuber', 'check if this channel is real', 'is this influencer legit', 'are their views real', 'bot check YouTube', 'vet this creator', 'is this channel bot inflated', 'check engagement on this YouTube channel', 'verify this influencer', 'should we partner with', or any YouTube channel URL shared with intent to assess creator credibility or audience quality."
---

# YouTube Influencer Auditor

## Purpose

Vet a YouTube influencer before spending money on a partnership or sponsored placement. The goal is fast signal: are this channel's numbers real, or bot-inflated? The output is a structured **Authenticity Report** saved to Notion with a clear numeric score and a go/no-go verdict — not a wall of raw stats.

---

## Step 0: Parse the input

Establish what was provided:
- A `youtube.com/@handle` or `youtube.com/channel/UC...` URL → **channel audit mode** (default)
- A single `youtube.com/watch?v=...` URL → **video audit mode** (scope to that video + channel-level checks)
- A name or handle without a URL → search for the channel first, confirm with the user before proceeding

If unclear, ask one quick question.

---

## Step 1: Get the YouTube Data API key

```bash
grep YOUTUBE_API_KEY ~/.env 2>/dev/null || grep YOUTUBE_API_KEY ./.env 2>/dev/null
```

If no key is found, request it:
> "I need a YouTube Data API v3 key to run the audit. You can grab one free in ~2 min at console.cloud.google.com → APIs & Services → Credentials → Create API key (enable YouTube Data API v3). Drop it here and I'll save it."

Once received:
```bash
echo "YOUTUBE_API_KEY=<key>" >> ~/.env
```

---

## Step 2: Install dependencies

```bash
pip install google-api-python-client youtube-transcript-api requests --break-system-packages -q
```

---

## Step 3: Run the audit script

The audit script lives at `scripts/channel_auditor.py` in this skill's directory. Find it:

```bash
find ~/.claude/skills/youtube-influencer-auditor/scripts/ -name "channel_auditor.py" 2>/dev/null | head -1
```

Run it:

```bash
YOUTUBE_API_KEY=<key> python3 <script_path>/channel_auditor.py \
  --channel "<url_or_handle>" \
  --max-videos 20 \
  --max-comments 100
```

The script outputs a JSON blob with all raw signals. Capture it:

```bash
YOUTUBE_API_KEY=<key> python3 <script_path>/channel_auditor.py \
  --channel "<url_or_handle>" \
  --max-videos 20 \
  --max-comments 100 \
  > /tmp/yt_audit_raw.json
```

---

## Step 4: Score the signals

Read `/tmp/yt_audit_raw.json` and compute the **Authenticity Score** (0–100) using this rubric. Each signal contributes to a deduction from 100.

### Signal checklist & deductions

**A. Engagement Rate** (weight: 25 pts)
- Calculate per-video: `(likes + comments) / views * 100`
- Industry benchmarks by subscriber tier:
  - <10K subs: expect 4–8% ER
  - 10K–100K: expect 2–5% ER
  - 100K–1M: expect 1–3% ER
  - 1M+: expect 0.5–2% ER
- If average ER is **below 50%** of the tier benchmark → deduct 15 pts
- If average ER is **below 25%** of the tier benchmark → deduct 25 pts (cap)

**B. Like-to-Comment Ratio** (weight: 15 pts)
- Healthy ratio: 20–100 likes per comment
- If ratio > 200:1 (lots of likes, almost no comments) → deduct 10 pts (like-buying signal)
- If ratio < 5:1 (comments far exceed likes) → deduct 5 pts (comment-buying signal)

**C. View Velocity Spikes** (weight: 20 pts)
- Look at view counts across the 20 most recent videos
- If any single video has >5× the channel's median views with no obvious reason (viral topic, collab, trending) → flag as spike
- 1 unexplained spike → deduct 5 pts
- 2+ unexplained spikes → deduct 15 pts
- Consistent spike pattern (every few months) → deduct 20 pts (cap)

**D. Comment Quality** (weight: 20 pts)
- Sample 50–100 comments across top 3 videos
- Bot-signal patterns to check:
  - Generic praise ("great video!", "amazing content!", "love this!" with nothing else) — if >40% of comments match this → deduct 10 pts
  - Short emoji-only comments (👍, 🔥, ❤️) — if >30% → deduct 5 pts
  - Duplicate or near-duplicate comments across videos — if >10% → deduct 10 pts
  - Commenter profile signals (new accounts, no profile pic, no videos) — check 20 random commenters; if >60% appear low-quality → deduct 10 pts
- Cap deduction at 20 pts

**E. Subscriber-to-View Ratio** (weight: 10 pts)
- A healthy channel typically gets 10–50% of its subscribers to watch each video
- If avg views / subscribers < 3% → deduct 10 pts (suggests bought subs or subscriber drop-off)
- If avg views / subscribers > 80% → note as unusually high (possibly a new viral channel — not a red flag on its own)

**F. Growth Pattern** (weight: 10 pts)
- If channel age and video count are available, estimate posting cadence
- Irregular posting with consistent high view counts → mild flag (deduct 5 pts)
- Channel created <6 months ago with 100K+ subs → flag for scrutiny (deduct 5 pts, note it)
- Flat subscriber growth despite viral videos → deduct 5 pts (suggests subs aren't converting)

### Authenticity Score

```
Score = 100 - sum of all deductions (minimum 0)
```

### Verdict mapping

| Score | Verdict |
|-------|---------|
| 80–100 | ✅ Looks Legit — audience appears organic, low bot risk |
| 60–79 | ⚠️ Mixed Signals — some anomalies, proceed with caution |
| 40–59 | 🚩 Suspicious — notable inflation signals, negotiate carefully or skip |
| 0–39 | ❌ Likely Bot-Inflated — strong evidence of artificial amplification, do not partner |

---

## Step 5: Save to Notion

Search for the right Notion location:
- If this is a partnership decision → look for a "Partnerships" or "Influencer Vetting" database in your Notion
- If none exists → create a new page in your main workspace titled "Influencer Audits"

Use this page structure:

```
# YouTube Audit: [Channel Name]
Date: [today]
URL: [channel URL]
Audited by: Claude

## Verdict
[EMOJI + one-line verdict with score]

## Authenticity Score: [X]/100

## Signal Breakdown
| Signal | Finding | Deduction |
|--------|---------|-----------|
| Engagement Rate | X% avg (benchmark: Y%) | -N pts |
| Like:Comment Ratio | X:1 | -N pts |
| View Spikes | [description] | -N pts |
| Comment Quality | [description] | -N pts |
| Sub:View Ratio | X% | -N pts |
| Growth Pattern | [description] | -N pts |

## Red Flags Detected
[Bullet list of the most suspicious specific findings — e.g. "Video from March 14 got 850K views vs channel median of 22K with no trending topic or collab"]

## Green Flags
[Bullet list of authentic signals — e.g. "Comments show consistent topic discussion, many repeat commenters across videos"]

## Recommendation
[One paragraph: should you partner with this creator? At what budget level? Any conditions?]

## Raw Data Summary
- Subscribers: X
- Total videos analysed: X
- Avg views/video: X
- Avg engagement rate: X%
- Comments sampled: X
- Channel age: X months/years
```

---

## Step 6: Report back

After saving to Notion:
1. Notion page link
2. The verdict + score inline in chat (bold, one line)
3. The 2–3 biggest red flags or green flags
4. One clear recommendation sentence

Keep it short. The detail is in Notion.

---

## Error handling

**No comments on videos:** Some channels disable comments. Note it — disabled comments on a monetised channel is itself a mild red flag (deduct 5 pts from Comment Quality). Proceed with remaining signals.

**Channel not found:** Try searching by name via YouTube search endpoint. If still missing, report back.

**API quota:** YouTube Data API gives 10K units/day free. This audit uses ~300–500 units. If quota is exhausted, note and suggest tomorrow or a second API key.

**Private videos:** Skip, note count. If >30% of a channel's videos are private, that's unusual — flag it.

**Very new channel (<10 videos):** Insufficient data for reliable audit. Proceed but caveat the score heavily — note sample size in the report.
