#!/usr/bin/env python3
"""
Universal Authenticity Scoring Engine — scoring.py  (v2.0)

Deterministic, platform-aware bot-inflation scorer shared by all four auditors
(twitter / youtube / tiktok / instagram). Each auditor normalises its raw
platform data into the `signals` schema below and calls `score(signals)`.

Why deterministic? The v1 skills asked the model to apply the rubric by hand,
so two runs (or two colleagues) could score the same account differently. This
module makes the score reproducible: same input -> same number, every time.

signals schema
--------------
{
  "platform": "twitter"|"youtube"|"tiktok"|"instagram",
  "tier_size": int,                       # followers (X/TikTok/IG) or subscribers (YT)
  "engagement": {
      "avg_er_pct": float,                # average engagement rate, percent
      "base": "impressions"|"views"|"followers",
      "spike_count": int,                 # videos/posts with >5x median engagement
      "max_spike_ratio": float,           # largest single spike vs median
      "sustained_drop": bool,             # spike followed by sustained collapse
  },
  "ratios": {
      "like_to_comment": float|None,
      "following_to_follower": float|None,
      "sub_to_view_pct": float|None,
  },
  "audience": {                           # follower/subscriber sample; None if unavailable
      "sample_size": int,
      "suspicious_pct": float,
  } | None,
  "comments": {                           # comment / reply quality
      "sampled": int,
      "generic_pct": float,
      "emoji_only_pct": float,
      "duplicate_pct": float,
      "suspicious_author_pct": float,     # 0 if not measured
  } | None,
  "history": {
      "age_days": int|None,
      "posts_per_day": float|None,
      "default_avatar": bool,
      "verified": bool,
  },
}
"""

from __future__ import annotations


# ── engagement-rate benchmarks (low, high) by platform + audience tier ──────────
# Sources: published 2024-25 creator-marketing ER benchmarks, conservative ranges.
# ER definitions differ by platform (see each auditor) but the tiering logic is shared.

_ER_BENCHMARKS = {
    "twitter": [
        (5_000,    3.0, 8.0),
        (50_000,   1.0, 4.0),
        (500_000,  0.5, 2.0),
        (float("inf"), 0.1, 1.0),
    ],
    "youtube": [
        (10_000,   4.0, 8.0),
        (100_000,  2.0, 5.0),
        (1_000_000, 1.0, 3.0),
        (float("inf"), 0.5, 2.0),
    ],
    "tiktok": [
        (10_000,   8.0, 18.0),
        (100_000,  6.0, 12.0),
        (500_000,  4.0, 9.0),
        (1_000_000, 3.0, 7.0),
        (float("inf"), 2.0, 6.0),
    ],
    "instagram": [
        (10_000,   2.0, 6.0),
        (100_000,  1.5, 4.0),
        (500_000,  1.0, 3.0),
        (1_000_000, 0.8, 2.5),
        (float("inf"), 0.5, 1.5),
    ],
}

# Per-platform signal weights (must sum to 100). YouTube has no follower sample,
# so its audience-quality weight is reallocated to comment quality + spikes.
_WEIGHTS = {
    "twitter":   {"er": 25, "audience": 25, "comments": 15, "spikes": 15, "ratios": 10, "history": 10},
    "youtube":   {"er": 25, "audience": 0,  "comments": 25, "spikes": 20, "ratios": 15, "history": 15},
    "tiktok":    {"er": 25, "audience": 25, "comments": 15, "spikes": 15, "ratios": 10, "history": 10},
    "instagram": {"er": 25, "audience": 25, "comments": 15, "spikes": 15, "ratios": 10, "history": 10},
}

VERDICTS = [
    (80, "✅ Looks Legit", "audience appears organic, low bot risk"),
    (60, "⚠️ Mixed Signals", "some anomalies, proceed with caution / negotiate on CPE"),
    (40, "🚩 Suspicious", "notable inflation signals, high risk for paid partnerships"),
    (0,  "❌ Likely Bot-Inflated", "strong evidence of artificial amplification, do not pay"),
]


def _benchmark(platform: str, tier_size: int) -> tuple[float, float]:
    for ceiling, low, high in _ER_BENCHMARKS[platform]:
        if tier_size < ceiling:
            return low, high
    return _ER_BENCHMARKS[platform][-1][1], _ER_BENCHMARKS[platform][-1][2]


def _cap(points: float, weight: int) -> int:
    return int(min(points, weight))


def score(signals: dict) -> dict:
    platform = signals["platform"]
    if platform not in _WEIGHTS:
        raise ValueError(f"Unknown platform: {platform}")
    w = _WEIGHTS[platform]
    tier = max(signals.get("tier_size") or 0, 0)

    deductions: list[dict] = []
    red_flags: list[str] = []
    green_flags: list[str] = []
    caveats: list[str] = []

    def deduct(signal: str, pts: int, reason: str):
        if pts > 0:
            deductions.append({"signal": signal, "points": pts, "reason": reason})

    # ── A. Engagement rate ──────────────────────────────────────────────────
    eng = signals.get("engagement", {}) or {}
    er = eng.get("avg_er_pct")
    low, high = _benchmark(platform, tier)
    if er is None:
        caveats.append("Engagement rate unavailable — ER signal skipped.")
    else:
        if er < low * 0.25:
            deduct("Engagement Rate", _cap(w["er"], w["er"]),
                   f"ER {er:.2f}% is <25% of the {low:.1f}–{high:.1f}% benchmark for this tier")
            red_flags.append(f"Engagement rate {er:.2f}% is far below the {low:.1f}% floor for a {tier:,}-audience account")
        elif er < low * 0.5:
            deduct("Engagement Rate", _cap(15, w["er"]),
                   f"ER {er:.2f}% is <50% of the {low:.1f}–{high:.1f}% benchmark")
            red_flags.append(f"Engagement rate {er:.2f}% is well under the {low:.1f}% benchmark floor")
        elif er < low * 0.8:
            deduct("Engagement Rate", _cap(7, w["er"]),
                   f"ER {er:.2f}% is modestly below the {low:.1f}% benchmark floor")
        elif er > high * 3 and tier >= 100_000:
            deduct("Engagement Rate", _cap(8, w["er"]),
                   f"ER {er:.2f}% is >3x the {high:.1f}% ceiling on a large account (possible like-buying)")
            red_flags.append(f"Suspiciously high ER ({er:.2f}%) for a {tier:,}-audience account — possible bought engagement")
        else:
            green_flags.append(f"Engagement rate {er:.2f}% sits inside the healthy {low:.1f}–{high:.1f}% band for this tier")

    # ── B. Audience / follower quality ──────────────────────────────────────
    aud = signals.get("audience")
    if w["audience"] > 0:
        if not aud or not aud.get("sample_size"):
            caveats.append("No follower/audience sample available — audience-quality signal skipped.")
        else:
            sus = aud.get("suspicious_pct", 0)
            n = aud["sample_size"]
            if n < 50:
                caveats.append(f"Audience sample small ({n}) — quality estimate is low-confidence.")
            if sus > 30:
                deduct("Audience Quality", _cap(20, w["audience"]),
                       f"{sus:.0f}% of the {n}-account sample look bot-like")
                red_flags.append(f"{sus:.0f}% of sampled followers are bot-like (new, no posts, no avatar, or mass-following)")
            elif sus > 15:
                deduct("Audience Quality", _cap(12, w["audience"]), f"{sus:.0f}% of the sample look bot-like")
                red_flags.append(f"{sus:.0f}% of sampled followers look low-quality")
            elif sus > 5:
                deduct("Audience Quality", _cap(5, w["audience"]), f"{sus:.0f}% of the sample look bot-like")
            else:
                green_flags.append(f"Only {sus:.0f}% of sampled followers look suspicious — healthy audience")

    # ── C. Comment / reply quality ──────────────────────────────────────────
    cm = signals.get("comments")
    if cm and cm.get("sampled"):
        pts = 0.0
        reasons = []
        if cm.get("generic_pct", 0) > 40:
            pts += 10; reasons.append(f"{cm['generic_pct']:.0f}% generic praise")
        if cm.get("emoji_only_pct", 0) > 30:
            pts += 5; reasons.append(f"{cm['emoji_only_pct']:.0f}% emoji-only")
        if cm.get("duplicate_pct", 0) > 10:
            pts += 8; reasons.append(f"{cm['duplicate_pct']:.0f}% duplicate/near-duplicate")
        if cm.get("suspicious_author_pct", 0) > 50:
            pts += 10; reasons.append(f"{cm['suspicious_author_pct']:.0f}% from bot-like accounts")
        if pts > 0:
            deduct("Comment Quality", _cap(pts, w["comments"]), "; ".join(reasons))
            red_flags.append("Comment section shows bot patterns: " + "; ".join(reasons))
        else:
            green_flags.append(f"Comments look organic across {cm['sampled']} sampled (low generic/duplicate rates)")
    else:
        caveats.append("No comments/replies sampled — comment-quality signal skipped.")

    # ── D. Engagement spikes ────────────────────────────────────────────────
    spike_count = eng.get("spike_count", 0)
    if eng.get("sustained_drop"):
        deduct("Engagement Spikes", _cap(w["spikes"], w["spikes"]),
               "spike followed by sustained engagement collapse (burst-buying pattern)")
        red_flags.append("Burst-buying pattern: an engagement spike is followed by a sustained drop")
    elif spike_count >= 3:
        deduct("Engagement Spikes", _cap(int(w["spikes"] * 0.66), w["spikes"]),
               f"{spike_count} unexplained engagement spikes (>5x median)")
        red_flags.append(f"{spike_count} posts spike to >5x the median with no obvious viral cause")
    elif spike_count >= 1:
        deduct("Engagement Spikes", _cap(5, w["spikes"]),
               f"{spike_count} unexplained spike(s) >5x median")
    else:
        green_flags.append("Engagement is consistent — no unexplained spikes")

    # ── E. Ratio flags (platform-specific) ──────────────────────────────────
    ratios = signals.get("ratios", {}) or {}
    rpts = 0.0
    rreasons = []
    ltc = ratios.get("like_to_comment")
    if ltc is not None:
        if ltc > 200:
            rpts += 6; rreasons.append(f"like:comment {ltc:.0f}:1 (likes far exceed comments — like-buying)")
        elif ltc < 3 and ltc > 0:
            rpts += 4; rreasons.append(f"like:comment {ltc:.1f}:1 (comments exceed likes — comment-bots)")
    ftf = ratios.get("following_to_follower")
    if ftf is not None and ftf > 1.2:
        rpts += 4; rreasons.append("follows more accounts than follow back (mass-follow inflation)")
    svp = ratios.get("sub_to_view_pct")
    if svp is not None and svp < 3:
        rpts += 6; rreasons.append(f"only {svp:.1f}% of subscribers watch each video (bought subs / dead audience)")
    if rpts > 0:
        deduct("Ratio Flags", _cap(rpts, w["ratios"]), "; ".join(rreasons))
        for r in rreasons:
            red_flags.append("Ratio anomaly: " + r)

    # ── F. Account history ─────────────────────────────────────────────────
    hist = signals.get("history", {}) or {}
    hpts = 0.0
    hreasons = []
    age = hist.get("age_days")
    if age is not None and age < 365 and tier > 100_000 and not hist.get("verified"):
        hpts += 5; hreasons.append(f"account <1yr old with {tier:,} audience and not verified")
    ppd = hist.get("posts_per_day")
    if ppd is not None and ppd > 50:
        hpts += 5; hreasons.append(f"{ppd:.0f} posts/day average (automation signal)")
    if hist.get("default_avatar"):
        hpts += 3; hreasons.append("default / missing profile avatar")
    if hpts > 0:
        deduct("Account History", _cap(hpts, w["history"]), "; ".join(hreasons))
        for r in hreasons:
            red_flags.append("History flag: " + r)
    elif hist.get("verified"):
        green_flags.append("Account is verified")

    total_deduction = sum(d["points"] for d in deductions)
    final = max(0, 100 - total_deduction)

    verdict, verdict_emoji, verdict_note = "", "", ""
    for floor, label, note in VERDICTS:
        if final >= floor:
            verdict_emoji = label.split(" ", 1)[0]
            verdict = label.split(" ", 1)[1]
            verdict_note = note
            break

    return {
        "platform": platform,
        "authenticity_score": final,
        "verdict": verdict,
        "verdict_emoji": verdict_emoji,
        "verdict_note": verdict_note,
        "total_deduction": total_deduction,
        "deductions": deductions,
        "red_flags": red_flags,
        "green_flags": green_flags,
        "caveats": caveats,
        "benchmark_used": {"er_low": low, "er_high": high, "tier_size": tier},
        "weights": w,
    }
