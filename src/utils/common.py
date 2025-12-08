import re
import datetime
import time
from urllib.parse import urlparse
from functools import lru_cache

try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None

HIGHLIGHT_COLOR = "#fff6b0"

def markdown_bold_to_highlight(html_text: str) -> str:
    """Convert **bold** markers into highlighted phrases and list items."""
    def wrap_highlight(match):
        text = match.group(1)
        if len(text.split()) >= 2:
            return (
                f"<span class='highlight' style='background-color: {HIGHLIGHT_COLOR};"
                " padding: 3px 5px; border-radius: 4px;'>"
                f"{text}"
                "</span>"
            )
        return f"<strong>{text}</strong>"

    lines = []
    for raw_line in html_text.splitlines():
        cleaned = raw_line.strip()
        if not cleaned:
            continue
        cleaned = re.sub(r"^[•□\-]\s*", "", cleaned)
        converted = re.sub(r"\*\*(.+?)\*\*", wrap_highlight, cleaned)
        lines.append(converted)

    if not lines:
        return ""

    items = [f"<li>{line}</li>" for line in lines]
    return "<ul class='summary-list'>" + "".join(items) + "</ul>"

def contains_korean(text: str) -> bool:
    return bool(re.search(r"[가-힣]", text))

_translator = None

@lru_cache(maxsize=256)
def translate_title_to_korean(title: str) -> str:
    """Translate English titles to Korean for display. Fallback to original on failure."""
    if not title or contains_korean(title):
        return title
    
    if GoogleTranslator is None:
        return title

    global _translator
    if _translator is None:
        _translator = GoogleTranslator(source="auto", target="ko")

    try:
        result = _translator.translate(title)
        return result if result else title
    except Exception:
        pass
    return title

def format_timestamp(ts: float) -> str:
    if not ts:
        return "발행 시각 정보 없음"
    try:
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "발행 시각 정보 없음"

def extract_source_name(entry, link: str) -> str:
    source_title = getattr(entry, "source", None)
    if source_title:
        title_val = getattr(source_title, "title", None)
        if title_val:
            return title_val
    
    netloc = urlparse(link or "").netloc
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc or "출처 미상"

def extract_image_url(entry) -> str:
    media_content = getattr(entry, "media_content", None) or []
    if media_content:
        first = media_content[0]
        if isinstance(first, dict) and first.get("url"):
            return first["url"]

    media_thumbnail = getattr(entry, "media_thumbnail", None) or []
    if media_thumbnail:
        thumb = media_thumbnail[0]
        if isinstance(thumb, dict) and thumb.get("url"):
            return thumb["url"]

    image_link = getattr(entry, "image", None)
    if isinstance(image_link, dict) and image_link.get("href"):
        return image_link["href"]

    def extract_from_html(html_text: str) -> str:
        if not html_text:
            return ""
        match = re.search(r"<img[^>]+src=['\"]([^'\"]+)['\"]", html_text, re.IGNORECASE)
        return match.group(1) if match else ""

    contents = getattr(entry, "content", None) or []
    for content in contents:
        val = content.get("value", "") if isinstance(content, dict) else getattr(content, "value", "")
        candidate = extract_from_html(val)
        if candidate:
            return candidate

    summary_html = getattr(entry, "summary", "") or getattr(entry, "description", "")
    html_candidate = extract_from_html(summary_html)
    if html_candidate:
        return html_candidate

    return ""

def sanitize_summary(summary: str) -> str:
    cleaned_lines = []
    for line in summary.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if "URL:" in stripped:
            continue
        if re.search(r"출처\s*:", stripped):
            continue
        if re.search(r"https?://", stripped):
            continue
        cleaned_lines.append(stripped)

    return "\n".join(cleaned_lines)
