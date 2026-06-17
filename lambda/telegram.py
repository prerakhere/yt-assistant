"""
Telegram module — sends the digest message to your Telegram chat.

Uses the Telegram Bot API (simple HTTP POST, no SDK needed).
The `requests` library handles the HTTP call.
"""

import time
import requests

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

# Telegram has a 4096 character limit per message
MAX_MSG_LEN = 4000


def send_digest(bot_token, chat_id, message):
    """
    Send a message to Telegram. Splits into multiple messages if too long.

    Args:
        bot_token: Telegram bot token from @BotFather
        chat_id: Your personal chat ID (numeric string)
        message: The formatted digest text
    """
    url = TELEGRAM_API.format(token=bot_token)

    # Split long messages
    chunks = _split_message(message)

    for i, chunk in enumerate(chunks):
        if i > 0:
            time.sleep(1)  # 1s delay between chunks to avoid rate limits
        response = requests.post(url, json={
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        })
        if not response.ok:
            # Fallback: send without Markdown if formatting breaks
            requests.post(url, json={
                "chat_id": chat_id,
                "text": chunk,
                "disable_web_page_preview": True,
            }).raise_for_status()


def _split_message(message):
    """Split message into chunks under Telegram's 4096 char limit."""
    if len(message) <= MAX_MSG_LEN:
        return [message]

    chunks = []
    while message:
        if len(message) <= MAX_MSG_LEN:
            chunks.append(message)
            break
        # Split at last newline before limit
        split_at = message.rfind("\n", 0, MAX_MSG_LEN)
        if split_at == -1:
            split_at = MAX_MSG_LEN
        chunks.append(message[:split_at])
        message = message[split_at:].lstrip("\n")

    return chunks
