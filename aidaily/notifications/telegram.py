"""Telegram Bot API transport.

Message composition belongs to notification-specific modules. This module owns only
the external API call and multipart encoding.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import uuid

from aidaily import config
from aidaily.integrations.http import request_bytes
from aidaily.notifications.captions import validate_daily_header


def _multipart(fields: dict, file_field: str, file_path: str) -> tuple[bytes, str]:
    boundary = "----aidaily" + uuid.uuid4().hex
    newline = b"\r\n"
    body = b""
    for key, value in fields.items():
        body += f"--{boundary}".encode() + newline
        body += f'Content-Disposition: form-data; name="{key}"'.encode() + newline * 2
        body += str(value).encode() + newline
    filename = os.path.basename(file_path)
    body += f"--{boundary}".encode() + newline
    body += (
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"'
    ).encode() + newline
    body += b"Content-Type: image/png" + newline * 2
    with open(file_path, "rb") as image:
        body += image.read()
    body += newline + f"--{boundary}--".encode() + newline
    return body, f"multipart/form-data; boundary={boundary}"


def send_photo(image_path: str, caption: str, token: str, chat_id: str) -> dict:
    validate_daily_header(caption)
    if not token or not chat_id:
        raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")

    if os.path.isfile(image_path):
        url = f"{config.TELEGRAM_API_URL}/bot{token}/sendPhoto"
        body, content_type = _multipart(
            {"chat_id": chat_id, "caption": caption}, "photo", image_path
        )
        headers = {"Content-Type": content_type}
    else:
        url = f"{config.TELEGRAM_API_URL}/bot{token}/sendMessage"
        body = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": caption,
            "disable_web_page_preview": "true",
        }).encode()
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

    raw, _ = request_bytes(url, data=body, headers=headers, timeout=30)
    result = json.loads(raw.decode())
    if not result.get("ok"):
        raise RuntimeError(f"Telegram rejected the notification: {result}")
    return result


def send_admin_text(text: str, token: str, chat_id: str) -> dict:
    """Operational alert to an explicitly configured admin, outside reader digests."""
    body = urllib.parse.urlencode({'chat_id': chat_id, 'text': text,
                                  'disable_web_page_preview': 'true'}).encode()
    raw, _ = request_bytes(f'{config.TELEGRAM_API_URL}/bot{token}/sendMessage', data=body,
        headers={'Content-Type': 'application/x-www-form-urlencoded'}, timeout=30)
    result = json.loads(raw.decode())
    if not result.get('ok'):
        raise RuntimeError('Telegram rejected admin alert')
    return result
