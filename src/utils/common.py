import re
import datetime
import time
from urllib.parse import urlparse
from functools import lru_cache

try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None

HIGHLIGHT_COLOR = "#E6F8D7"

HIGHLIGHT_STYLE = (
    f"background-color: {HIGHLIGHT_COLOR}; padding: 3px 5px; border-radius: 4px;"
)


def _wrap_highlight(text: str) -> str:
    return (
        "<span class='highlight' style='"
        + HIGHLIGHT_STYLE
        + "'>"
        + text
        + "</span>"
    )


def get_kst_now() -> datetime.datetime:
    """Returns current time in KST (UTC+9)."""
    utc_now = datetime.datetime.utcnow()
    kst_timezone = datetime.timezone(datetime.timedelta(hours=9))
    return utc_now.replace(tzinfo=datetime.timezone.utc).astimezone(kst_timezone)


def markdown_bold_to_highlight(html_text: str) -> str:
    r"""Convert structured markdown summary to HTML.

    Supports two formats:
    1. New format: ## 1. 핵심 내용, ## 2. 배경 및 맥락, etc. + **한 줄 요약**
    2. Legacy format: [제목], [요약], [의미]
    
    Bold text (\*\* ... \*\*) is converted to highlighted spans.
    """
    
    if not html_text or not html_text.strip():
        return ""

    # If it's already HTML, don't re-process
    if "<ul" in html_text or "<li>" in html_text or "<div" in html_text:
        return html_text

    # Check if it's new format (has ## headers)
    is_new_format = "## " in html_text or "**주제**:" in html_text or "**한 줄 요약**:" in html_text
    
    if is_new_format:
        return _render_new_format(html_text)
    else:
        return _render_legacy_format(html_text)


def _render_new_format(text: str) -> str:
    """Render new structured format with sections."""
    
    sections = []
    current_section = {"title": "", "items": []}
    one_line_summary = ""
    
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        
        # Check for one-line summary
        if "**한 줄 요약**:" in stripped or "한 줄 요약:" in stripped:
            # Extract the summary text after the colon
            summary_text = re.sub(r"^\*?\*?한 줄 요약\*?\*?:\s*", "", stripped)
            one_line_summary = summary_text
            continue
        
        # Check for section header (## 1. 핵심 내용)
        header_match = re.match(r"^##\s*\d*\.?\s*(.+)$", stripped)
        if header_match:
            if current_section["title"] or current_section["items"]:
                sections.append(current_section)
            current_section = {"title": header_match.group(1).strip(), "items": []}
            continue
        
        # Check for **주제**: line (treat as important)
        if stripped.startswith("**주제**:") or stripped.startswith("주제:"):
            topic_text = re.sub(r"^\*?\*?주제\*?\*?:\s*", "", stripped)
            current_section["items"].append({"text": topic_text, "important": True})
            continue
        
        # Regular bullet point - remove common bullet characters (dash, dot, circle, etc.)
        # CAUTION: Do NOT remove '*' greedily, as it might be part of **Bold** syntax at the start.
        # Only remove '*' if followed by space, or just rely on other bullet types.
        # Safest: Remove specific bullet chars, then leading whitespace.
        cleaned = re.sub(r"^[•\-○●·\u2022\u25cf\u25cb]+", "", stripped)
        cleaned = re.sub(r"^\s+", "", cleaned)
        
        # Handle star bullet separately: '* ' at start of line
        cleaned = re.sub(r"^\*\s+", "", cleaned)
        
        # Now cleaned should preserve '**' if it was '**Keyword**'
        if not cleaned:
            continue
        
        # Check for bold markers and wrap them in highlight span directly
        # Regex: replace **content** with <span class='highlight' ...>content</span>
        
        def replace_bold(match):
            content = match.group(1)
            return _wrap_highlight(content)
            
        cleaned = re.sub(r"\*\*(.+?)\*\*", replace_bold, cleaned)
        
        current_section["items"].append({"text": cleaned, "important": False})
    
    # Don't forget the last section
    if current_section["title"] or current_section["items"]:
        sections.append(current_section)
    
    if not sections and not one_line_summary:
        return ""
    
    # Render HTML
    html_parts = []
    
    for section in sections:
        if not section["items"]:
            continue
        
        section_html = []
        if section["title"]:
            section_html.append(f"<div class='summary-section-title'>{section['title']}</div>")
        
        items_html = []
        for item in section["items"]:
            # 'text' already contains <span class='highlight'>...</span>
            items_html.append(f"<li>{item['text']}</li>")
        
        if items_html:
            section_html.append(f"<ul class='summary-list'>{''.join(items_html)}</ul>")
        
        html_parts.append("".join(section_html))
    
    main_html = "".join(html_parts)
    
    # Add one-line summary at the end
    meaning_html = ""
    if one_line_summary:
        meaning_html = f"<div class='meaning-box'><div class='meaning-line'>{one_line_summary}</div></div>"
    
    return main_html + meaning_html


def _render_legacy_format(html_text: str) -> str:
    """Render legacy format with [제목], [요약], [의미] sections."""
    
    main_lines = []
    meaning_lines = []
    total_chars = 0
    current_section = None

    for raw_line in html_text.splitlines():
        cleaned = raw_line.strip()
        if not cleaned:
            continue

        # Remove bullets but preserve bold markers
        cleaned = re.sub(r"^[•□\-○●·\u2022\u25cf\u25cb]+", "", cleaned)
        cleaned = re.sub(r"^\s+", "", cleaned)
        cleaned = re.sub(r"^\*\s+", "", cleaned)

        section_match = re.fullmatch(r"\[?(제목|요약|의미)\]?", cleaned)
        if section_match:
            current_section = section_match.group(1)
            continue

        target_list = meaning_lines if current_section == "의미" else main_lines
        target_list.append(cleaned)
        total_chars += len(cleaned)

    if not main_lines and not meaning_lines:
        return ""

    highlight_budget = int(total_chars * 0.2)
    highlighted_chars = 0

    def render_lines(lines):
        rendered = []
        for text in lines:
            # Inline bold handling for legacy
            def replace_bold(match):
                return _wrap_highlight(match.group(1))
            
            # Highlight **bold** sections inline
            processed = re.sub(r"\*\*(.+?)\*\*", replace_bold, text)
            rendered.append(processed)
        return rendered

    rendered_main = render_lines(main_lines)
    rendered_meaning = render_lines(meaning_lines)

    main_html = ""
    if rendered_main:
        items = [f"<li>{line}</li>" for line in rendered_main]
        main_html = "<ul class='summary-list'>" + "".join(items) + "</ul>"

    meaning_html = ""
    if rendered_meaning:
        meaning_items = "".join(
            f"<div class='meaning-line'>{line}</div>" for line in rendered_meaning
        )
        meaning_html = f"<div class='meaning-box'>{meaning_items}</div>"

    return main_html + meaning_html

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

def extract_image_url(entry, link: str = "") -> str:
    """Extract image URL from feed entry with YouTube support.
    
    - Properly handles YouTube video thumbnails
    - Falls back through multiple sources
    """
    
    # 1. Try to extract YouTube video ID and get proper thumbnail
    youtube_id = _extract_youtube_video_id(link or getattr(entry, 'link', ''))
    if youtube_id:
        # Use maxresdefault for best quality, falls back automatically on YouTube's side
        return f"https://img.youtube.com/vi/{youtube_id}/maxresdefault.jpg"
    
    # 2. Check media_content
    media_content = getattr(entry, "media_content", None) or []
    if media_content:
        first = media_content[0]
        if isinstance(first, dict) and first.get("url"):
            return first["url"]

    # 3. Check media_thumbnail
    media_thumbnail = getattr(entry, "media_thumbnail", None) or []
    if media_thumbnail:
        thumb = media_thumbnail[0]
        if isinstance(thumb, dict) and thumb.get("url"):
            return thumb["url"]

    # 4. Check image link
    image_link = getattr(entry, "image", None)
    if isinstance(image_link, dict) and image_link.get("href"):
        return image_link["href"]

    # 5. Check links (enclosure type)
    links = getattr(entry, "links", []) or []
    for l in links:
        if isinstance(l, dict) and l.get("type", "").startswith("image/") and l.get("href"):
            return l["href"]
        # Some feeds use enclosure without explicit image type but correct rel
        if isinstance(l, dict) and l.get("rel") == "enclosure" and l.get("href"):
             # Basic extension check
             if l["href"].lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                 return l["href"]

    # 6. Extract from HTML content
    def extract_from_html(html_text: str) -> str:
        if not html_text:
            return ""
        # Improved regex to handle various attributes and spacing
        match = re.search(r'<img[^>]+src\s*=\s*["\']([^"\']+)["\']', html_text, re.IGNORECASE)
        return match.group(1) if match else ""

    # Check content (full text)
    contents = getattr(entry, "content", None) or []
    for content in contents:
        val = content.get("value", "") if isinstance(content, dict) else getattr(content, "value", "")
        candidate = extract_from_html(val)
        if candidate:
            return candidate

    # Check summary/description
    summary_html = getattr(entry, "summary", "") or getattr(entry, "description", "")
    html_candidate = extract_from_html(summary_html)
    if html_candidate:
        return html_candidate

    # Check summary_detail (common in feedparser)
    summary_detail = getattr(entry, "summary_detail", None)
    if summary_detail:
        val = summary_detail.get("value", "") if isinstance(summary_detail, dict) else getattr(summary_detail, "value", "")
        candidate = extract_from_html(val)
        if candidate:
            return candidate

    return ""


def _extract_youtube_video_id(url: str) -> str:
    """Extract YouTube video ID from various URL formats."""
    if not url:
        return ""
    
    # Standard YouTube URL patterns
    patterns = [
        r'youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
        r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
        r'youtu\.be/([a-zA-Z0-9_-]{11})',
        r'youtube\.com/v/([a-zA-Z0-9_-]{11})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return ""


# Category-specific fallback images (can be overridden via config)
FALLBACK_IMAGES = {
    "ai": "https://images.unsplash.com/photo-1677442136019-21780ecad995?w=400&q=80",  # AI abstract
    "xr": "https://images.unsplash.com/photo-1622979135225-d2ba269cf1ac?w=400&q=80",  # VR headset
    "gov": "https://images.unsplash.com/photo-1568992687947-868a62a9f521?w=400&q=80", # Government building
    "members": "https://images.unsplash.com/photo-1559136555-9303baea8ebd?w=400&q=80", # Business
    "default": "https://images.unsplash.com/photo-1504711434969-e33886168f5c?w=400&q=80" # News
}


def get_fallback_image(category: str = "default") -> str:
    """Get a fallback image URL for a given category."""
    return FALLBACK_IMAGES.get(category, FALLBACK_IMAGES["default"])

def sanitize_summary(summary: str) -> str:
    # Remove Qwen's <think>...</think> reasoning blocks
    summary = re.sub(r'<think>.*?</think>', '', summary, flags=re.DOTALL)
    
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
        cleaned = re.sub(r"[^0-9A-Za-z가-힣\s.,;:!?\"'()\[\]{}<>@#%&*`~\-_/+|=\u2022\u25cf\u25cb\u00b7]", "", stripped)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        cleaned_lines.append(cleaned)

    return "\n".join(cleaned_lines)


def trim_summary_lines(summary: str, min_lines: int = 3, max_lines: int = 5) -> str:
    """Force summaries to stay within the desired 3~5 line window.

    The 의미 섹션은 항상 보존하며, 요약 줄 수 보정은 제목/요약 파트에만 적용.
    """

    lines = [line.strip() for line in summary.splitlines() if line.strip()]

    meaning_lines = []
    for idx, line in enumerate(lines):
        if re.fullmatch(r"\[?의미\]?", line):
            meaning_lines = lines[idx + 1 :]
            lines = lines[:idx]
            break

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

    if meaning_lines:
        trimmed.append("[의미]")
        trimmed.extend(meaning_lines)

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
