#!/usr/bin/env python3
"""
TikTok Influencer Auditor — tiktok_auditor.py  (v2.0)
Fetches profile, recent videos, and comment quality via Apify, normalises into
the shared `signals` schema, and runs the deterministic scoring engine
(scoring.py) to emit a final Authenticity Report as JSON.

TikTok engagement rate is computed as (likes + comments + shares) / views, the
standard TikTok ER definition (views are public, so this is the honest base).

Usage:
  APIFY_API_TOKEN=<token> python3 tiktok_auditor.py --handle "@handle_or_url" \
    [--max-videos 30] [--max-comments 100]

Configurable actors (env, optional):
  APIFY_TIKTOK_SCRAPER_ACTOR    (default clockworks/tiktok-scraper)
  APIFY_TIKTOK_COMMENTS_ACTOR   (default clockworks/tiktok-comments-scraper)
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
ACTOR_TIKTOK = os.environ.get("APIFY_TIKTOK_SCRAPER_ACTOR", "clockworks~tiktok-scraper")
ACTOR_TIKTOK_COMMENTS = os.environ.get("APIFY_TIKTOK_COMMENTS_ACTOR", "clockworks~tiktok-comments-scraper")

GENERIC_COMMENT_PATTERNS = [
    r"^(great|awesome|amazing|love this|nice|cool|perfect|wow|omg|fire|so good|love it|best|goat|king|queen|slay|real|facts)\s*[!.]*$",
    r"^(👍|🔥|❤️|💯|🙌|👏|😍|🤩|💪|✅|😱|🥹|😭){1,5}$",
    r"^(first|1st)[!.]*$",
    r"^(follow me|check my page|f4f|sub4sub)[!.]*$",
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


def age_days_from(val):
    if not val:
        return None
    try:
        if isinstance(val, (int, float)) or str(val).isdigit():
            dt = datetime.fromtimestamp(int(val), tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return None


def normalise_handle(handle_or_url: str) -> str:
    h = handle_or_url.strip().rstrip("/")
    h = re.sub(r"https?://(www\.)?tiktok\.com/", "", h)
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


def fetch_profile_and_videos(api_token: str, handle: str, max_videos: int) -> dict:
    run_input = {"profiles": [handle], "resultsPerPage": max_videos,
                 "shouldDownloadVideos": False, "shouldDownloadCovers": False}
    items = run_apify_actor(api_token, ACTOR_TIKTOK, run_input)
    profile, videos = {}, []
    for it in items:
        a = it.get("authorMeta") or {}
        if not profile and a:
            profile = {
                "handle": a.get("name", handle), "display_name": a.get("nickName", ""),
                "bio": (a.get("signature") or "")[:300], "followers": safe_int(a.get("fans")),
                "following": safe_int(a.get("following")), "hearts": safe_int(a.get("heart")),
                "video_count": safe_int(a.get("video")), "verified": bool(a.get("verified")),
                "profile_image": bool(a.get("avatar")),
            }
        videos.append({
            "video_id": it.get("id", ""), "text": it.get("text", ""),
            "url": it.get("webVideoUrl", ""), "created_at": it.get("createTimeISO") or it.get("createTime"),
            "views": safe_int(it.get("playCount")), "likes": safe_int(it.get("diggCount")),
            "comments": safe_int(it.get("commentCount")), "shares": safe_int(it.get("shareCount")),
        })
    return {"profile": profile, "videos": videos}


def fetch_comments(api_token: str, video_urls: list, max_per: int) -> list:
    all_comments = []
    for url in video_urls[:3]:
        try:
            items = run_apify_actor(api_token, ACTOR_TIKTOK_COMMENTS,
                                    {"postURLs": [url], "maxItems": max_per}, timeout_secs=90)
            for it in items:
                all_comments.append({"text": it.get("text", "") or it.get("comment", "")})
        except Exception as e:
            print(f"  ⚠ Comment fetch for {url} failed: {e}", file=sys.stderr)
        time.sleep(2)
    return all_comments


def build_signals(profile, videos, comments):
    fc = profile.get("followers", 0)
    views = [v["views"] for v in videos if v["views"] > 0]
    er_list = [(v["likes"] + v["comments"] + v["shares"]) / v["views"] * 100 for v in videos if v["views"] > 0]
    avg_er = sum(er_list) / len(er_list) if er_list else None

    eng = [v["likes"] + v["comments"] + v["shares"] for v in videos]
    median_eng = statistics.median(eng) if len(eng) >= 3 else (sum(eng) / len(eng) if eng else 0)
    spikes = [e for e in eng if median_eng > 0 and e > 5 * median_eng]
    max_spike = round(max(eng) / median_eng, 1) if median_eng > 0 and eng else 0

    avg_likes = sum(v["likes"] for v in videos) / len(videos) if videos else 0
    avg_comments = sum(v["comments"] for v in videos) / len(videos) if videos else 0
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
        "platform": "tiktok", "tier_size": fc,
        "engagement": {"avg_er_pct": round(avg_er, 3) if avg_er is not None else None,
                       "base": "views", "spike_count": len(spikes),
                       "max_spike_ratio": max_spike, "sustained_drop": False},
        "ratios": {"like_to_comment": ltc, "following_to_follower": ftf, "sub_to_view_pct": None},
        "audience": None,  # TikTok follower lists aren't cheaply sampleable; see caveats
        "comments": cm,
        "history": {"age_days": None, "posts_per_day": None,
                    "default_avatar": not profile.get("profile_image", True),
                    "verified": profile.get("verified", False)},
    }


def main():
    p = argparse.ArgumentParser(description="TikTok influencer bot-inflation auditor")
    p.add_argument("--handle", required=True)
    p.add_argument("--max-videos", type=int, default=30)
    p.add_argument("--max-comments", type=int, default=100)
    args = p.parse_args()

    token = os.environ.get("APIFY_API_TOKEN", "")
    if not token:
        print("ERROR: APIFY_API_TOKEN not set", file=sys.stderr); sys.exit(1)

    handle = normalise_handle(args.handle)
    print(f"[1/3] Fetching profile + videos for @{handle}...", file=sys.stderr)
    pv = fetch_profile_and_videos(token, handle, args.max_videos)
    profile, videos = pv["profile"], pv["videos"]

    top_urls = [v["url"] for v in sorted(videos, key=lambda v: v["views"], reverse=True) if v["url"]][:3]
    print(f"[2/3] Fetching comments for top {len(top_urls)} videos...", file=sys.stderr)
    comments = fetch_comments(token, top_urls, max_per=max(30, args.max_comments // 3))

    print("[3/3] Scoring...", file=sys.stderr)
    signals = build_signals(profile, videos, comments)
    report = score(signals)

    print(json.dumps({
        "audited_handle": f"@{handle}", "profile_url": f"https://www.tiktok.com/@{handle}",
        "profile": profile, "signals": signals, "report": report,
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
