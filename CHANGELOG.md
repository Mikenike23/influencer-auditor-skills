# Changelog

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
