#!/usr/bin/env python3
"""
YouTube Influencer Auditor — channel_auditor.py  (v2.0)
Fetches channel stats, video performance, and comment quality via the YouTube
Data API, normalises them into the shared `signals` schema, and runs the
deterministic scoring engine (scoring.py) to emit a final report as JSON.

Usage:
  YOUTUBE_API_KEY=<key> python3 channel_auditor.py --channel "@handle_or_url" \
    [--max-videos 20] [--max-comments 100]
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
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    print("ERROR: google-api-python-client not installed. Run: pip install google-api-python-client --break-system-packages", file=sys.stderr)
    sys.exit(1)


GENERIC_COMMENT_PATTERNS = [
    r"^(great|awesome|amazing|excellent|fantastic|wonderful|love this|nice|cool|perfect|brilliant|incredible|superb|outstanding)\s*(video|content|work|channel|post)?[!.]*$",
    r"^(👍|🔥|❤️|💯|🙌|👏|😍|🤩|💪){1,5}$",
    r"^(thanks|thank you|thx|ty)[!.]*$",
    r"^(first|1st)[!.]*$",
    r"^(keep (it up|going)|keep up the (good|great) work)[!.]*$",
]
GENERIC_RE = [re.compile(p, re.IGNORECASE) for p in GENERIC_COMMENT_PATTERNS]


def is_generic_comment(text: str) -> bool:
    t = text.strip()
    return len(t) < 3 or any(r.match(t) for r in GENERIC_RE)


def is_emoji_only(text: str) -> bool:
    cleaned = re.sub(r'[\U0001F300-\U0001FAFF\U00002600-\U000027BF\s]+', '', text.strip())
    return len(cleaned) == 0 and len(text.strip()) > 0


def safe_int(val, default=0):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def age_days_from(iso: str):
    if not iso:
        return None
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(iso.replace("Z", "+00:00"))).days
    except Exception:
        return None


def get_youtube_client(api_key: str):
    return build("youtube", "v3", developerKey=api_key, cache_discovery=False)


def resolve_channel_id(youtube, channel_input: str):
    h = channel_input.strip().rstrip("/")
    h = re.sub(r"https?://(www\.)?youtube\.com/", "", h)
    if h.startswith("UC") and len(h) > 20:
        return h, f"https://youtube.com/channel/{h}"
    if h.startswith("channel/"):
        cid = h.replace("channel/", "")
        return cid, f"https://youtube.com/channel/{cid}"
    handle_clean = h[1:] if h.startswith("@") else h
    resp = youtube.channels().list(part="id,snippet", forHandle=handle_clean, maxResults=1).execute()
    items = resp.get("items", [])
    if not items:
        resp2 = youtube.search().list(part="snippet", q=handle_clean, type="channel", maxResults=1).execute()
        items2 = resp2.get("items", [])
        if not items2:
            raise ValueError(f"Channel not found: {channel_input}")
        cid = items2[0]["snippet"]["channelId"]
    else:
        cid = items[0]["id"]
    return cid, f"https://youtube.com/channel/{cid}"


def fetch_channel_metadata(youtube, channel_id: str) -> dict:
    resp = youtube.channels().list(part="snippet,statistics", id=channel_id).execute()
    items = resp.get("items", [])
    if not items:
        raise ValueError(f"No channel data for ID: {channel_id}")
    snip, stats = items[0].get("snippet", {}), items[0].get("statistics", {})
    return {
        "channel_id": channel_id, "channel_name": snip.get("title", ""),
        "description": snip.get("description", "")[:500], "published_at": snip.get("publishedAt", ""),
        "country": snip.get("country", ""), "subscriber_count": safe_int(stats.get("subscriberCount")),
        "view_count": safe_int(stats.get("viewCount")), "video_count": safe_int(stats.get("videoCount")),
        "hidden_subscriber_count": stats.get("hiddenSubscriberCount", False),
    }


def fetch_recent_videos(youtube, channel_id: str, max_results: int = 20) -> list:
    ch = youtube.channels().list(part="contentDetails", id=channel_id).execute()
    uploads = (ch["items"][0]["contentDetails"]["relatedPlaylists"].get("uploads", "") if ch.get("items") else "")
    if not uploads:
        return []
    video_ids, next_page = [], None
    while len(video_ids) < max_results:
        params = dict(part="contentDetails", playlistId=uploads, maxResults=50)
        if next_page:
            params["pageToken"] = next_page
        pl = youtube.playlistItems().list(**params).execute()
        for item in pl.get("items", []):
            video_ids.append(item["contentDetails"]["videoId"])
            if len(video_ids) >= max_results:
                break
        next_page = pl.get("nextPageToken")
        if not next_page:
            break
    videos = []
    for i in range(0, len(video_ids), 50):
        v_resp = youtube.videos().list(part="snippet,statistics,contentDetails", id=",".join(video_ids[i:i+50])).execute()
        for v in v_resp.get("items", []):
            snip, stats = v.get("snippet", {}), v.get("statistics", {})
            videos.append({
                "video_id": v["id"], "title": snip.get("title", ""), "published_at": snip.get("publishedAt", ""),
                "views": safe_int(stats.get("viewCount")), "likes": safe_int(stats.get("likeCount")),
                "comments_disabled": stats.get("commentCount") is None, "comment_count": safe_int(stats.get("commentCount")),
            })
    return videos


def fetch_comments(youtube, video_id: str, max_results: int = 50) -> list:
    comments = []
    try:
        resp = youtube.commentThreads().list(part="snippet", videoId=video_id, order="relevance",
                                              maxResults=min(max_results, 100), textFormat="plainText").execute()
        for item in resp.get("items", []):
            top = item["snippet"]["topLevelComment"]["snippet"]
            comments.append({"text": top.get("textDisplay", ""), "like_count": safe_int(top.get("likeCount"))})
    except HttpError as e:
        if "disabled" in str(e).lower() or "403" in str(e):
            pass
    return comments


def build_signals(metadata, videos, comments):
    subs = metadata["subscriber_count"]
    views = [v["views"] for v in videos if v["views"] > 0]
    avg_views = sum(views) / len(views) if views else 0
    avg_likes = sum(v["likes"] for v in videos) / len(videos) if videos else 0
    avg_comments = sum(v["comment_count"] for v in videos) / len(videos) if videos else 0

    er_list = [(v["likes"] + v["comment_count"]) / v["views"] * 100 for v in videos if v["views"] > 0]
    avg_er = sum(er_list) / len(er_list) if er_list else None

    median_views = statistics.median(views) if len(views) >= 3 else avg_views
    spikes = [v for v in videos if median_views > 0 and v["views"] > 5 * median_views]
    max_spike = round(max(views) / median_views, 1) if median_views > 0 and views else 0

    ltc = round(avg_likes / avg_comments, 1) if avg_comments > 0 else None
    svp = round(avg_views / subs * 100, 2) if subs > 0 else None

    cm = None
    if comments:
        texts = [c["text"] for c in comments]
        norm = [re.sub(r'\s+', ' ', t.lower().strip()) for t in texts]
        dupes = sum(x - 1 for x in Counter(norm).values() if x > 1)
        cm = {
            "sampled": len(texts),
            "generic_pct": round(sum(is_generic_comment(t) for t in texts) / len(texts) * 100, 1),
            "emoji_only_pct": round(sum(is_emoji_only(t) for t in texts) / len(texts) * 100, 1),
            "duplicate_pct": round(dupes / len(texts) * 100, 1),
            "suspicious_author_pct": 0,
        }

    age = age_days_from(metadata.get("published_at", ""))
    ppd = round(metadata["video_count"] / age, 2) if age and age > 0 else None

    return {
        "platform": "youtube", "tier_size": subs,
        "engagement": {"avg_er_pct": round(avg_er, 3) if avg_er is not None else None,
                       "base": "views", "spike_count": len(spikes),
                       "max_spike_ratio": max_spike, "sustained_drop": False},
        "ratios": {"like_to_comment": ltc, "following_to_follower": None, "sub_to_view_pct": svp},
        "audience": None,
        "comments": cm,
        "history": {"age_days": age, "posts_per_day": ppd, "default_avatar": False,
                    "verified": False},
    }


def main():
    p = argparse.ArgumentParser(description="YouTube channel bot-inflation auditor")
    p.add_argument("--channel", required=True)
    p.add_argument("--max-videos", type=int, default=20)
    p.add_argument("--max-comments", type=int, default=100)
    args = p.parse_args()

    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if not api_key:
        print("ERROR: YOUTUBE_API_KEY not set", file=sys.stderr); sys.exit(1)

    youtube = get_youtube_client(api_key)
    print(f"[1/4] Resolving channel: {args.channel}", file=sys.stderr)
    channel_id, channel_url = resolve_channel_id(youtube, args.channel)
    print(f"[2/4] Fetching channel metadata (ID: {channel_id})", file=sys.stderr)
    metadata = fetch_channel_metadata(youtube, channel_id)
    print(f"[3/4] Fetching up to {args.max_videos} recent videos", file=sys.stderr)
    videos = fetch_recent_videos(youtube, channel_id, max_results=args.max_videos)
    print("[4/4] Sampling comments from top 3 videos + scoring", file=sys.stderr)
    all_comments, per = [], max(30, args.max_comments // 3)
    for vid in sorted(videos, key=lambda v: v["views"], reverse=True)[:3]:
        all_comments.extend(fetch_comments(youtube, vid["video_id"], max_results=per))
        time.sleep(0.5)

    signals = build_signals(metadata, videos, all_comments)
    report = score(signals)

    print(json.dumps({
        "audited_channel": args.channel, "channel_url": channel_url,
        "metadata": metadata, "signals": signals, "report": report,
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
