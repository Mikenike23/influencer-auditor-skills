#!/usr/bin/env python3
"""
Twitter / X Influencer Auditor — account_auditor.py
Fetches account profile, recent tweets, follower sample, and reply quality
for bot-inflation detection via Apify. Outputs a JSON blob for scoring.

Usage:
  APIFY_API_TOKEN=<token> python3 account_auditor.py --handle "@handle_or_url" \
    [--max-tweets 100] [--max-follower-sample 200]
"""

import argparse
import json
import os
import re
import sys
import time

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests --break-system-packages", file=sys.stderr)
    sys.exit(1)


# ── constants ─────────────────────────────────────────────────────────────────

APIFY_BASE = "https://api.apify.com/v2"
# Apify actor IDs (public, maintained actors)
ACTOR_TWITTER_SCRAPER = "61RPP7dywgiy0JPD0"   # apify/twitter-scraper
ACTOR_TWITTER_FOLLOWERS = "rVxBpOWkALQvvPBRE"  # apidojo/twitter-user-scraper (followers)

GENERIC_REPLY_PATTERNS = [
    r"^(great|awesome|amazing|love this|nice|cool|perfect|facts|fire|based|exactly|100%|fr|agree|so true)\s*[!.]*$",
    r"^(👍|🔥|❤️|💯|🙌|👏|😍|🤩|💪|✅|⚡){1,5}$",
    r"^(thanks|thank you|thx|ty)\s*[!.]*$",
    r"^(this[!.]*|yes[!.]*|no[!.]*|lol[!.]*|lmao[!.]*|haha[!.]*){1}$",
]
GENERIC_RE = [re.compile(p, re.IGNORECASE) for p in GENERIC_REPLY_PATTERNS]


def is_generic_reply(text: str) -> bool:
    t = text.strip()
    if len(t) < 2:
        return True
    return any(r.match(t) for r in GENERIC_RE)

def is_emoji_only(text: str) -> bool:
    cleaned = re.sub(r'[\U0001F300-\U0001FAFF\U00002600-\U000027BF\s]+', '', text.strip())
    return len(cleaned) == 0 and len(text.strip()) > 0

def safe_int(val, default=0):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default

def normalise_handle(handle_or_url: str) -> str:
    """Return clean Twitter handle without @ or URL prefix."""
    h = handle_or_url.strip().rstrip("/")
    h = re.sub(r"https?://(www\.)?(twitter\.com|x\.com)/", "", h)
    h = h.lstrip("@")
    # Remove any trailing path (e.g. /with_replies)
    h = h.split("/")[0]
    return h


# ── Apify helpers ─────────────────────────────────────────────────────────────

def run_apify_actor(api_token: str, actor_id: str, run_input: dict, timeout_secs: int = 120) -> list[dict]:
    """Run an Apify actor and return the dataset items."""
    headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}

    # Start the run
    start_url = f"{APIFY_BASE}/acts/{actor_id}/runs"
    print(f"  → Starting Apify actor {actor_id}...", file=sys.stderr)
    r = requests.post(start_url, headers=headers, json=run_input, timeout=30)
    r.raise_for_status()
    run_id = r.json()["data"]["id"]
    dataset_id = r.json()["data"]["defaultDatasetId"]

    # Poll until finished
    status_url = f"{APIFY_BASE}/actor-runs/{run_id}"
    elapsed = 0
    poll_interval = 5
    while elapsed < timeout_secs:
        time.sleep(poll_interval)
        elapsed += poll_interval
        sr = requests.get(status_url, headers=headers, timeout=15)
        sr.raise_for_status()
        status = sr.json()["data"]["status"]
        print(f"  → Run status: {status} ({elapsed}s)", file=sys.stderr)
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break

    if status != "SUCCEEDED":
        raise RuntimeError(f"Apify run {run_id} ended with status: {status}")

    # Fetch dataset items
    items_url = f"{APIFY_BASE}/datasets/{dataset_id}/items?format=json&clean=true"
    ir = requests.get(items_url, headers=headers, timeout=30)
    ir.raise_for_status()
    return ir.json()


# ── data fetching ─────────────────────────────────────────────────────────────

def fetch_user_timeline(api_token: str, handle: str, max_tweets: int) -> dict:
    """Fetch profile + recent tweets via Apify twitter-scraper."""
    run_input = {
        "startUrls": [{"url": f"https://x.com/{handle}"}],
        "maxItems": max_tweets,
        "addUserInfo": True,
        "scrapeTweetReplies": False,
    }
    items = run_apify_actor(api_token, ACTOR_TWITTER_SCRAPER, run_input)

    profile = {}
    tweets = []
    for item in items:
        # Profile info is usually on each tweet item
        if not profile and item.get("author"):
            author = item["author"]
            profile = {
                "handle": author.get("userName", handle),
                "display_name": author.get("name", ""),
                "bio": author.get("description", "")[:300],
                "followers": safe_int(author.get("followers")),
                "following": safe_int(author.get("following")),
                "tweet_count": safe_int(author.get("statusesCount")),
                "created_at": author.get("createdAt", ""),
                "verified": author.get("isVerified", False) or author.get("isBlueVerified", False),
                "profile_image": bool(author.get("profileImageUrl")),
            }

        if item.get("type") == "tweet" or item.get("text"):
            tweets.append({
                "tweet_id": item.get("id", ""),
                "text": item.get("text", ""),
                "created_at": item.get("createdAt", ""),
                "likes": safe_int(item.get("likeCount")),
                "retweets": safe_int(item.get("retweetCount")),
                "replies": safe_int(item.get("replyCount")),
                "views": safe_int(item.get("viewCount")),
                "impressions": safe_int(item.get("impressionCount")),
                "is_retweet": item.get("isRetweet", False),
                "is_reply": item.get("isReply", False),
                "has_media": bool(item.get("media")),
            })

    return {"profile": profile, "tweets": tweets}


def fetch_follower_sample(api_token: str, handle: str, max_followers: int) -> list[dict]:
    """Sample followers and check their profile quality."""
    # Use Apify's twitter follower scraper
    run_input = {
        "handle": handle,
        "maxFollowers": max_followers,
    }
    try:
        items = run_apify_actor(api_token, ACTOR_TWITTER_FOLLOWERS, run_input, timeout_secs=90)
    except Exception as e:
        print(f"  ⚠ Follower fetch failed ({e}), skipping follower sample", file=sys.stderr)
        return []

    followers = []
    for item in items:
        followers.append({
            "handle": item.get("userName", ""),
            "followers": safe_int(item.get("followers")),
            "following": safe_int(item.get("following")),
            "tweet_count": safe_int(item.get("statusesCount")),
            "created_at": item.get("createdAt", ""),
            "has_profile_image": bool(item.get("profileImageUrl")),
            "is_verified": item.get("isVerified", False),
            "bio": item.get("description", ""),
        })
    return followers


def fetch_replies(api_token: str, tweet_ids: list[str], max_per_tweet: int = 20) -> list[dict]:
    """Fetch replies to a list of tweet IDs."""
    all_replies = []
    for tid in tweet_ids[:5]:  # cap at 5 tweets
        run_input = {
            "startUrls": [{"url": f"https://x.com/i/status/{tid}"}],
            "maxItems": max_per_tweet,
            "scrapeTweetReplies": True,
        }
        try:
            items = run_apify_actor(api_token, ACTOR_TWITTER_SCRAPER, run_input, timeout_secs=60)
            for item in items:
                if item.get("isReply") and item.get("inReplyToId") == tid:
                    author = item.get("author", {})
                    all_replies.append({
                        "tweet_id": item.get("id", ""),
                        "text": item.get("text", ""),
                        "likes": safe_int(item.get("likeCount")),
                        "author_followers": safe_int(author.get("followers")),
                        "author_following": safe_int(author.get("following")),
                        "author_tweet_count": safe_int(author.get("statusesCount")),
                        "author_created_at": author.get("createdAt", ""),
                        "author_has_image": bool(author.get("profileImageUrl")),
                    })
        except Exception as e:
            print(f"  ⚠ Reply fetch for tweet {tid} failed: {e}", file=sys.stderr)
        time.sleep(2)
    return all_replies


# ── analysis ──────────────────────────────────────────────────────────────────

def classify_follower(f: dict) -> str:
    """Return 'suspicious', 'borderline', or 'healthy'."""
    from datetime import datetime, timezone

    # Parse account age
    age_days = None
    if f.get("created_at"):
        try:
            created = datetime.fromisoformat(f["created_at"].replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - created).days
        except Exception:
            pass

    is_new = age_days is not None and age_days < 30
    is_young = age_days is not None and 30 <= age_days < 90
    low_tweets = f["tweet_count"] < 5
    no_image = not f["has_profile_image"]
    mass_following = f["following"] > 5000 and f["followers"] < 100

    suspicious_signals = sum([is_new, low_tweets, no_image, mass_following])
    if suspicious_signals >= 2 or (is_new and suspicious_signals >= 1):
        return "suspicious"
    if is_young and suspicious_signals >= 1:
        return "borderline"
    return "healthy"


def analyse_followers(followers: list[dict]) -> dict:
    if not followers:
        return {"sample_size": 0, "suspicious_pct": 0, "borderline_pct": 0, "healthy_pct": 0}

    classifications = [classify_follower(f) for f in followers]
    total = len(classifications)
    suspicious = classifications.count("suspicious")
    borderline = classifications.count("borderline")
    healthy = classifications.count("healthy")

    return {
        "sample_size": total,
        "suspicious_count": suspicious,
        "borderline_count": borderline,
        "healthy_count": healthy,
        "suspicious_pct": round(suspicious / total * 100, 1),
        "borderline_pct": round(borderline / total * 100, 1),
        "healthy_pct": round(healthy / total * 100, 1),
    }


def analyse_tweets(tweets: list[dict], follower_count: int) -> dict:
    if not tweets:
        return {}

    original = [t for t in tweets if not t["is_retweet"]]
    if not original:
        original = tweets

    like_list = [t["likes"] for t in original]
    rt_list = [t["retweets"] for t in original]
    reply_list = [t["replies"] for t in original]
    view_list = [t["views"] for t in original if t["views"] > 0]
    impression_list = [t["impressions"] for t in original if t["impressions"] > 0]

    avg_likes = sum(like_list) / len(like_list) if like_list else 0
    avg_rts = sum(rt_list) / len(rt_list) if rt_list else 0
    avg_replies = sum(reply_list) / len(reply_list) if reply_list else 0

    # Engagement rate
    if impression_list:
        base_list = impression_list
        base_type = "impressions"
    elif view_list:
        base_list = view_list
        base_type = "views"
    elif follower_count > 0:
        base_list = [follower_count] * len(original)
        base_type = "followers"
    else:
        base_list = []
        base_type = "unknown"

    er_list = []
    for i, t in enumerate(original):
        if i < len(base_list) and base_list[i] > 0:
            er_list.append((t["likes"] + t["retweets"] + t["replies"]) / base_list[i] * 100)
    avg_er = sum(er_list) / len(er_list) if er_list else 0

    # Spike detection
    import statistics
    eng_list = [t["likes"] + t["retweets"] + t["replies"] for t in original]
    median_eng = statistics.median(eng_list) if len(eng_list) >= 3 else avg_likes
    spikes = []
    for t in original:
        total_eng = t["likes"] + t["retweets"] + t["replies"]
        if median_eng > 0 and total_eng > 5 * median_eng:
            spikes.append({
                "tweet_id": t["tweet_id"],
                "text_preview": t["text"][:100],
                "likes": t["likes"],
                "retweets": t["retweets"],
                "replies": t["replies"],
                "total_engagement": total_eng,
                "median_engagement": int(median_eng),
                "spike_ratio": round(total_eng / median_eng, 1),
            })

    # Following/follower ratio
    return {
        "original_tweets_analysed": len(original),
        "avg_likes": round(avg_likes, 1),
        "avg_retweets": round(avg_rts, 1),
        "avg_replies": round(avg_replies, 1),
        "avg_engagement_rate_pct": round(avg_er, 3),
        "engagement_rate_base": base_type,
        "median_engagement": int(median_eng),
        "spike_count": len(spikes),
        "engagement_spikes": spikes,
        "retweet_heavy": (avg_rts > avg_likes * 2),
    }


def analyse_replies(replies: list[dict]) -> dict:
    if not replies:
        return {"total_sampled": 0, "generic_pct": 0, "emoji_only_pct": 0, "suspicious_author_pct": 0, "duplicate_pct": 0}

    from collections import Counter
    from datetime import datetime, timezone

    total = len(replies)
    texts = [r["text"] for r in replies]
    generic = sum(1 for t in texts if is_generic_reply(t))
    emoji_only = sum(1 for t in texts if is_emoji_only(t))

    normalised = [re.sub(r'\s+', ' ', t.lower().strip()) for t in texts]
    counts = Counter(normalised)
    dupes = sum(v - 1 for v in counts.values() if v > 1)

    # Suspicious author check
    suspicious_authors = 0
    for r in replies:
        age_days = None
        if r.get("author_created_at"):
            try:
                created = datetime.fromisoformat(r["author_created_at"].replace("Z", "+00:00"))
                age_days = (datetime.now(timezone.utc) - created).days
            except Exception:
                pass
        flags = sum([
            age_days is not None and age_days < 30,
            r["author_tweet_count"] < 5,
            not r["author_has_image"],
            r["author_following"] > 5000 and r["author_followers"] < 100,
        ])
        if flags >= 2:
            suspicious_authors += 1

    return {
        "total_sampled": total,
        "generic_pct": round(generic / total * 100, 1),
        "emoji_only_pct": round(emoji_only / total * 100, 1),
        "duplicate_pct": round(dupes / total * 100, 1),
        "suspicious_author_pct": round(suspicious_authors / total * 100, 1),
    }


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="X/Twitter influencer bot-inflation auditor")
    parser.add_argument("--handle", required=True, help="Twitter handle, @handle, or x.com URL")
    parser.add_argument("--max-tweets", type=int, default=100, help="Max tweets to analyse (default 100)")
    parser.add_argument("--max-follower-sample", type=int, default=200, help="Max followers to sample (default 200)")
    args = parser.parse_args()

    api_token = os.environ.get("APIFY_API_TOKEN", "")
    if not api_token:
        print("ERROR: APIFY_API_TOKEN not set", file=sys.stderr)
        sys.exit(1)

    handle = normalise_handle(args.handle)
    print(f"[1/4] Fetching timeline for @{handle} (up to {args.max_tweets} tweets)...", file=sys.stderr)
    timeline_data = fetch_user_timeline(api_token, handle, args.max_tweets)
    profile = timeline_data["profile"]
    tweets = timeline_data["tweets"]

    print(f"[2/4] Sampling up to {args.max_follower_sample} followers...", file=sys.stderr)
    followers = fetch_follower_sample(api_token, handle, args.max_follower_sample)

    # Pick top 5 tweets by engagement for reply analysis
    top_tweet_ids = sorted(
        [t["tweet_id"] for t in tweets if t["tweet_id"] and not t["is_retweet"]],
        key=lambda tid: next((t["likes"] + t["retweets"] + t["replies"] for t in tweets if t["tweet_id"] == tid), 0),
        reverse=True
    )[:5]

    print(f"[3/4] Fetching replies for top {len(top_tweet_ids)} tweets...", file=sys.stderr)
    replies = fetch_replies(api_token, top_tweet_ids, max_per_tweet=15)

    print(f"[4/4] Running analysis...", file=sys.stderr)
    tweet_analysis = analyse_tweets(tweets, profile.get("followers", 0))
    follower_analysis = analyse_followers(followers)
    reply_analysis = analyse_replies(replies)

    result = {
        "audited_handle": f"@{handle}",
        "profile_url": f"https://x.com/{handle}",
        "profile": profile,
        "tweet_analysis": tweet_analysis,
        "follower_analysis": follower_analysis,
        "reply_analysis": reply_analysis,
        "raw_tweets_sample": tweets[:20],
        "raw_replies_sample": replies[:20],
    }

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
