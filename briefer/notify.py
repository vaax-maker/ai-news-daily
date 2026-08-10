"""텔레그램 전송 (sendPhoto: 세로 인포그래픽 + 티저 캡션).

Ported from send_telegram.py. Credentials are never hardcoded — pass token/chat
explicitly (loaded by the caller from env or a creds file).
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

SITE_URL = "https://vaax-maker.github.io/ai-news-daily/"


def build_caption(brief):
    """Build the sendPhoto caption from today's brief doc."""
    date = brief.get("date", "")
    try:
        import datetime
        dobj = datetime.date.fromisoformat(date)
        wk = ["월", "화", "수", "목", "금", "토", "일"][dobj.weekday()]
        dl = f"{dobj.month}월{dobj.day}일({wk})"
    except Exception:
        dl = date

    title = brief.get("title", "")
    stories = brief.get("stories") or []
    lines = [f"[AI 브리핑] {dl}", "", f"\"{title}\"", ""]
    for s in stories[:3]:
        headline = s.get("headline", "")
        if headline:
            lines.append(f"ㅇ {headline}")
            lines.append("")
    lines.append(SITE_URL)
    return "\n".join(lines)


def _multipart(fields, filefield, filepath):
    b = "----b" + uuid.uuid4().hex
    nl = b"\r\n"
    body = b""
    for k, v in fields.items():
        body += f"--{b}".encode() + nl
        body += f'Content-Disposition: form-data; name="{k}"'.encode() + nl + nl
        body += str(v).encode() + nl
    fn = os.path.basename(filepath)
    body += f"--{b}".encode() + nl
    body += f'Content-Disposition: form-data; name="{filefield}"; filename="{fn}"'.encode() + nl
    body += b"Content-Type: image/png" + nl + nl
    body += open(filepath, "rb").read() + nl
    body += f"--{b}--".encode() + nl
    return body, f"multipart/form-data; boundary={b}"


def send_photo(png_path, caption, token, chat):
    """Send sendPhoto(png_path, caption) via Telegram Bot API. Returns the parsed JSON response."""
    if not token or not chat:
        raise ValueError("token/chat required (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)")
    if os.path.exists(png_path):
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        body, ct = _multipart({"chat_id": chat, "caption": caption}, "photo", png_path)
        req = urllib.request.Request(url, data=body, headers={"Content-Type": ct})
        kind = "sendPhoto(인포그래픽+캡션)"
    else:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        body = urllib.parse.urlencode({"chat_id": chat, "text": caption,
                                       "disable_web_page_preview": "true"}).encode()
        req = urllib.request.Request(url, data=body)
        kind = "sendMessage(텍스트만 — 이미지 없음)"
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.loads(r.read().decode())
    ok = res.get("ok")
    mid = res.get("result", {}).get("message_id")
    chat_info = res.get("result", {}).get("chat", {})
    print(f"[{kind}] ok={ok} message_id={mid} → chat: "
          f"{chat_info.get('title') or chat_info.get('username') or chat_info.get('id')} "
          f"({chat_info.get('type')})", file=sys.stderr)
    return res


if __name__ == "__main__":
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    png = sys.argv[1] if len(sys.argv) > 1 else "docs/infographic.png"
    brief = json.load(open(sys.argv[2])) if len(sys.argv) > 2 else {}
    caption = build_caption(brief)
    send_photo(png, caption, token, chat)
