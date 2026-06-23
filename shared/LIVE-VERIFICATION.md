# Free mode — live channel verification (no API)

The Apify / YouTube-API scripts are the rigorous, deterministic path. But you don't always have keys or budget, and **even when you do, you should sanity-check the script's score against the channel's live growth curve.** This doc is the no-API method.

> **The core lesson:** verifying that the *person* is real is **not** the same as verifying that the *channel* is real and engaged. A genuine human can have a dormant, declining, or near-empty channel. Audit the channel, not the identity.

## Why a browser (WebFetch won't work)

Social networks and Social Blade sit behind Cloudflare / heavy JS, so a plain HTTP fetch returns an empty shell. Render the page in a real browser — e.g. **Claude in Chrome** — or just look yourself. Decline the cookie banner (Reject All).

## Per-platform sources

| Platform | Where to look |
|----------|---------------|
| YouTube | `https://socialblade.com/youtube/handle/<handle>` (or `/channel/<UC...>`) |
| TikTok | `https://socialblade.com/tiktok/user/<handle>` |
| Instagram | `https://socialblade.com/instagram/user/<handle>` |
| X / Twitter | **Social Blade discontinued Twitter** — open the live profile `https://x.com/<handle>` and read it directly |

## What to read

- **Account age / created date** — a years-old account with a long post history is hard to fake; a brand-new account with big numbers is not.
- **30-day follower delta** — the headline anti-bot signal. Smooth daily gains = organic. Overnight vertical jumps = bought. **Flat or negative growth = dormant/declining** (a real-but-dead channel).
- **Per-post / per-video engagement vs follower count** — likes & comments per post divided by followers. Compare to the platform's tier benchmark (TikTok runs high, Instagram lower).
- **Growth-curve shape** — steady ramp = healthy; **spike-then-collapse** = burst-buying; sawtooth with no engagement = manipulation.
- **Following-to-follower ratio** — a huge following count relative to followers suggests follow-for-follow farming.
- **Social Blade grade** — a quick directional read (it rewards growth, so a low grade alone isn't a bot verdict).

## Red flags this catches that "claimed numbers" hide

- Real identity, **dead channel**: flat/negative 30-day growth and near-zero recent engagement.
- A card's "big audience" that turns out to be a **near-empty handle** (e.g. a few followers, no posts).
- **Overnight follower jumps** with no matching rise in engagement.

## Verdict

Use the same 0–100 bands as the scripted audits. **If you can only eyeball the numbers and can't confirm a real, engaged audience, return ⚠️ Mixed (unverified) — never a pass.** This is a screen, not a forensic audit.

---

## When to escalate to a paid audience-quality tool

Social Blade shows **growth and engagement**, not the **% of fake followers**. For that — especially on Instagram and TikTok, where the scripts skip follower sampling — escalate to a dedicated audience-quality tool before committing real budget:

| Tool | Strength | Cost / access (2026) |
|------|----------|----------------------|
| **HypeAuditor** | Gold standard for fake-follower detection (ML, ~53 patterns); also covers X & Twitch | Opaque, ~$400+/mo, usually annual |
| **Modash** | 350M+ profiles (IG/TikTok/YT), clean data & UX | From ~$199/mo; **14-day free trial (20 profiles)**; API exists but enterprise (~$16k/yr) |
| **IQFluence / insightIQ** | Cheapest; has a **free fake-follower check** | Low monthly tiers (IG/TikTok/YT) |

**Honest notes (checked 2026-06):**
- None of these offers a cheap, usable API for automation — Modash's API is enterprise-priced; the others have no public self-serve API.
- **No off-the-shelf MCP connector exists** for any of them (the MCP registry has nothing in this category), so they can't be wired into an agent cheaply. The practical stack stays: **scripted audit (API/Apify) + free Social Blade cross-check in a browser**, with a paid tool's **free trial / free check** used by hand on finalists before money changes hands.
