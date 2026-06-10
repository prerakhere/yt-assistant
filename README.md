# YouTube Subscription Daily Digest

Daily summary of your YouTube subscription videos, delivered to Telegram. Powered by AWS Lambda + Bedrock (Amazon Nova Lite).

## Architecture

```
EventBridge (daily 8 AM IST) → Lambda → YouTube API + Transcripts → Bedrock → Telegram
```

## Cost

- YouTube Data API: Free (under 300 units/day of 10,000 quota)
- Transcripts: Free (youtube-transcript-api, no API quota)
- Lambda: Free tier (1 invocation/day)
- EventBridge: Free tier
- SSM Parameter Store: Free (standard parameters)
- Bedrock (Nova Lite): ~$0.30-0.50/month

**Total: under $1/month**

## Setup

### Prerequisites

- AWS CLI configured (`aws sts get-caller-identity` should work)
- Python 3.12+
- Node.js 18+ (for CDK CLI)
- AWS CDK (`npm install -g aws-cdk`)

### 1. Google Cloud (YouTube API)

1. Go to https://console.cloud.google.com
2. Create a new project (e.g. "yt-digest")
3. Enable "YouTube Data API v3"
4. Create OAuth 2.0 credentials (Desktop app type)
5. Note your Client ID and Client Secret
6. Run the one-time auth to get a refresh token:

```bash
cd lambda
pip install google-auth-oauthlib
python -c "
from google_auth_oauthlib.flow import InstalledAppFlow
flow = InstalledAppFlow.from_client_config(
    {'installed': {'client_id': 'YOUR_CLIENT_ID', 'client_secret': 'YOUR_CLIENT_SECRET',
     'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
     'token_uri': 'https://oauth2.googleapis.com/token'}},
    scopes=['https://www.googleapis.com/auth/youtube.readonly']
)
creds = flow.run_local_server(port=8080)
print(f'Refresh token: {creds.refresh_token}')
"
```

7. Save the refresh token — you'll need it in step 3.

### 2. Telegram Bot

1. Message @BotFather on Telegram → `/newbot` → follow prompts
2. Save the bot token (e.g. `123456:ABC-DEF...`)
3. Message your new bot (say anything)
4. Get your chat ID:
```bash
curl https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates | python -m json.tool
```
Look for `"chat": {"id": 123456789}` — that's your chat ID.

### 3. Store Secrets in AWS SSM

```bash
aws ssm put-parameter --name /yt-digest/youtube-refresh-token \
    --value "YOUR_REFRESH_TOKEN" --type SecureString

aws ssm put-parameter --name /yt-digest/telegram-bot-token \
    --value "YOUR_BOT_TOKEN" --type SecureString

aws ssm put-parameter --name /yt-digest/telegram-chat-id \
    --value "YOUR_CHAT_ID" --type String
```

### 4. Update YouTube OAuth Credentials

Edit `lambda/youtube.py` and replace `CLIENT_ID` and `CLIENT_SECRET` with your values from step 1.

### 5. Deploy

```bash
cd cdk
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cdk bootstrap  # first time only
cdk deploy
```

### 6. Test

Invoke the Lambda manually to verify:
```bash
aws lambda invoke --function-name YtDigestStack-DigestFn* /dev/stdout
```

## Project Structure

```
├── cdk/
│   ├── app.py              # CDK entry point
│   ├── stack.py            # Infrastructure definition
│   ├── cdk.json            # CDK config
│   └── requirements.txt    # CDK dependencies
├── lambda/
│   ├── handler.py          # Lambda entry (orchestrator)
│   ├── youtube.py          # YouTube API + transcript fetching
│   ├── summarizer.py       # Bedrock Nova Lite summarization
│   ├── telegram.py         # Telegram message delivery
│   └── requirements.txt    # Lambda dependencies
└── .gitignore
```
