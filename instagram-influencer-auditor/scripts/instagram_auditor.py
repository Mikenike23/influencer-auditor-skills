#!/usr/bin/env python3
"""
Instagram Influencer Auditor — instagram_auditor.py  (v2.0)
Fetches profile, recent posts, and comment quality via Apify, normalises into
the shared `signals` schema, and runs the deterministic scoring engine
(scoring.py) to emit a final Authenticity Report as JSON.

Instagram engagement rate is computed as (likes + comments) / followers, the
standard public-ER definition (impressions are private to the account owner).

Usage:
  APIFY_API_TOKEN=<token> python3 instagram_auditor.py --handle "@handle_or_url" \
    [--max-posts 24] [--max-comments 100]

Configurable actors (env, optional):
  APIFY_IG_PROFILE_ACTOR    (default apify/instagram-profile-scraper)
  APIFY_IG_COMMENTS_ACTOR   (default apify/instagram-comment-scraper)
"""

import argparse
import json
import os
import re
import statistics
import sys
import time
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from scoring import score
except ImportError:
    print("ERROR: scoring.py not found next to this script.", file=sys.stderr)
    sys.exit(1)

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests --break-system-packages", file=sys.stderr)
    sys.exit(1)


APIFY_BASE = "https://api.apify.com/v2"
ACTOR_IG_PROFILE = os.environ.get("APIFY_IG_PROFILE_ACTOR", "apify~instagram-profile-scraper")
ACTOR_IG_COMMENTS = os.environ.get("APIFY_IG_COMMENTS_ACTOR", "apify~instagram-comment-scraper")

GENERIC_COMMENT_PATTERNS = [
    r"^(great|awesome|amazing|love this|nice|cool|perfect|wow|omg|gorgeous|beautiful|stunning|so good|love it|best|goals|queen|king|slay)\s*[!.]*$",
    r"^(👍|🔥|❤️|💯|🙌|👏|😍|🤩|💪|✅|😱|🥰|😘){1,5}$",
    r"^(follow me|check my page|dm me|f4f|l4l|nice page|great content)[!.]*$",
]
GENERIC_RE = [re.compile(p, re.IGNORECASE) for p in GENERIC_COMMENT_PATTERNS]


def is_generic_comment(text: str) -> bool:
    t = text.strip()
    return len(t) < 2 or any(r.match(t) for r in GENERIC_RE)


def is_emoji_only(text: str) -> bool:
    cleaned = re.sub(r'[\U0001F300-\U0001FAFF\U00002600-\U000027BF\s]+', '', text.strip())
    return len(cleaned) == 0 and len(text.strip()) > 0


def safe_int(val, default=0):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def normalise_handle(handle_or_url: str) -> str:
    h = handle_or_url.strip().rstrip("/")
    h = re.sub(r"https?://(www\.)?instagram\.com/", "", h)
    return h.lstrip("@").split("/")[0].split("?")[0]


def run_apify_actor(api_token: str, actor_id: str, run_input: dict, timeout_secs: int = 150) -> list:
    headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
    print(f"  → Starting Apify actor {actor_id}...", file=sys.stderr)
    r = requests.post(f"{APIFY_BASE}/acts/{actor_id}/runs", headers=headers, json=run_input, timeout=30)
    r.raise_for_status()
    run_id = r.json()["data"]["id"]
    dataset_id = r.json()["data"]["defaultDatasetId"]
    elapsed, status = 0, "RUNNING"
    while elapsed < timeout_secs:
        time.sleep(5); elapsed += 5
        sr = requests.get(f"{APIFY_BASE}/actor-runs/{run_id}", headers=headers, timeout=15)
        sr.raise_for_status()
        status = sr.json()["data"]["status"]
        print(f"  → Run status: {status} ({elapsed}s)", file=sys.stderr)
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break
    if status != "SUCCEEDED":
        raise RuntimeError(f"Apify run {run_id} ended with status: {status}")
    ir = requests.get(f"{APIFY_BASE}/datasets/{dataset_id}/items?format=json&clean=true", headers=headers, timeout=30)
    ir.raise_for_status()
    return ir.json()


def fetch_profile_and_posts(api_token: str, handle: str, max_posts: int) -> dict:
    items = run_apify_actor(api_token, ACTOR_IG_PROFILE,
                            {"usernames": [handle], "resultsLimit": max_posts})
    if not items:
        return {"profile": {}, "posts": []}
    it = items[0]
    profile = {
        "handle": it.get("username", handle), "display_name": it.get("fullName", ""),
        "bio": (it.get("biography") or "")[:300], "followers": safe_int(it.get("followersCount")),
        "following": safe_int(it.get("followsCount")), "post_count": safe_int(it.get("postsCount")),
        "verified": bool(it.get("verified")), "profile_image": bool(it.get("profilePicUrl")),
        "is_private": bool(it.get("private")),
    }
    posts = []
    for pst in (it.get("latestPosts") or [])[:max_posts]:
        posts.append({
            "post_id": pst.get("id", ""), "url": pst.get("url", ""),
            "caption": (pst.get("caption") or "")[:200], "timestamp": pst.get("timestamp", ""),
            "likes": safe_int(pst.get("likesCount")), "comments": safe_int(pst.get("commentsCount")),
        })
    return {"profile": profile, "posts": posts}


def fetch_comments(api_token: str, post_urls: list, max_per: int) -> list:
    all_comments = []
    for url in post_urls[:3]:
        try:
            items = run_apify_actor(api_token, ACTOR_IG_COMMENTS,
                                    {"directUrls": [url], "resultsLimit": max_per}, timeout_secs=90)
            for it in items:
                all_comments.append({"text": it.get("text", "")})
        except Exception as e:
            print(f"  ⚠ Comment fetch for {url} failed: {e}", file=sys.stderr)
        time.sleep(2)
    return all_comments


def build_signals(profile, posts, comments):
    fc = profile.get("followers", 0)
    er_list = [(p["likes"] + p["comments"]) / fc * 100 for p in posts if fc > 0]
    avg_er = sum(er_list) / len(er_list) if er_list else None

    eng = [p["likes"] + p["comments"] for p in posts]
    median_eng = statistics.median(eng) if len(eng) >= 3 else (sum(eng) / len(eng) if eng else 0)
    spikes = [e for e in eng if median_eng > 0 and e > 5 * median_eng]
    max_spike = round(max(eng) / median_eng, 1) if median_eng > 0 and eng else 0

    avg_likes = sum(p["likes"] for p in posts) / len(posts) if posts else 0
    avg_comments = sum(p["comments"] for p in posts) / len(posts) if posts else 0
    ltc = round(avg_likes / avg_comments, 1) if avg_comments > 0 else None
    ftf = round(profile.get("following", 0) / fc, 2) if fc > 0 else None

    cm = None
    if comments:
        texts = [c["text"] for c in comments if c["text"]]
        if texts:
            norm = [re.sub(r'\s+', ' ', t.lower().strip()) for t in texts]
            dupes = sum(x - 1 for x in Counter(norm).values() if x > 1)
            cm = {
                "sampled": len(texts),
                "generic_pct": round(sum(is_generic_comment(t) for t in texts) / len(texts) * 100, 1),
                "emoji_only_pct": round(sum(is_emoji_only(t) for t in texts) / len(texts) * 100, 1),
                "duplicate_pct": round(dupes / len(texts) * 100, 1),
                "suspicious_author_pct": 0,
            }

    return {
        "platform": "instagram", "tier_size": fc,
        "engagement": {"avg_er_pct": round(avg_er, 3) if avg_er is not None else None,
                       "base": "followers", "spike_count": len(spikes),
                       "max_spike_ratio": max_spike, "sustained_drop": False},
        "ratios": {"like_to_comment": ltc, "following_to_follower": ftf, "sub_to_view_pct": None},
        "audience": None,  # IG follower lists aren't cheaply sampleable; see caveats
        "comments": cm,
        "history": {"age_days": None, "posts_per_day": None,
                    "default_avatar": not profile.get("profile_image", True),
                    "verified": profile.get("verified", False)},
    }


def main():
    p = argparse.ArgumentParser(description="Instagram influencer bot-inflation auditor")
    p.add_argument("--handle", required=True)
    p.add_argument("--max-posts", type=int, default=24)
    p.add_argument("--max-comments", type=int, default=100)
    args = p.parse_args()

    token = os.environ.get("APIFY_API_TOKEN", "")
    if not token:
        print("ERROR: APIFY_API_TOKEN not set", file=sys.stderr); sys.exit(1)

    handle = normalise_handle(args.handle)
    print(f"[1/3] Fetching profile + posts for @{handle}...", file=sys.stderr)
    pp = fetch_profile_and_posts(token, handle, args.max_posts)
    profile, posts = pp["profile"], pp["posts"]

    if profile.get("is_private"):
        print("  ⚠ Account is private — limited data available.", file=sys.stderr)

    top_urls = [p["url"] for p in sorted(posts, key=lambda p: p["likes"] + p["comments"], reverse=True) if p["url"]][:3]
    print(f"[2/3] Fetching comments for top {len(top_urls)} posts...", file=sys.stderr)
    comments = fetch_comments(token, top_urls, max_per=max(30, args.max_comments // 3))

    print("[3/3] Scoring...", file=sys.stderr)
    signals = build_signals(profile, posts, comments)
    report = score(signals)
    if profile.get("is_private"):
        report["caveats"].append("Account is private — a private account pitching paid partnerships is itself a yellow flag.")

    print(json.dumps({
        "audited_handle": f"@{handle}", "profile_url": f"https://www.instagram.com/{handle}",
        "profile": profile, "signals": signals, "report": report,
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
