"""
Lambda handler — orchestrates the daily YouTube digest.

Flow:
1. Fetch your YouTube subscriptions and their recent videos (last 24h)
2. Fetch transcript for each video (falls back to title+description)
3. Summarize each video using Bedrock
4. Format and send digest to Telegram
"""

import os
import traceback
from datetime import datetime, timezone
from collections import defaultdict

from youtube import get_new_videos
from summarizer import summarize_videos, summarize_bulk_channels
from telegram import send_digest


def handler(event, context):
    """AWS Lambda entry point. Called daily by EventBridge."""

    region = os.environ.get("BEDROCK_REGION", "ap-south-1")
    bedrock_model_param = os.environ["BEDROCK_MODEL_PARAM"]
    youtube_param = os.environ["YOUTUBE_TOKEN_PARAM"]
    youtube_client_id_param = os.environ["YOUTUBE_CLIENT_ID_PARAM"]
    youtube_client_secret_param = os.environ["YOUTUBE_CLIENT_SECRET_PARAM"]
    telegram_token_param = os.environ["TELEGRAM_TOKEN_PARAM"]
    telegram_chat_id_param = os.environ["TELEGRAM_CHAT_ID_PARAM"]

    import boto3
    ssm = boto3.client("ssm")

    def get_param(name):
        return ssm.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]

    # Load telegram creds first so we can send error messages
    try:
        telegram_token = get_param(telegram_token_param)
        telegram_chat_id = get_param(telegram_chat_id_param)
    except Exception as e:
        raise RuntimeError(f"Cannot load Telegram creds from SSM: {e}")

    def notify_error(step, error):
        """Send error to Telegram so I always know something broke."""
        msg = f"⚠️ *YT Digest Failed*\n\nStep: {step}\nError: `{error}`"
        try:
            send_digest(telegram_token, telegram_chat_id, msg)
        except Exception:
            pass

    try:
        print("📦 Loading SSM parameters...")
        model_id = get_param(bedrock_model_param)
        video_fetch_mode = get_param(os.environ["VIDEO_FETCH_MODE_PARAM"])
        youtube_refresh_token = get_param(youtube_param)
        youtube_client_id = get_param(youtube_client_id_param)
        youtube_client_secret = get_param(youtube_client_secret_param)
        print("✅ SSM params loaded")
    except Exception as e:
        notify_error("Loading SSM parameters", e)
        raise

    try:
        print("🔍 Fetching YouTube subscriptions and videos...")
        use_rss = video_fetch_mode == "rss"
        videos = get_new_videos(youtube_refresh_token, youtube_client_id, youtube_client_secret, use_rss=use_rss)
        print(f"✅ Found {len(videos)} new videos")
    except Exception as e:
        notify_error("Fetching YouTube videos", e)
        raise

    if not videos:
        send_digest(telegram_token, telegram_chat_id,
                    "📺 No new videos from your subscriptions today.")
        return {"statusCode": 200, "body": "No new videos"}

    # Separate prolific channels from normal ones
    by_channel = defaultdict(list)
    for v in videos:
        by_channel[v["channel"]].append(v)

    BULK_THRESHOLD = 5
    MAX_INDIVIDUAL_VIDEOS = 40  # Cap individual Bedrock calls (bulk channels don't count)
    normal_videos = []
    bulk_channels = {}

    for channel, vids in by_channel.items():
        if len(vids) >= BULK_THRESHOLD:
            bulk_channels[channel] = [v["title"] for v in vids]
        else:
            normal_videos.extend(vids)

    # Cap individual videos to prevent runaway Bedrock costs
    normal_videos = normal_videos[:MAX_INDIVIDUAL_VIDEOS]

    print(f"🧠 Summarizing {len(normal_videos)} videos individually, {len(bulk_channels)} channels in bulk...")

    try:
        summaries = summarize_videos(normal_videos, region, model_id)
        print(f"✅ Individual summaries done")
    except Exception as e:
        notify_error("Bedrock summarization", e)
        raise

    try:
        bulk_summaries = summarize_bulk_channels(bulk_channels, region, model_id)
        print(f"✅ Bulk summaries done")
    except Exception as e:
        notify_error("Bulk channel summarization", e)
        bulk_summaries = []

    # Format and send
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    today_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Store in DynamoDB for future querying
    try:
        table_name = os.environ.get("VIDEOS_TABLE")
        if table_name:
            dynamodb_table = boto3.resource("dynamodb").Table(table_name)
            with dynamodb_table.batch_writer() as batch:
                for s in summaries:
                    batch.put_item(Item={
                        "date": today_key,
                        "video_id": s["video_id"],
                        "title": s["title"],
                        "channel": s["channel"],
                        "summary": s["summary"],
                        "published_at": today_key,
                    })
                for bs in bulk_summaries:
                    batch.put_item(Item={
                        "date": today_key,
                        "video_id": f"bulk_{bs['channel']}",
                        "title": f"[{bs['count']} videos]",
                        "channel": bs["channel"],
                        "summary": bs["summary"],
                        "published_at": today_key,
                    })
            print(f"💾 Stored {len(summaries) + len(bulk_summaries)} items in DynamoDB")
    except Exception as e:
        print(f"⚠️ DynamoDB write failed (non-fatal): {e}")
    message = f"📺 *YouTube Digest — {today}*\n\n"

    for i, s in enumerate(summaries, 1):
        link = f"https://youtu.be/{s['video_id']}"
        message += f"{i}. [{s['title']}]({link}) ({s['channel']})\n"
        message += f"    → {s['summary']}\n\n"

    if bulk_summaries:
        message += "📦 *Bulk uploads:*\n\n"
        for bs in bulk_summaries:
            message += f"*{bs['channel']}* ({bs['count']} videos)\n"
            message += f"   {bs['summary']}\n\n"

    total = len(summaries) + sum(bs["count"] for bs in bulk_summaries)
    message += f"_{total} videos summarized_"

    try:
        print("📤 Sending digest to Telegram...")
        send_digest(telegram_token, telegram_chat_id, message)
        print("✅ Done!")
    except Exception as e:
        notify_error("Sending Telegram message", e)
        raise

    return {"statusCode": 200, "body": f"Sent digest with {total} videos"}
