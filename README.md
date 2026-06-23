# Influencer Auditor Skills

Four Claude / Cowork skills for vetting influencers and KOLs before partnerships, sponsorships, or paid promotions. Each one analyses an account for **bot inflation and fake engagement** and returns a **0–100 Authenticity Score** with a clear go/no-go verdict.

| Platform | Skill | Data source | Cost |
|----------|-------|-------------|------|
| 🐦 X / Twitter | `twitter-influencer-auditor` | Apify | ~$0.20–0.50 / run |
| 🎬 YouTube | `youtube-influencer-auditor` | YouTube Data API v3 | Free (10K units/day) |
| 🎵 TikTok | `tiktok-influencer-auditor` | Apify | ~$0.20–0.60 / run |
| 📸 Instagram | `instagram-influencer-auditor` | Apify | ~$0.20–0.60 / run |

> **No keys, no budget?** There's also a **free, no-API mode**: verify the live channel in a browser via Social Blade. See [Free mode](#free-mode--no-api-keys-live-cross-check) below.

## What's new in v2.1

- **Free mode — live channel verification (no API keys).** A browser-based cross-check via Social Blade (YouTube/TikTok/Instagram) and the live profile for X. Reads account age, 30-day follower delta, per-post engagement, and growth-curve shape. Full method: [`shared/LIVE-VERIFICATION.md`](shared/LIVE-VERIFICATION.md).
- **Core caveat, sharpened: a real *person* is not a real *channel*.** Dormant/declining channels (flat or negative 30-day growth, near-zero recent engagement) and "audiences" that turn out to be near-empty handles are fails even when identity checks out.
- **Paid audience-quality escalation guide** — HypeAuditor / Modash / IQFluence for a true % of fake followers, with honest pricing/API notes (no cheap API; no off-the-shelf MCP connector as of 2026-06).

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

## Free mode — no API keys (live cross-check)

The scripts above are the rigorous path, but you don't always have keys or budget — and even when you do, it's worth sanity-checking the score against the channel's **live growth curve**. Plain HTTP fetches are blocked by Cloudflare/JS, so render the page in a browser (e.g. **Claude in Chrome**):

- **YouTube / TikTok / Instagram** → Social Blade: `socialblade.com/<platform>/user|handle/<name>`. Read account age, **30-day follower delta** (overnight jumps = bought), per-post engagement vs follower count, growth-curve shape, and the SB grade.
- **X / Twitter** → Social Blade discontinued Twitter, so open the **live profile** `x.com/<handle>` and read followers + recent-post engagement directly.

**The lesson behind this mode: a real *person* is not a real *channel*.** Catch real-but-dormant/declining accounts and "audiences" that are actually near-empty handles. If you can only eyeball the numbers, return ⚠️ Mixed (unverified), not a pass. Full method → [`shared/LIVE-VERIFICATION.md`](shared/LIVE-VERIFICATION.md).

## Escalating to a paid audience-quality tool

Social Blade shows **growth and engagement**, not the **% of fake followers**. For that — especially on Instagram/TikTok, where the scripts skip follower sampling — use a dedicated tool before committing budget: **HypeAuditor** (best fake-follower detection, also covers X), **Modash** (clean data; 14-day free trial), or **IQFluence/insightIQ** (cheapest; free fake-follower check). None has a cheap API or an MCP connector as of 2026-06, so use their free trials/checks by hand on finalists. Details in [`shared/LIVE-VERIFICATION.md`](shared/LIVE-VERIFICATION.md).

## Setup

1. **Install a skill** — drop its folder into your Claude/Cowork skills directory (`~/.claude/skills/`), or install the packaged `.skill` bundle from the Releases section.
2. **Add your API keys** — copy `.env.example` to `.env` and fill in what you need:
   - `YOUTUBE_API_KEY` — free from [Google Cloud Console](https://console.cloud.google.com) (enable *YouTube Data API v3*). Needed for YouTube only.
   - `APIFY_API_TOKEN` — from [apify.com](https://apify.com) → Settings → API & Integrations. Needed for X, TikTok, and Instagram. New accounts get $5 free credit.
   - *(No keys at all? Use [Free mode](#free-mode--no-api-keys-live-cross-check).)*
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
│   ├── scoring.py                  # canonical deterministic scoring engine (source of truth)
│   └── LIVE-VERIFICATION.md        # free, no-API browser method + paid-tool escalation
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

- **A real person is not a real channel.** Identity verification (the human exists, listings repeat their numbers) is not enough — always check the live channel's growth and engagement (see [Free mode](#free-mode--no-api-keys-live-cross-check)). Dormant/declining channels pass an identity check but fail an audience check.
- **Apify actor IDs** can change or vary by account. Each script lets you override the actor via env vars (see each SKILL.md). Defaults point at widely-used public actors.
- **TikTok & Instagram follower sampling** isn't cheap, so the audience-quality signal is skipped there and surfaced as a caveat. Those audits lean on engagement rate, comment quality, ratios, and spikes — which catch most paid-engagement inflation. For a true % of fake followers, escalate to a paid tool (see above).
- **No off-the-shelf MCP connector** exists for the paid audience-quality tools (checked the MCP registry, 2026-06), and none offers a cheap API — so the practical stack is scripted audit + free Social Blade cross-check, with paid tools used by hand on finalists.
- **A high score means "no inflation detected in the signals we could see,"** not a guarantee of authenticity. Always read the caveats. This is a screening tool, not a forensic audit.
- **Benchmarks are conservative industry ranges** (2024–25). Treat scores as a comparative screen across candidates, not an absolute truth.

## License

MIT — see [LICENSE](LICENSE). Use it, fork it, adapt it.
