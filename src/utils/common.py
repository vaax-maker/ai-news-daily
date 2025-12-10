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
    seen = set()
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
        cleaned = re.sub(r"[^0-9A-Za-z가-힣\s.,;:!?\"'()\[\]{}<>@#%&*`~\-_/+|=]", "", stripped)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        cleaned_lines.append(cleaned)

    return "\n".join(cleaned_lines)


def trim_summary_lines(summary: str, min_lines: int = 3, max_lines: int = 5) -> str:
    """Force summaries to stay within the desired 3~5 line window."""
    lines = [line.strip() for line in summary.splitlines() if line.strip()]

    if len(lines) < min_lines:
        # Break long sentences to meet the minimum line requirement
        combined = " ".join(lines) if lines else summary
        sentences = re.split(r"(?<=[.!?\u3002])\s+", combined)
        sentences = [s.strip() for s in sentences if s.strip()]

        for sentence in sentences:
            if sentence not in lines:
                lines.append(sentence)
            if len(lines) >= min_lines:
                break

    trimmed = lines[:max_lines] if lines else []
    return "\n".join(trimmed)


def shorten_korean_title(title: str, max_length: int = 40) -> str:
    """Translate English titles to Korean and trim them to under 40 chars."""
    translated = translate_title_to_korean(title)
    translated = translated or title

    if len(translated) > max_length:
        return translated[: max_length - 1] + "…"
    return translated


def parse_article_datetime(article: dict) -> datetime.datetime:
    """Robust datetime parser for article dictionaries.

    Tries timestamp fields first, then common string date fields used across
    feeds and generated HTML. Returns datetime.min on failure so sorting keeps
    unknown dates last.
    """

    if not article:
        return datetime.datetime.min

    ts = article.get("timestamp")
    if ts:
        try:
            return datetime.datetime.fromtimestamp(float(ts))
        except Exception:
            pass

    candidates = [
        article.get("published_display"),
        article.get("published"),
        article.get("published_at"),
        article.get("date"),
    ]

    for value in candidates:
        if not value:
            continue
        cleaned = str(value).replace(".", "-")
        try:
            return datetime.datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        except Exception:
            pass
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.datetime.strptime(cleaned, fmt)
            except Exception:
                continue

    return datetime.datetime.min
