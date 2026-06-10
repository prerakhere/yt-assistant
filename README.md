# yt-assistant

Daily YouTube subscription digest delivered to Telegram + DynamoDB storage for future querying via OpenClaw.

## What it does

Every day at 6 AM IST, a Lambda fetches your latest YouTube subscription videos, summarizes them using AWS Bedrock, and sends a formatted digest to your Telegram bot.

## Architecture

```
EventBridge (daily 6 AM IST) → Lambda → RSS Feeds + Transcripts → Bedrock → Telegram
                                                                           → DynamoDB
```

## Cost

| Service | Monthly cost |
|---------|-------------|
| Lambda | Free tier |
| EventBridge | Free tier |
| SSM Parameter Store | Free |
| DynamoDB | Free tier |
| Bedrock (Nova Lite) | ~₹25-30 |
| **Total** | **~₹25-30/month** |

## Features

- Fetches subscriptions via RSS feeds (fast, parallel transcript fetching)
- Summarizes videos using Bedrock (batched, 3 per call)
- Bulk summarizes channels with 5+ videos on same day
- Clickable video links in digest
- Stores summaries in DynamoDB for future OpenClaw integration
- Error notifications via Telegram
- Configurable: model, fetch mode (RSS/API) via SSM parameters

## Project Structure

```
├── cdk/
│   ├── app.py              # CDK entry point
│   ├── stack.py            # Infrastructure (Lambda, EventBridge, IAM, DynamoDB)
│   ├── cdk.json            # CDK config
│   └── requirements.txt    # CDK dependencies
├── lambda/
│   ├── handler.py          # Lambda entry (orchestrator)
│   ├── youtube.py          # RSS feeds + YouTube API fallback + transcript fetching
│   ├── summarizer.py       # Bedrock batched summarization
│   ├── telegram.py         # Telegram message delivery
│   └── requirements.txt    # Lambda dependencies
└── .gitignore
```

## SSM Parameters

| Parameter | Value |
|-----------|-------|
| `/yt-digest/youtube-refresh-token` | OAuth refresh token |
| `/yt-digest/youtube-client-id` | GCP OAuth client ID |
| `/yt-digest/youtube-client-secret` | GCP OAuth client secret |
| `/yt-digest/telegram-bot-token` | Telegram bot token |
| `/yt-digest/telegram-chat-id` | Your Telegram chat ID |
| `/yt-digest/bedrock-model-id` | e.g. `apac.amazon.nova-lite-v1:0` |
| `/yt-digest/video-fetch-mode` | `rss` (default) or `api` |

## Setup

### Prerequisites

- AWS CLI configured with a profile
- Python 3.12+
- Node.js 18+ (for CDK)
- Docker (for Lambda bundling)

### Deploy

```bash
cd cdk
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npx cdk bootstrap --profile <your-profile>
npx cdk deploy --profile <your-profile>
```

### Test

```bash
aws lambda invoke --function-name <function-name> \
    --invocation-type Event --profile <your-profile> --region ap-south-1 response.json
```

## Roadmap

- [ ] OpenClaw integration (conversational queries over stored digests)
- [ ] Save to Watch Later via Telegram replies
- [ ] Weekly roundup summaries
