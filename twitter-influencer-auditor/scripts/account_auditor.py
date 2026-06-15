#!/usr/bin/env python3
"""
Twitter / X Influencer Auditor — account_auditor.py  (v2.0)
Fetches profile, recent tweets, follower sample, and reply quality via Apify,
normalises them into the shared `signals` schema, and runs the deterministic
scoring engine (scoring.py) to emit a final Authenticity Report as JSON.

Usage:
  APIFY_API_TOKEN=<token> python3 account_auditor.py --handle "@handle_or_url" \
    [--max-tweets 100] [--max-follower-sample 200]

Configurable actors (env, optional):
  APIFY_TWITTER_SCRAPER_ACTOR   (default apify/twitter-scraper)
  APIFY_TWITTER_FOLLOWERS_ACTOR (default apidojo/twitter-user-scraper)
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
ACTOR_TWITTER_SCRAPER = os.environ.get("APIFY_TWITTER_SCRAPER_ACTOR", "apify~twitter-scraper")
ACTOR_TWITTER_FOLLOWERS = os.environ.get("APIFY_TWITTER_FOLLOWERS_ACTOR", "apidojo~twitter-user-scraper")

GENERIC_REPLY_PATTERNS = [
    r"^(great|awesome|amazing|love this|nice|cool|perfect|facts|fire|based|exactly|100%|fr|agree|so true|wow|wagmi|gm|lfg)\s*[!.]*$",
    r"^(👍|🔥|❤️|💯|🙌|👏|😍|🤩|💪|✅|⚡|🚀){1,5}$",
    r"^(thanks|thank you|thx|ty)\s*[!.]*$",
    r"^(this[!.]*|yes[!.]*|no[!.]*|lol[!.]*|lmao[!.]*|haha[!.]*){1}$",
]
GENERIC_RE = [re.compile(p, re.IGNORECASE) for p in GENERIC_REPLY_PATTERNS]


def is_generic_reply(text: str) -> bool:
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


def age_days_from(created_at: str):
    if not created_at:
        return None
    for parser in (
        lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")),
        lambda s: datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y"),
    ):
        try:
            return (datetime.now(timezone.utc) - parser(created_at)).days
        except Exception:
            continue
    return None


def normalise_handle(handle_or_url: str) -> str:
    h = handle_or_url.strip().rstrip("/")
    h = re.sub(r"https?://(www\.)?(twitter\.com|x\.com)/", "", h)
    return h.lstrip("@").split("/")[0]


def run_apify_actor(api_token: str, actor_id: str, run_input: dict, timeout_secs: int = 120) -> list:
    headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
    print(f"  → Starting Apify actor {actor_id}...", file=sys.stderr)
    r = requests.post(f"{APIFY_BASE}/acts/{actor_id}/runs", headers=headers, json=run_input, timeout=30)
    r.raise_for_status()
    run_id = r.json()["data"]["id"]
    dataset_id = r.json()["data"]["defaultDatasetId"]
    elapsed, poll = 0, 5
    status = "RUNNING"
    while elapsed < timeout_secs:
        time.sleep(poll); elapsed += poll
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


def fetch_user_timeline(api_token: str, handle: str, max_tweets: int) -> dict:
    run_input = {"startUrls": [{"url": f"https://x.com/{handle}"}], "maxItems": max_tweets,
                 "addUserInfo": True, "scrapeTweetReplies": False}
    items = run_apify_actor(api_token, ACTOR_TWITTER_SCRAPER, run_input)
    profile, tweets = {}, []
    for item in items:
        if not profile and item.get("author"):
            a = item["author"]
            profile = {
                "handle": a.get("userName", handle), "display_name": a.get("name", ""),
                "bio": a.get("description", "")[:300], "followers": safe_int(a.get("followers")),
                "following": safe_int(a.get("following")), "tweet_count": safe_int(a.get("statusesCount")),
                "created_at": a.get("createdAt", ""),
                "verified": a.get("isVerified", False) or a.get("isBlueVerified", False),
                "profile_image": bool(a.get("profileImageUrl")),
            }
        if item.get("type") == "tweet" or item.get("text"):
            tweets.append({
                "tweet_id": item.get("id", ""), "text": item.get("text", ""),
                "created_at": item.get("createdAt", ""), "likes": safe_int(item.get("likeCount")),
                "retweets": safe_int(item.get("retweetCount")), "replies": safe_int(item.get("replyCount")),
                "views": safe_int(item.get("viewCount")), "impressions": safe_int(item.get("impressionCount")),
                "is_retweet": item.get("isRetweet", False), "is_reply": item.get("isReply", False),
            })
    return {"profile": profile, "tweets": tweets}


def fetch_follower_sample(api_token: str, handle: str, max_followers: int) -> list:
    run_input = {"handle": handle, "maxFollowers": max_followers}
    try:
        items = run_apify_actor(api_token, ACTOR_TWITTER_FOLLOWERS, run_input, timeout_secs=90)
    except Exception as e:
        print(f"  ⚠ Follower fetch failed ({e}), skipping follower sample", file=sys.stderr)
        return []
    return [{
        "handle": i.get("userName", ""), "followers": safe_int(i.get("followers")),
        "following": safe_int(i.get("following")), "tweet_count": safe_int(i.get("statusesCount")),
        "created_at": i.get("createdAt", ""), "has_profile_image": bool(i.get("profileImageUrl")),
        "is_verified": i.get("isVerified", False),
    } for i in items]


def fetch_replies(api_token: str, tweet_ids: list, max_per_tweet: int = 15) -> list:
    all_replies = []
    for tid in tweet_ids[:5]:
        run_input = {"startUrls": [{"url": f"https://x.com/i/status/{tid}"}], "maxItems": max_per_tweet,
                     "scrapeTweetReplies": True}
        try:
            for item in run_apify_actor(api_token, ACTOR_TWITTER_SCRAPER, run_input, timeout_secs=60):
                if item.get("isReply") and item.get("inReplyToId") == tid:
                    a = item.get("author", {})
                    all_replies.append({
                        "text": item.get("text", ""), "author_followers": safe_int(a.get("followers")),
                        "author_following": safe_int(a.get("following")),
                        "author_tweet_count": safe_int(a.get("statusesCount")),
                        "author_created_at": a.get("createdAt", ""),
                        "author_has_image": bool(a.get("profileImageUrl")),
                    })
        except Exception as e:
            print(f"  ⚠ Reply fetch for tweet {tid} failed: {e}", file=sys.stderr)
        time.sleep(2)
    return all_replies


def classify_follower(f: dict) -> str:
    age = age_days_from(f.get("created_at", ""))
    is_new = age is not None and age < 30
    is_young = age is not None and 30 <= age < 90
    flags = sum([is_new, f["tweet_count"] < 5, not f["has_profile_image"],
                 f["following"] > 5000 and f["followers"] < 100])
    if flags >= 2 or (is_new and flags >= 1):
        return "suspicious"
    if is_young and flags >= 1:
        return "borderline"
    return "healthy"


def build_signals(profile, tweets, followers, replies):
    original = [t for t in tweets if not t["is_retweet"]] or tweets

    imp = [t["impressions"] for t in original if t["impressions"] > 0]
    views = [t["views"] for t in original if t["views"] > 0]
    fc = profile.get("followers", 0)
    if imp:
        bases, base_type = imp, "impressions"
    elif views:
        bases, base_type = views, "views"
    elif fc > 0:
        bases, base_type = [fc] * len(original), "followers"
    else:
        bases, base_type = [], "unknown"
    er_list = [(t["likes"] + t["retweets"] + t["replies"]) / bases[i] * 100
               for i, t in enumerate(original) if i < len(bases) and bases[i] > 0]
    avg_er = sum(er_list) / len(er_list) if er_list else None

    eng = [t["likes"] + t["retweets"] + t["replies"] for t in original]
    median_eng = statistics.median(eng) if len(eng) >= 3 else (sum(eng) / len(eng) if eng else 0)
    spikes = [e for e in eng if median_eng > 0 and e > 5 * median_eng]
    max_spike = round(max(eng) / median_eng, 1) if median_eng > 0 and eng else 0

    sustained_drop = False
    if len(eng) >= 9:
        third = len(eng) // 3
        newest_avg = sum(eng[:third]) / third
        oldest_avg = sum(eng[-third:]) / third
        if oldest_avg > 0 and max(eng) > 5 * median_eng and newest_avg < 0.4 * oldest_avg:
            sustained_drop = True

    fa = [classify_follower(f) for f in followers]
    audience = None
    if fa:
        audience = {"sample_size": len(fa), "suspicious_pct": round(fa.count("suspicious") / len(fa) * 100, 1)}

    comments = None
    if replies:
        texts = [r["text"] for r in replies]
        norm = [re.sub(r'\s+', ' ', t.lower().strip()) for t in texts]
        dupes = sum(v - 1 for v in Counter(norm).values() if v > 1)
        sus_auth = 0
        for r in replies:
            age = age_days_from(r.get("author_created_at", ""))
            flags = sum([age is not None and age < 30, r["author_tweet_count"] < 5,
                         not r["author_has_image"], r["author_following"] > 5000 and r["author_followers"] < 100])
            if flags >= 2:
                sus_auth += 1
        comments = {
            "sampled": len(replies),
            "generic_pct": round(sum(is_generic_reply(t) for t in texts) / len(texts) * 100, 1),
            "emoji_only_pct": round(sum(is_emoji_only(t) for t in texts) / len(texts) * 100, 1),
            "duplicate_pct": round(dupes / len(texts) * 100, 1),
            "suspicious_author_pct": round(sus_auth / len(replies) * 100, 1),
        }

    avg_likes = sum(t["likes"] for t in original) / len(original) if original else 0
    avg_replies = sum(t["replies"] for t in original) / len(original) if original else 0
    ltc = round(avg_likes / avg_replies, 1) if avg_replies > 0 else None
    ftf = round(profile["following"] / fc, 2) if fc > 0 else None

    age = age_days_from(profile.get("created_at", ""))
    ppd = round(profile["tweet_count"] / age, 1) if age and age > 0 else None

    return {
        "platform": "twitter", "tier_size": fc,
        "engagement": {"avg_er_pct": round(avg_er, 3) if avg_er is not None else None,
                       "base": base_type, "spike_count": len(spikes),
                       "max_spike_ratio": max_spike, "sustained_drop": sustained_drop},
        "ratios": {"like_to_comment": ltc, "following_to_follower": ftf, "sub_to_view_pct": None},
        "audience": audience, "comments": comments,
        "history": {"age_days": age, "posts_per_day": ppd,
                    "default_avatar": not profile.get("profile_image", True),
                    "verified": profile.get("verified", False)},
    }


def main():
    p = argparse.ArgumentParser(description="X/Twitter influencer bot-inflation auditor")
    p.add_argument("--handle", required=True)
    p.add_argument("--max-tweets", type=int, default=100)
    p.add_argument("--max-follower-sample", type=int, default=200)
    args = p.parse_args()

    token = os.environ.get("APIFY_API_TOKEN", "")
    if not token:
        print("ERROR: APIFY_API_TOKEN not set", file=sys.stderr); sys.exit(1)

    handle = normalise_handle(args.handle)
    print(f"[1/4] Fetching timeline for @{handle}...", file=sys.stderr)
    td = fetch_user_timeline(token, handle, args.max_tweets)
    profile, tweets = td["profile"], td["tweets"]

    print(f"[2/4] Sampling up to {args.max_follower_sample} followers...", file=sys.stderr)
    followers = fetch_follower_sample(token, handle, args.max_follower_sample)

    top_ids = sorted([t["tweet_id"] for t in tweets if t["tweet_id"] and not t["is_retweet"]],
                     key=lambda tid: next((t["likes"] + t["retweets"] + t["replies"]
                                           for t in tweets if t["tweet_id"] == tid), 0), reverse=True)[:5]
    print(f"[3/4] Fetching replies for top {len(top_ids)} tweets...", file=sys.stderr)
    replies = fetch_replies(token, top_ids)

    print("[4/4] Scoring...", file=sys.stderr)
    signals = build_signals(profile, tweets, followers, replies)
    report = score(signals)

    print(json.dumps({
        "audited_handle": f"@{handle}", "profile_url": f"https://x.com/{handle}",
        "profile": profile, "signals": signals, "report": report,
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
