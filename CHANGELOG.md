# Changelog

## v2.1 — 2026-06-23

### Added
- **Free mode — live channel verification (no API keys).** New `shared/LIVE-VERIFICATION.md`: how to vet a channel with just a browser (e.g. Claude in Chrome) via Social Blade — YouTube / TikTok / Instagram — reading account age, 30-day follower delta, per-post engagement, and growth-curve shape. Zero API cost, and doubles as a sanity-check on the scripted scores.
- **X/Twitter live-profile fallback.** Social Blade discontinued Twitter; the free path now reads the live `x.com` profile directly for follower count + recent engagement.
- **Paid audience-quality escalation guide.** When you need a true % of fake followers (especially IG/TikTok, where follower sampling is skipped), escalate to HypeAuditor / Modash / IQFluence — with honest pricing/API notes (no cheap API; no off-the-shelf MCP connector as of 2026-06).
- A **Free mode** callout in all four SKILL.md files.

### Changed
- Sharpened the core caveat across the skills: **a real *person* is not a real *channel*.** Dormant or declining channels (flat/negative 30-day growth, near-zero recent engagement) and "audiences" that turn out to be near-empty handles are fails even when identity checks out. If you can only eyeball the numbers, return ⚠️ Mixed (unverified), never a pass.
- Scoring engine (`shared/scoring.py`) unchanged — this release is methodology + docs only.

## v2.0 — 2026-06-15

### Added
- **TikTok auditor** (`tiktok-influencer-auditor`) — ER = (likes+comments+shares)/views, comment-quality and ratio analysis via Apify.
- **Instagram auditor** (`instagram-influencer-auditor`) — ER = (likes+comments)/followers, comment-quality and ratio analysis via Apify.
- **Deterministic scoring engine** (`shared/scoring.py`) — platform-aware, reproducible scoring shared by all four auditors. Vendored into each skill's `scripts/` for standalone installs.
- `.env.example`, `CHANGELOG.md`, and an MIT `LICENSE`.
- Configurable Apify actors via env vars on every Apify-backed auditor.

### Changed
- **Scoring moved from prompt to code.** v1 asked the model to apply the rubric by hand; the same account could score differently across runs. Scoring is now computed in `scoring.py` — same input, same score.
- **Sharper detection signals:** burst-buying detection (spike-then-sustained-collapse), posts/day automation signal, follow-to-follower inflation, default-avatar checks, and platform-correct ER benchmarks by audience tier.
- **YouTube weighting:** with no public follower list, the audience-quality weight is reallocated to comment quality + spikes.
- SKILL.md files rewritten to be **colleague-ready** — no personal vault/Notion dependencies; results go to chat and an optional saved file.

### Notes
- TikTok/Instagram follower-quality sampling is skipped (not cheaply available) and surfaced as a caveat; those audits lean on engagement, comments, ratios, and spikes.

## v1.0 — 2026-04-14
- Initial release: `twitter-influencer-auditor` and `youtube-influencer-auditor` with a rubric-based (model-interpreted) Authenticity Score.
