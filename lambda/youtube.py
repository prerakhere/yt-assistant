"""
YouTube module — fetches subscriptions and new videos (last 24h).

Uses:
- google-api-python-client for YouTube Data API v3 (subscriptions, playlist items)
- youtube-transcript-api for free transcript fetching (no quota cost)
"""

from datetime import datetime, timedelta, timezone

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi

# Max transcript length (in characters) to send to Bedrock — keeps cost low
MAX_TRANSCRIPT_CHARS = 8000


def _get_youtube_client(refresh_token, client_id, client_secret):
    """Build an authenticated YouTube API client using a refresh token."""
    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("youtube", "v3", credentials=credentials)


def _get_subscribed_channel_ids(youtube):
    """Get all channel IDs you're subscribed to."""
    channel_ids = []
    MAX_PAGES = 20  # Cap: 20 pages × 50 = 1000 subs max
    pages = 0
    request = youtube.subscriptions().list(
        part="snippet", mine=True, maxResults=50
    )
    while request and pages < MAX_PAGES:
        response = request.execute()
        for item in response["items"]:
            channel_ids.append({
                "id": item["snippet"]["resourceId"]["channelId"],
                "title": item["snippet"]["title"],
            })
        pages += 1
        request = youtube.subscriptions().list_next(request, response)
    return channel_ids


def _get_recent_videos(youtube, channels, since):
    """Get videos published after `since` from each channel's uploads playlist."""
    videos = []
    for ch in channels:
        uploads_id = "UU" + ch["id"][2:]
        try:
            response = youtube.playlistItems().list(
                part="snippet",
                playlistId=uploads_id,
                maxResults=5,
            ).execute()
        except Exception:
            continue

        for item in response.get("items", []):
            published = item["snippet"]["publishedAt"]
            pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            if pub_dt >= since:
                videos.append({
                    "video_id": item["snippet"]["resourceId"]["videoId"],
                    "title": item["snippet"]["title"],
                    "channel": ch["title"],
                    "description": item["snippet"].get("description", ""),
                    "published_at": pub_dt,
                })
    return videos


def _get_recent_videos_rss(channels, since):
    """Get videos published after `since` using RSS feeds (fast, no quota)."""
    import feedparser
    from concurrent.futures import ThreadPoolExecutor

    def fetch_feed(ch):
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={ch['id']}"
        try:
            feed = feedparser.parse(url)
        except Exception:
            return []

        results = []
        for entry in feed.entries:
            pub_dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            if pub_dt >= since:
                results.append({
                    "video_id": entry.yt_videoid,
                    "title": entry.title,
                    "channel": ch["title"],
                    "description": entry.get("summary", ""),
                    "published_at": pub_dt,
                })
        return results

    videos = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        for result in executor.map(fetch_feed, channels):
            videos.extend(result)

    return videos


def _get_transcript(video_id):
    """Fetch video transcript. Returns None if unavailable."""
    try:
        segments = YouTubeTranscriptApi.get_transcript(
            video_id, languages=["en", "hi", "en-IN"]
        )
        full_text = " ".join(s["text"] for s in segments)
        return full_text[:MAX_TRANSCRIPT_CHARS]
    except Exception:
        return None


def get_new_videos(refresh_token, client_id, client_secret, use_rss=False):
    """
    Main function called by handler.

    Args:
        use_rss: If True, uses RSS feeds (fast). If False, uses YouTube API (current).

    Returns list of dicts:
      [{"video_id", "title", "channel", "transcript_or_desc"}, ...]
    """
    youtube = _get_youtube_client(refresh_token, client_id, client_secret)

    # Get all subscriptions (always uses API — needed for channel IDs)
    channels = _get_subscribed_channel_ids(youtube)

    # Get videos from last 24 hours
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    if use_rss:
        videos = _get_recent_videos_rss(channels, since)
    else:
        videos = _get_recent_videos(youtube, channels, since)

    # Filter out Shorts (videos under 60 seconds)
    videos = _filter_shorts(videos)

    # Sort by newest first
    videos.sort(key=lambda v: v["published_at"], reverse=True)

    # Fetch transcripts in parallel (free, no API quota)
    from concurrent.futures import ThreadPoolExecutor

    def fetch_transcript(video):
        transcript = _get_transcript(video["video_id"])
        video["transcript_or_desc"] = transcript or video["description"] or video["title"]

    with ThreadPoolExecutor(max_workers=10) as executor:
        executor.map(fetch_transcript, videos)

    return videos


def _filter_shorts(videos):
    """Remove videos with #shorts in the title."""
    return [v for v in videos if "#shorts" not in v["title"].lower()]
