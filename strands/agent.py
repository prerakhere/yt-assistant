"""Strands agent for YT Assistant — replaces OpenClaw container."""

import os
import json
import logging
from datetime import datetime, timezone, timedelta

import boto3
from strands import Agent, tool
from strands.models.bedrock import BedrockModel
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)

# --- Config ---
TABLE_NAME = os.environ.get("VIDEOS_TABLE", "yt-digest-videos")
REGION = os.environ.get("AWS_REGION", "ap-south-1")
MODEL_ID = os.environ.get("MODEL_ID", "apac.amazon.nova-pro-v1:0")

# --- AWS clients ---
dynamodb = boto3.resource("dynamodb", region_name=REGION)
table = dynamodb.Table(TABLE_NAME)
ssm = boto3.client("ssm", region_name=REGION)


def _today_ist():
    ist = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist).strftime("%Y-%m-%d")


# --- Tools ---

@tool
def query_videos_by_date(date: str) -> str:
    """Query all videos from a specific date.

    Args:
        date: Date in YYYY-MM-DD format
    """
    try:
        resp = table.query(
            KeyConditionExpression=Key("date").eq(date)
        )
        items = [i for i in resp.get("Items", []) if i.get("video_id") != "digest_order"]
        if not items:
            return json.dumps({"results": [], "message": f"No videos found for {date}"})
        return json.dumps({"results": items, "count": len(items)}, default=str)
    except Exception as e:
        return json.dumps({"error": f"{type(e).__name__}: {e}"})


@tool
def query_videos_by_channel(channel: str, limit: int = 20) -> str:
    """Query videos from a specific channel.

    Args:
        channel: The channel name (case-sensitive)
        limit: Max results to return
    """
    resp = table.query(
        IndexName="channel-index",
        KeyConditionExpression=Key("channel").eq(channel),
        Limit=limit,
        ScanIndexForward=False,
    )
    items = resp.get("Items", [])
    if not items:
        return json.dumps({"results": [], "message": f"No videos found for channel '{channel}'"})
    return json.dumps({"results": items, "count": len(items)}, default=str)


@tool
def search_videos(keyword: str, days: int = 7) -> str:
    """Search videos by keyword in title or summary across recent days.

    Args:
        keyword: Search term to look for in title/summary
        days: Number of days to search back
    """
    kw = keyword.lower()
    results = []
    today = datetime.now(timezone(timedelta(hours=5, minutes=30)))

    for i in range(days):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        resp = table.query(KeyConditionExpression=Key("date").eq(d))
        for item in resp.get("Items", []):
            if item.get("video_id") == "digest_order":
                continue
            title = (item.get("title") or "").lower()
            summary = (item.get("summary") or "").lower()
            if kw in title or kw in summary:
                results.append(item)

    if not results:
        return json.dumps({"results": [], "message": f"No videos matching '{keyword}' in last {days} days"})
    return json.dumps({"results": results, "count": len(results)}, default=str)


@tool
def get_digest_order(date: str) -> str:
    """Get the ordered list of videos from a day's digest (position numbers).

    Args:
        date: Date in YYYY-MM-DD format
    """
    resp = table.query(
        KeyConditionExpression=Key("date").eq(date) & Key("video_id").eq("digest_order")
    )
    items = resp.get("Items", [])
    if not items or not items[0].get("ordered_ids"):
        return json.dumps({"error": f"No digest order found for {date}"})

    ordered_ids = items[0]["ordered_ids"]

    # Get video details
    all_resp = table.query(KeyConditionExpression=Key("date").eq(date))
    video_map = {i["video_id"]: i for i in all_resp.get("Items", []) if i.get("video_id") != "digest_order"}

    result = []
    for i, vid in enumerate(ordered_ids):
        v = video_map.get(vid, {})
        result.append({
            "position": i + 1,
            "video_id": vid,
            "title": v.get("title", "Unknown"),
            "channel": v.get("channel", "Unknown"),
        })
    return json.dumps(result, default=str)


@tool
def save_to_playlist(video_ids: list[str], playlist: str = "Later") -> str:
    """Save videos to a YouTube playlist.

    Args:
        video_ids: List of YouTube video IDs to save
        playlist: Playlist name (default: "Later")
    """
    import urllib.request
    import urllib.parse

    def get_ssm_param(name):
        return ssm.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]

    refresh_token = get_ssm_param("/yt-digest/youtube-refresh-token")
    client_id = get_ssm_param("/yt-digest/youtube-client-id")
    client_secret = get_ssm_param("/yt-digest/youtube-client-secret")

    # Get access token
    token_data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=token_data)
    with urllib.request.urlopen(req) as resp:
        access_token = json.loads(resp.read())["access_token"]

    # Find or create playlist
    headers = {"Authorization": f"Bearer {access_token}"}
    list_req = urllib.request.Request(
        "https://www.googleapis.com/youtube/v3/playlists?part=snippet&mine=true&maxResults=50",
        headers=headers,
    )
    with urllib.request.urlopen(list_req) as resp:
        playlists = json.loads(resp.read())

    playlist_id = None
    created = False
    for p in playlists.get("items", []):
        if p["snippet"]["title"].lower() == playlist.lower():
            playlist_id = p["id"]
            break

    if not playlist_id:
        create_body = json.dumps({
            "snippet": {"title": playlist, "description": "Created by YT Assistant"},
            "status": {"privacyStatus": "private"},
        }).encode()
        create_req = urllib.request.Request(
            "https://www.googleapis.com/youtube/v3/playlists?part=snippet,status",
            data=create_body,
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_req) as resp:
            playlist_id = json.loads(resp.read())["id"]
            created = True

    # Add videos
    saved = []
    failed = []
    for vid in video_ids:
        body = json.dumps({
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {"kind": "youtube#video", "videoId": vid},
            }
        }).encode()
        add_req = urllib.request.Request(
            "https://www.googleapis.com/youtube/v3/playlistItems?part=snippet",
            data=body,
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(add_req) as resp:
                saved.append(vid)
        except Exception as e:
            failed.append({"videoId": vid, "error": str(e)})

    return json.dumps({
        "playlist": playlist,
        "playlistCreated": created,
        "saved": saved,
        "failed": failed,
    })


# --- System Prompt ---
def _build_system_prompt():
    return f"""You are Prerak's personal YouTube subscription assistant (YT Assistant).

Today's date: {_today_ist()}. Use this for relative date calculations (yesterday, last week, etc).
Timezone: Asia/Kolkata (IST, UTC+5:30).

## Personality
- Concise and direct. No filler.
- Present information in clean, scannable formats (numbered lists).
- Casual but efficient tone.

## Tools
You have these tools:
- query_videos_by_date: Get all videos from a date (YYYY-MM-DD)
- query_videos_by_channel: Get videos from a channel (case-sensitive name)
- search_videos: Search by keyword in title/summary across recent days
- get_digest_order: Get position-numbered video list for a date's digest
- save_to_playlist: Save video IDs to a YouTube playlist

## Rules
1. ALWAYS use your DynamoDB tools for video/channel queries. Never make up data.
2. If no results, say so clearly. Try search_videos as fallback before giving up.
3. When user says "save 2 5 7" — use get_digest_order for the relevant date to resolve position numbers to video_ids, then call save_to_playlist.
4. Channel names are case-sensitive. If unsure of casing, use search_videos with channel name as keyword.
5. Format video results as: [Title](https://youtu.be/VIDEO_ID) — Channel\\n  Summary
6. Max 5 videos per response unless user asks for more.
7. Never show raw video_ids to the user.
8. If asked about something outside subscription data, ask before searching elsewhere.
"""


def create_agent(session_id: str = None):
    """Create a Strands agent, optionally with AgentCore Memory session manager."""
    model = BedrockModel(
        model_id=MODEL_ID,
        region_name=REGION,
    )

    tools = [
        query_videos_by_date,
        query_videos_by_channel,
        search_videos,
        get_digest_order,
        save_to_playlist,
    ]

    agent_kwargs = {
        "model": model,
        "system_prompt": _build_system_prompt(),
        "tools": tools,
    }

    # Use AgentCore Memory if MEMORY_ID is set
    memory_id = os.environ.get("AGENTCORE_MEMORY_ID")
    if memory_id and session_id:
        try:
            from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
            from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager

            config = AgentCoreMemoryConfig(
                memory_id=memory_id,
                session_id=session_id,
                actor_id="prerak",
            )
            session_manager = AgentCoreMemorySessionManager(
                agentcore_memory_config=config,
                region_name=REGION,
            )
            agent_kwargs["session_manager"] = session_manager
            logger.info(f"[memory] Connected to AgentCore Memory: {memory_id}, session: {session_id}")
        except ImportError as e:
            logger.error(f"[memory] FAILED — package not installed: {e}")
        except Exception as e:
            logger.error(f"[memory] FAILED to initialize: {type(e).__name__}: {e}")
    elif memory_id and not session_id:
        logger.warning("[memory] MEMORY_ID set but no session_id provided — running without persistence")
    else:
        logger.info("[memory] No AGENTCORE_MEMORY_ID set — running without persistence")

    return Agent(**agent_kwargs)
