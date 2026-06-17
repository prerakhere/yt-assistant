"""
Router Lambda — bridges Telegram webhook to AgentCore Runtime.

Flow: Telegram POST → extract message → invoke AgentCore → send response to Telegram
"""

import os
import json
import boto3
import requests

AGENT_RUNTIME_ARN = os.environ["AGENT_RUNTIME_ARN"]
TELEGRAM_TOKEN_PARAM = os.environ["TELEGRAM_TOKEN_PARAM"]
TELEGRAM_CHAT_ID_PARAM = os.environ["TELEGRAM_CHAT_ID_PARAM"]
REGION = os.environ.get("AWS_REGION", "ap-south-1")

ssm = boto3.client("ssm")
agentcore = boto3.client("bedrock-agentcore", region_name=REGION)


def get_param(name):
    return ssm.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]


def send_telegram(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    # Try Markdown first, fallback to plain text if it fails
    resp = requests.post(url, json={
        "chat_id": chat_id,
        "text": text[:4000],
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    })
    if not resp.ok:
        requests.post(url, json={
            "chat_id": chat_id,
            "text": text[:4000],
            "disable_web_page_preview": True,
        })


def handler(event, context):
    # Validate Telegram secret token (prevents unauthorized invocations)
    headers = event.get("headers", {})
    expected_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    if expected_secret and headers.get("x-telegram-bot-api-secret-token") != expected_secret:
        return {"statusCode": 403, "body": "Forbidden"}

    # Parse Telegram webhook payload
    body = json.loads(event.get("body", "{}"))
    message = body.get("message", {})
    text = message.get("text", "")
    chat_id = str(message.get("chat", {}).get("id", ""))

    if not text or not chat_id:
        return {"statusCode": 200, "body": "ok"}

    # Load Telegram creds
    token = get_param(TELEGRAM_TOKEN_PARAM)
    allowed_chat_id = get_param(TELEGRAM_CHAT_ID_PARAM)

    # Only respond to your chat (security)
    if chat_id != allowed_chat_id:
        return {"statusCode": 200, "body": "ok"}

    # Invoke AgentCore
    try:
        import uuid
        session_id = f"tg_{chat_id}_stable_session_v15abcdefg"
        response = agentcore.invoke_agent_runtime(
            agentRuntimeArn=AGENT_RUNTIME_ARN,
            runtimeSessionId=session_id,
            payload=json.dumps({"prompt": text}),
            qualifier="DEFAULT",
        )
        response_body = json.loads(response["response"].read())
        reply = response_body.get("response", "Sorry, I couldn't process that.")
    except Exception as e:
        print(f"AgentCore error: {type(e).__name__}: {e}")
        reply = f"⚠️ Error: {e}"

    # Send response back to Telegram
    send_telegram(token, chat_id, reply)

    return {"statusCode": 200, "body": json.dumps({"reply": reply})}
