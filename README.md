# Influencer Auditor Skills

Two Claude Cowork skills for vetting influencers before partnerships or sponsorships — detects bot inflation using engagement analysis, follower quality scoring, comment pattern detection, and spike analysis.

## Skills

### 🎬 `youtube-influencer-auditor`
Audits a YouTube channel for fake engagement and bot-inflated subscribers.

**Signals analysed:**
- Engagement rate vs. subscriber tier benchmarks
- Like-to-comment ratio anomalies
- View velocity spikes (>5× median with no viral context)
- Comment quality (generic %, emoji-only %, duplicates)
- Subscriber-to-view ratio
- Growth pattern anomalies

**Requirements:** YouTube Data API v3 key (free, 10K units/day)

**Output:** Authenticity Score (0–100) + verdict saved to Notion
| Score | Verdict |
|-------|---------|
| 80–100 | ✅ Looks Legit |
| 60–79 | ⚠️ Mixed Signals |
| 40–59 | 🚩 Suspicious |
| 0–39 | ❌ Likely Bot-Inflated |

---

### 🐦 `twitter-influencer-auditor`
Audits an X/Twitter account for fake followers and bought engagement.

**Signals analysed:**
- Engagement rate vs. follower tier benchmarks
- Follower quality (samples 200 followers, classifies suspicious/borderline/healthy)
- Following/follower ratio
- Engagement spike patterns (burst buying detection)
- Reply quality (generic %, emoji-only %, suspicious replier profiling)
- Account history signals (age vs. follower count, tweet velocity)

**Requirements:** Apify API token (~$0.20–0.50/run)

**Output:** Authenticity Score (0–100) + verdict saved to Notion

---

## Installation

Drop the skill folder into your Claude Cowork skills directory (`~/.claude/skills/`) or double-click the `.skill` file if using Cowork desktop.

## Trigger phrases

- "audit this YouTuber / this X account"
- "is this influencer legit / bot inflated"
- "vet this KOL"
- "should we partner with [creator]"
- Any YouTube or X/Twitter profile URL shared with intent to assess credibility
