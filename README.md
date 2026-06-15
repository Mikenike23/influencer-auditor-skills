# Influencer Auditor Skills

Four Claude / Cowork skills for vetting influencers and KOLs before partnerships, sponsorships, or paid promotions. Each one analyses an account for **bot inflation and fake engagement** and returns a **0–100 Authenticity Score** with a clear go/no-go verdict.

| Platform | Skill | Data source | Cost |
|----------|-------|-------------|------|
| 🐦 X / Twitter | `twitter-influencer-auditor` | Apify | ~$0.20–0.50 / run |
| 🎬 YouTube | `youtube-influencer-auditor` | YouTube Data API v3 | Free (10K units/day) |
| 🎵 TikTok | `tiktok-influencer-auditor` | Apify | ~$0.20–0.60 / run |
| 📸 Instagram | `instagram-influencer-auditor` | Apify | ~$0.20–0.60 / run |

## What's new in v2

- **Deterministic scoring engine** (`shared/scoring.py`) — the score is now computed in code, not interpreted by hand. The same account returns the same number every time, so results are reproducible and comparable across a whole roster. A copy ships inside each skill so every skill is self-contained.
- **Two new platforms** — TikTok and Instagram added alongside the original X and YouTube auditors.
- **Sharper detection** — added burst-buying detection (spike-then-collapse), posts/day automation signal, follow-to-follower inflation, default-avatar checks, and platform-correct engagement-rate benchmarks by audience tier.
- **Colleague-ready** — no personal vault or workspace dependencies; configure once with your own API keys.

## How it works

Each skill does the same three things:

1. **Fetch** profile + recent posts + a comment/reply sample (and, where cheap, a follower sample).
2. **Normalise** the platform's raw data into one shared `signals` schema.
3. **Score** deterministically across six weighted signals — engagement rate vs. tier benchmark, audience quality, comment/reply authenticity, engagement spikes, ratio anomalies, and account history — producing a score, verdict, ranked deductions, red/green flags, and caveats.

| Score | Verdict |
|-------|---------|
| 80–100 | ✅ Looks Legit — audience appears organic, low bot risk |
| 60–79 | ⚠️ Mixed Signals — some anomalies, proceed with caution / negotiate on CPE |
| 40–59 | 🚩 Suspicious — notable inflation signals, high risk for paid partnerships |
| 0–39 | ❌ Likely Bot-Inflated — strong evidence of artificial amplification, do not pay |

The engine is platform-aware: engagement-rate benchmarks and signal weights differ per platform (e.g. TikTok ER runs much higher than Instagram; YouTube has no public follower list, so that weight is reallocated to comment quality and spikes).

## Setup

1. **Install a skill** — drop its folder into your Claude/Cowork skills directory (`~/.claude/skills/`), or install the packaged `.skill` bundle from the Releases section.
2. **Add your API keys** — copy `.env.example` to `.env` and fill in what you need:
   - `YOUTUBE_API_KEY` — free from [Google Cloud Console](https://console.cloud.google.com) (enable *YouTube Data API v3*). Needed for YouTube only.
   - `APIFY_API_TOKEN` — from [apify.com](https://apify.com) → Settings → API & Integrations. Needed for X, TikTok, and Instagram. New accounts get $5 free credit.
3. **Run** — in Claude/Cowork, just say "audit this TikTok / YouTuber / X account / Instagram" and paste the profile URL. Or run a script directly:

```bash
# YouTube (free)
YOUTUBE_API_KEY=<key> python3 youtube-influencer-auditor/scripts/channel_auditor.py --channel "@mkbhd"

# X / Twitter, TikTok, Instagram (Apify, paid)
APIFY_API_TOKEN=<token> python3 twitter-influencer-auditor/scripts/account_auditor.py --handle "@handle"
APIFY_API_TOKEN=<token> python3 tiktok-influencer-auditor/scripts/tiktok_auditor.py --handle "@handle"
APIFY_API_TOKEN=<token> python3 instagram-influencer-auditor/scripts/instagram_auditor.py --handle "@handle"
```

Each script prints a JSON report (`profile`, `signals`, `report`) to stdout and progress to stderr.

## Repo layout

```
influencer-auditor-skills/
├── README.md
├── LICENSE                         # MIT
├── CHANGELOG.md
├── .env.example
├── shared/
│   └── scoring.py                  # canonical deterministic scoring engine (source of truth)
├── twitter-influencer-auditor/
│   ├── SKILL.md
│   └── scripts/{account_auditor.py, scoring.py}
├── youtube-influencer-auditor/
│   ├── SKILL.md
│   └── scripts/{channel_auditor.py, scoring.py}
├── tiktok-influencer-auditor/
│   ├── SKILL.md
│   └── scripts/{tiktok_auditor.py, scoring.py}
└── instagram-influencer-auditor/
    ├── SKILL.md
    └── scripts/{instagram_auditor.py, scoring.py}
```

`shared/scoring.py` is the canonical engine; an identical copy is vendored into each skill's `scripts/` so a skill works standalone. If you change the engine, sync the copies (`for d in *-influencer-auditor; do cp shared/scoring.py "$d/scripts/"; done`).

## Limitations & honest caveats

- **Apify actor IDs** can change or vary by account. Each script lets you override the actor via env vars (see each SKILL.md). Defaults point at widely-used public actors.
- **TikTok & Instagram follower sampling** isn't cheap, so the audience-quality signal is skipped there and surfaced as a caveat. Those audits lean on engagement rate, comment quality, ratios, and spikes — which catch most paid-engagement inflation.
- **A high score means "no inflation detected in the signals we could see,"** not a guarantee of authenticity. Always read the caveats. This is a screening tool, not a forensic audit.
- **Benchmarks are conservative industry ranges** (2024–25). Treat scores as a comparative screen across candidates, not an absolute truth.

## License

MIT — see [LICENSE](LICENSE). Use it, fork it, adapt it.
