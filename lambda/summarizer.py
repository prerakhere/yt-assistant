"""
Summarizer module — uses AWS Bedrock to summarize video content.

The model is configurable via the BEDROCK_MODEL_ID environment variable.
boto3 (AWS SDK for Python) comes pre-installed in Lambda.
"""

import boto3
from botocore.config import Config

# Strict config: no retries, 30s timeout per call
BEDROCK_CONFIG = Config(
    retries={"max_attempts": 0},
    read_timeout=30,
    connect_timeout=5,
)


def _summarize_one(bedrock, model_id, title, transcript_or_desc):
    """Call Bedrock to summarize a single video's content."""
    prompt = (
        "Summarize this YouTube video in 1-2 concise sentences. "
        "Focus on the key topic or takeaway.\n\n"
        f"Title: {title}\n"
        f"Content: {transcript_or_desc}"
    )

    response = bedrock.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 150, "temperature": 0.3},
    )

    return response["output"]["message"]["content"][0]["text"].strip()


BATCH_SIZE = 3


def summarize_videos(videos, region, model_id):
    """
    Summarize videos using Bedrock in batches of 5 per call.

    Args:
        videos: list of dicts with keys: video_id, title, channel, transcript_or_desc
        region: AWS region for Bedrock (e.g. "ap-south-1")
        model_id: Bedrock model ID

    Returns:
        list of dicts: [{"title", "channel", "summary"}, ...]
    """
    bedrock = boto3.client("bedrock-runtime", region_name=region, config=BEDROCK_CONFIG)
    summaries = []

    for i in range(0, len(videos), BATCH_SIZE):
        batch = videos[i:i + BATCH_SIZE]
        try:
            batch_summaries = _summarize_batch(bedrock, model_id, batch)
        except Exception as e:
            # Fallback: mark all in batch as failed
            batch_summaries = [f"(Could not summarize: {e})"] * len(batch)

        for video, summary in zip(batch, batch_summaries):
            summaries.append({
                "video_id": video["video_id"],
                "title": video["title"],
                "channel": video["channel"],
                "summary": summary,
            })

    return summaries


def _summarize_batch(bedrock, model_id, batch):
    """Summarize a batch of videos in a single Bedrock call."""
    prompt = "Summarize each YouTube video below in 1-2 concise sentences. Focus on the key topic or takeaway.\n\n"

    for idx, video in enumerate(batch, 1):
        prompt += f"Video {idx}: {video['title']}\n{video['transcript_or_desc']}\n\n"

    prompt += f"Respond with exactly {len(batch)} numbered summaries (1. ... 2. ... etc), one per video."

    response = bedrock.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 150 * len(batch), "temperature": 0.3},
    )

    raw = response["output"]["message"]["content"][0]["text"].strip()

    # Parse numbered responses
    lines = raw.split("\n")
    results = []
    current = ""
    for line in lines:
        # Check if line starts a new numbered item
        stripped = line.strip()
        if stripped and stripped[0].isdigit() and "." in stripped[:3]:
            if current:
                results.append(current.strip())
            current = stripped.split(".", 1)[1].strip()
        else:
            current += " " + stripped

    if current:
        results.append(current.strip())

    # If parsing fails, return raw split evenly
    if len(results) != len(batch):
        return [raw] * 1 + ["(Summary parsing failed)"] * (len(batch) - 1)

    return results


def summarize_bulk_channels(bulk_channels, region, model_id):
    """
    Summarize channels that posted 20+ videos with a single Bedrock call per channel.

    Args:
        bulk_channels: dict of {channel_name: [list of video titles]}
        region: AWS region for Bedrock
        model_id: Bedrock model ID

    Returns:
        list of dicts: [{"channel", "count", "summary"}, ...]
    """
    if not bulk_channels:
        return []

    bedrock = boto3.client("bedrock-runtime", region_name=region, config=BEDROCK_CONFIG)
    results = []

    for channel, titles in bulk_channels.items():
        titles_text = "\n".join(f"- {t}" for t in titles)
        prompt = (
            f"This YouTube channel '{channel}' uploaded {len(titles)} videos today. "
            "Based on these video titles, give a 1-2 sentence summary of what the "
            "channel posted about today.\n\n"
            f"Titles:\n{titles_text}"
        )

        try:
            response = bedrock.converse(
                modelId=model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 100, "temperature": 0.3},
            )
            summary = response["output"]["message"]["content"][0]["text"].strip()
        except Exception as e:
            summary = f"(Could not summarize: {e})"

        results.append({
            "channel": channel,
            "count": len(titles),
            "summary": summary,
        })

    return results
