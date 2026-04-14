#!/usr/bin/env python3
"""
YouTube Influencer Auditor — channel_auditor.py
Fetches channel stats, video performance, and comment quality signals
for bot-inflation detection. Outputs a JSON blob for scoring.

Usage:
  YOUTUBE_API_KEY=<key> python3 channel_auditor.py --channel "@handle_or_url" \
    [--max-videos 20] [--max-comments 100]
"""

import argparse
import json
import os
import re
import sys
import time
from collections import Counter

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    print("ERROR: google-api-python-client not installed. Run: pip install google-api-python-client --break-system-packages", file=sys.stderr)
    sys.exit(1)


# ── helpers ──────────────────────────────────────────────────────────────────

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
    if len(t) < 3:
        return True
    return any(r.match(t) for r in GENERIC_RE)

def is_emoji_only(text: str) -> bool:
    # Remove common emoji ranges + whitespace; if nothing remains, it's emoji-only
    cleaned = re.sub(r'[\U0001F300-\U0001FAFF\U00002600-\U000027BF\s]+', '', text.strip())
    return len(cleaned) == 0 and len(text.strip()) > 0

def safe_int(val, default=0):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


# ── YouTube API client ────────────────────────────────────────────────────────

def get_youtube_client(api_key: str):
    return build("youtube", "v3", developerKey=api_key, cache_discovery=False)


def resolve_channel_id(youtube, channel_input: str) -> tuple[str, str]:
    """Return (channel_id, channel_url) from a handle, URL, or channel ID."""
    # Strip URL cruft
    handle = channel_input.strip().rstrip("/")
    handle = re.sub(r"https?://(www\.)?youtube\.com/", "", handle)

    if handle.startswith("UC") and len(handle) > 20:
        # Looks like a raw channel ID
        return handle, f"https://youtube.com/channel/{handle}"

    if handle.startswith("@"):
        handle_clean = handle[1:]
    elif handle.startswith("channel/"):
        cid = handle.replace("channel/", "")
        return cid, f"https://youtube.com/channel/{cid}"
    else:
        handle_clean = handle

    # Resolve @handle via channels endpoint
    resp = youtube.channels().list(
        part="id,snippet",
        forHandle=handle_clean,
        maxResults=1,
    ).execute()

    items = resp.get("items", [])
    if not items:
        # Fallback: search
        resp2 = youtube.search().list(
            part="snippet",
            q=handle_clean,
            type="channel",
            maxResults=1,
        ).execute()
        items2 = resp2.get("items", [])
        if not items2:
            raise ValueError(f"Channel not found: {channel_input}")
        cid = items2[0]["snippet"]["channelId"]
    else:
        cid = items[0]["id"]

    return cid, f"https://youtube.com/channel/{cid}"


def fetch_channel_metadata(youtube, channel_id: str) -> dict:
    resp = youtube.channels().list(
        part="snippet,statistics,brandingSettings",
        id=channel_id,
    ).execute()
    items = resp.get("items", [])
    if not items:
        raise ValueError(f"No channel data for ID: {channel_id}")
    ch = items[0]
    snip = ch.get("snippet", {})
    stats = ch.get("statistics", {})
    return {
        "channel_id": channel_id,
        "channel_name": snip.get("title", ""),
        "description": snip.get("description", "")[:500],
        "published_at": snip.get("publishedAt", ""),
        "country": snip.get("country", ""),
        "subscriber_count": safe_int(stats.get("subscriberCount")),
        "view_count": safe_int(stats.get("viewCount")),
        "video_count": safe_int(stats.get("videoCount")),
        "hidden_subscriber_count": stats.get("hiddenSubscriberCount", False),
    }


def fetch_recent_videos(youtube, channel_id: str, max_results: int = 20) -> list[dict]:
    """Fetch recent uploads via the channel's uploads playlist."""
    # Get uploads playlist ID
    ch_resp = youtube.channels().list(
        part="contentDetails",
        id=channel_id,
    ).execute()
    uploads_playlist = (
        ch_resp["items"][0]["contentDetails"]["relatedPlaylists"].get("uploads", "")
        if ch_resp.get("items") else ""
    )
    if not uploads_playlist:
        return []

    # Fetch playlist items
    video_ids = []
    next_page = None
    while len(video_ids) < max_results:
        params = dict(part="contentDetails", playlistId=uploads_playlist, maxResults=50)
        if next_page:
            params["pageToken"] = next_page
        pl_resp = youtube.playlistItems().list(**params).execute()
        for item in pl_resp.get("items", []):
            video_ids.append(item["contentDetails"]["videoId"])
            if len(video_ids) >= max_results:
                break
        next_page = pl_resp.get("nextPageToken")
        if not next_page:
            break

    if not video_ids:
        return []

    # Batch fetch video stats (50 per request)
    videos = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        v_resp = youtube.videos().list(
            part="snippet,statistics,contentDetails",
            id=",".join(batch),
        ).execute()
        for v in v_resp.get("items", []):
            snip = v.get("snippet", {})
            stats = v.get("statistics", {})
            cd = v.get("contentDetails", {})
            videos.append({
                "video_id": v["id"],
                "title": snip.get("title", ""),
                "published_at": snip.get("publishedAt", ""),
                "tags": snip.get("tags", []),
                "duration": cd.get("duration", ""),
                "views": safe_int(stats.get("viewCount")),
                "likes": safe_int(stats.get("likeCount")),
                "comments_disabled": stats.get("commentCount") is None,
                "comment_count": safe_int(stats.get("commentCount")),
            })

    return videos


def fetch_comments(youtube, video_id: str, max_results: int = 50) -> list[dict]:
    """Fetch top-level comments for a video, sorted by relevance."""
    comments = []
    try:
        resp = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            order="relevance",
            maxResults=min(max_results, 100),
            textFormat="plainText",
        ).execute()
        for item in resp.get("items", []):
            top = item["snippet"]["topLevelComment"]["snippet"]
            comments.append({
                "author_channel_id": top.get("authorChannelId", {}).get("value", ""),
                "author_display_name": top.get("authorDisplayName", ""),
                "text": top.get("textDisplay", ""),
                "like_count": safe_int(top.get("likeCount")),
                "published_at": top.get("publishedAt", ""),
            })
    except HttpError as e:
        if "disabled" in str(e).lower() or "403" in str(e):
            pass  # Comments disabled
    return comments


# ── analysis ─────────────────────────────────────────────────────────────────

def analyse_comments(all_comments: list[dict]) -> dict:
    if not all_comments:
        return {
            "total_sampled": 0,
            "generic_pct": 0,
            "emoji_only_pct": 0,
            "duplicate_pct": 0,
            "comments_disabled_on_some": False,
        }

    total = len(all_comments)
    texts = [c["text"] for c in all_comments]
    generic = sum(1 for t in texts if is_generic_comment(t))
    emoji_only = sum(1 for t in texts if is_emoji_only(t))

    # Near-duplicate detection: normalise + count
    normalised = [re.sub(r'\s+', ' ', t.lower().strip()) for t in texts]
    counts = Counter(normalised)
    dupes = sum(v - 1 for v in counts.values() if v > 1)

    return {
        "total_sampled": total,
        "generic_pct": round(generic / total * 100, 1),
        "emoji_only_pct": round(emoji_only / total * 100, 1),
        "duplicate_pct": round(dupes / total * 100, 1),
    }


def analyse_engagement(videos: list[dict], subscriber_count: int) -> dict:
    if not videos:
        return {}

    view_list = [v["views"] for v in videos if v["views"] > 0]
    like_list = [v["likes"] for v in videos]
    comment_list = [v["comment_count"] for v in videos]

    avg_views = sum(view_list) / len(view_list) if view_list else 0
    avg_likes = sum(like_list) / len(like_list) if like_list else 0
    avg_comments = sum(comment_list) / len(comment_list) if comment_list else 0

    # Engagement rate (likes + comments) / views
    er_list = []
    for v in videos:
        if v["views"] > 0:
            er_list.append((v["likes"] + v["comment_count"]) / v["views"] * 100)
    avg_er = sum(er_list) / len(er_list) if er_list else 0

    # Like:comment ratio
    lc_ratio = avg_likes / avg_comments if avg_comments > 0 else 9999

    # Sub:view ratio
    sv_ratio = avg_views / subscriber_count * 100 if subscriber_count > 0 else 0

    # Spike detection: views > 5× median
    import statistics
    if len(view_list) >= 3:
        median_views = statistics.median(view_list)
    else:
        median_views = avg_views

    spikes = []
    for v in videos:
        if median_views > 0 and v["views"] > 5 * median_views:
            spikes.append({
                "video_id": v["video_id"],
                "title": v["title"],
                "views": v["views"],
                "median_views": int(median_views),
                "spike_ratio": round(v["views"] / median_views, 1),
            })

    # Comments disabled count
    comments_disabled = sum(1 for v in videos if v["comments_disabled"])

    return {
        "videos_analysed": len(videos),
        "avg_views": int(avg_views),
        "avg_likes": int(avg_likes),
        "avg_comments": int(avg_comments),
        "avg_engagement_rate_pct": round(avg_er, 2),
        "like_to_comment_ratio": round(lc_ratio, 1),
        "sub_to_view_ratio_pct": round(sv_ratio, 2),
        "median_views": int(median_views),
        "view_spikes": spikes,
        "spike_count": len(spikes),
        "comments_disabled_count": comments_disabled,
    }


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="YouTube channel bot-inflation auditor")
    parser.add_argument("--channel", required=True, help="Channel URL, @handle, or channel ID")
    parser.add_argument("--max-videos", type=int, default=20, help="Max videos to analyse (default 20)")
    parser.add_argument("--max-comments", type=int, default=100, help="Max comments to sample total (default 100)")
    args = parser.parse_args()

    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if not api_key:
        print("ERROR: YOUTUBE_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    youtube = get_youtube_client(api_key)

    print(f"[1/4] Resolving channel: {args.channel}", file=sys.stderr)
    channel_id, channel_url = resolve_channel_id(youtube, args.channel)

    print(f"[2/4] Fetching channel metadata (ID: {channel_id})", file=sys.stderr)
    metadata = fetch_channel_metadata(youtube, channel_id)

    print(f"[3/4] Fetching up to {args.max_videos} recent videos", file=sys.stderr)
    videos = fetch_recent_videos(youtube, channel_id, max_results=args.max_videos)

    print(f"[4/4] Sampling comments from top 3 videos", file=sys.stderr)
    all_comments = []
    per_video = max(30, args.max_comments // 3)
    top_videos = sorted(videos, key=lambda v: v["views"], reverse=True)[:3]
    for vid in top_videos:
        comments = fetch_comments(youtube, vid["video_id"], max_results=per_video)
        all_comments.extend(comments)
        time.sleep(0.5)  # gentle rate limiting

    engagement = analyse_engagement(videos, metadata["subscriber_count"])
    comment_analysis = analyse_comments(all_comments)

    result = {
        "audited_channel": args.channel,
        "channel_url": channel_url,
        "metadata": metadata,
        "engagement": engagement,
        "comment_analysis": comment_analysis,
        "raw_videos": videos,
        "raw_comments_sample": all_comments[:50],  # cap for output size
    }

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
