import os
import time
import datetime
import feedparser
import google.generativeai as genai
import re
import random
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List
from urllib.parse import urlparse

try:
    from googletrans import Translator
except ImportError:  # pragma: no cover - optional dependency for local dev
    Translator = None

@dataclass
class CategoryConfig:
    key: str
    display_name: str
    rss_feeds: List[str]
    archive_dir: str
    index_path: str
    max_articles: int = 15
    fallback_image_url: str = ""
    # selection_mode: 기사 선택 방식 설정 (워크플로 입력 → 환경 변수 → 기본값 순으로 결정)
    #  - "time": RSS에서 가져온 최신 순으로 정렬해 상위 N개 선택
    #  - "random": 정렬 없이 무작위 섞기 후 상위 N개 선택
    #  - "keyword": 지정한 키워드가 제목·본문에 들어간 기사만 필터링 후 최신 순으로 선택
    selection_mode: str = "time"
    keyword_filters: List[str] = field(default_factory=list)


# --- 설정 ---


def resolve_selection_mode(key: str, default: str = "time") -> str:
    # <카테고리>_SELECTION_MODE 환경 변수로 선택 모드를 지정한다.
    # 예) AI 카테고리에 랜덤 적용: `export AI_SELECTION_MODE=random`
    # GitHub Actions( daily-news.yml )에서 workflow_dispatch 입력을 이 환경 변수로 전달한다.
    # 지원 값 외가 들어오면 기본값(default)을 사용한다.
    env_val = os.getenv(f"{key.upper()}_SELECTION_MODE", default).strip().lower()
    if env_val in {"time", "random", "keyword"}:
        return env_val
    return default


def resolve_keyword_filters(key: str) -> List[str]:
    # <카테고리>_KEYWORDS 환경 변수에 콤마(,)로 구분된 키워드를 넣는다.
    # 예) AI 카테고리에 "openai"와 "llm"을 필터링: `export AI_KEYWORDS="openai,llm"`
    # daily-news.yml의 workflow_dispatch 입력이 동일 이름의 환경 변수로 채워져 여기에서 읽힌다.
    # 키워드는 대소문자 구분 없이 제목·본문에서 검색된다.
    raw = os.getenv(f"{key.upper()}_KEYWORDS", "").strip()
    if not raw:
        return []
    return [kw.strip() for kw in raw.split(",") if kw.strip()]


# --- 설정 ---
CATEGORIES: Dict[str, CategoryConfig] = {
    "ai": CategoryConfig(
        key="ai",
        display_name="AI",
        rss_feeds=[
            "https://www.aitimes.com/rss/allArticle.xml",
            "https://www.bloter.net/archives/category/ai/feed",
            "https://www.reddit.com/r/ArtificialInteligence/top/.rss?t=day",
            "https://www.techmeme.com/feed.xml",
        ],
        archive_dir="docs/ai/daily",
        index_path="docs/ai/index.html",
        fallback_image_url="https://placehold.co/800x420/111827/FFFFFF?text=AI+News",
        selection_mode=resolve_selection_mode("ai"),
        keyword_filters=resolve_keyword_filters("ai"),
    ),
    "xr": CategoryConfig(
        key="xr",
        display_name="XR",
        rss_feeds=[
            "https://www.roadtovr.com/feed/",
            "https://uploadvr.com/rss",
            "https://arinsider.co/feed/",
            "https://skarredghost.com/feed/",
        ],
        archive_dir="docs/xr/daily",
        index_path="docs/xr/index.html",
        selection_mode=resolve_selection_mode("xr"),
        keyword_filters=resolve_keyword_filters("xr"),
    ),
}

# Gemini 호출 간격 (무료 플랜이면 6~7초 이상 권장, 유료/여유 있으면 줄여도 됨)
REQUEST_INTERVAL_SECONDS = 2
HIGHLIGHT_COLOR = "#fff6b0"


# **텍스트** → 강조 색상(문구만) + 목록 처리
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

    if Translator is None:
        return title

    global _translator
    if _translator is None:
        _translator = Translator()

    try:
        result = _translator.translate(title, dest="ko")
        if result and result.text:
            return result.text
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
        if isinstance(content, dict):
            candidate = extract_from_html(content.get("value", ""))
        else:
            candidate = extract_from_html(getattr(content, "value", ""))
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


# 1) Gemini 요약 함수
def summarize(text: str, title: str, display_name: str) -> str:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])

    # 사용 중인 모델 (필요시 다른 ID로 교체)
    model = genai.GenerativeModel("gemini-2.5-flash-preview-09-2025")

    prompt = f"""
아래 {display_name} 관련 기사 내용을 5줄 이내 한국어로 핵심만 요약해줘.
가능하면 수치, 회사명, 핵심 이슈 위주로 하고, 각 줄은 불릿 기호 "□"으로 시작해줘.
핵심 키워드는 강조(**굵게**) 처리하되, URL이나 링크는 포함하지 마.

제목: {title}
내용:
{text[:2000]}
"""

    res = model.generate_content(prompt)
    return res.text.strip()


# 2) RSS → (여러 RSS 전체) → 시간/랜덤 정렬 → 상위 N개만 요약
def fetch_and_summarize(config: CategoryConfig):
    raw_items = []

    for feed_url in config.rss_feeds:
        d = feedparser.parse(feed_url)

        for entry in d.entries:
            title = getattr(entry, "title", "")
            link = getattr(entry, "link", "")
            content = getattr(entry, "summary", "") or getattr(
                entry, "description", ""
            )

            # 게시 시각(published) 또는 수정 시각(updated) 사용
            published = getattr(entry, "published_parsed", None) or getattr(
                entry, "updated_parsed", None
            )
            if published:
                ts = time.mktime(published)  # epoch time
            else:
                ts = 0  # 날짜 정보 없으면 가장 뒤로 밀림 (time 모드일 때)

            raw_items.append((ts, title, link, content, entry))

    keywords = [kw.lower() for kw in config.keyword_filters]

    if config.selection_mode == "keyword" and keywords:
        # 키워드 모드: 제목+본문에 키워드가 하나라도 포함된 기사만 남긴다.
        # 키워드는 resolve_keyword_filters()로 환경 변수에서 읽어온 리스트를 사용한다.
        raw_items = [
            item
            for item in raw_items
            if any(kw in ((item[1] or "") + " " + (item[3] or "")).lower() for kw in keywords)
        ]

    # 기사 정렬/선택 방식
    three_days_ago = time.time() - 3 * 24 * 60 * 60
    if config.selection_mode == "time":
        # 시간 모드: 게시 시각(ts) 내림차순으로 최신 기사부터 정렬
        raw_items.sort(key=lambda x: x[0], reverse=True)
    elif config.selection_mode == "random":
        # 랜덤 모드: 최근 3일 내 기사만 대상으로 무작위 섞기 (없으면 전체 사용)
        recent_items = [item for item in raw_items if item[0] and item[0] >= three_days_ago]
        candidate_items = recent_items if recent_items else raw_items
        random.shuffle(candidate_items)
        raw_items = candidate_items
    elif config.selection_mode == "keyword":
        # 키워드 모드: 필터링 후 최신 순 정렬 (키워드가 없으면 아래 else로 동일 처리)
        raw_items.sort(key=lambda x: x[0], reverse=True)
    else:
        raw_items.sort(key=lambda x: x[0], reverse=True)

    # 상위 N개만 선택
    selected = raw_items[: config.max_articles]

    summarized = []
    for idx, (ts, title, link, content, entry) in enumerate(selected):
        text_with_url = content + f"\n\n기사 URL: {link}"

        summary = summarize(text_with_url, title, config.display_name)
        summary = sanitize_summary(summary)
        image_url = extract_image_url(entry) or config.fallback_image_url

        summarized.append(
            {
                "title": title,
                "link": link,
                "summary": summary,
                "published_display": format_timestamp(ts),
                "source_name": extract_source_name(entry, link),
                "image_url": image_url,
            }
        )

        # 쿼터 보호용 딜레이
        time.sleep(REQUEST_INTERVAL_SECONDS)

    return summarized


# 3) 개별 실행(날짜+시간) 페이지 생성
def build_daily_page(articles, date_str: str, time_str: str, config: CategoryConfig) -> str:
    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append("<html lang='ko'>")
    parts.append("<head>")
    parts.append("  <meta charset='utf-8' />")
    parts.append(f"  <title>{config.display_name} News - {date_str} {time_str}</title>")
    parts.append(
        "  <meta name='viewport' content='width=device-width, initial-scale=1' />"
    )
    parts.append("  <style>")
    parts.append(
        "    body { font-family: 'Noto Sans KR', 'Pretendard', sans-serif; line-height: 1.7; margin: 1.5rem; background: #f9fafb; color: #0f172a; }"
    )
    parts.append("    h1 { margin-bottom: 0.25rem; }")
    parts.append("    .meta { color: #475569; margin-bottom: 1.25rem; }")
    parts.append(
        "    .nav { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1rem; }"
    )
    parts.append(
        "    .nav a { padding: 0.45rem 0.8rem; border: 1px solid #e5e7eb; border-radius: 8px; text-decoration: none; color: #0f172a; background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,0.04); font-weight: 600; }"
    )
    parts.append("    .articles { display: grid; gap: 1rem; }")
    parts.append(
        "    .article-card { background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 1.1rem 1.2rem; box-shadow: 0 10px 25px rgba(15,23,42,0.06); }"
    )
    parts.append("    .article-card h2 { margin: 0; font-size: 1.15rem; }")
    parts.append(
        "    .article-card h2 a { color: #0f172a; text-decoration: none; }"
    )
    parts.append(
        "    .article-card h2 a:hover { text-decoration: underline; }"
    )
    parts.append(
        "    .original-title { display: block; font-size: 0.9rem; color: #6b7280; margin-top: 4px; }"
    )
    parts.append(
        "    .article-meta { color: #475569; font-size: 0.95rem; margin: 0.5rem 0 0.75rem; display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }"
    )
    parts.append(
        "    .meta-pill { background: #eef2ff; color: #4338ca; padding: 0.25rem 0.6rem; border-radius: 999px; font-weight: 600; font-size: 0.9rem; }"
    )
    parts.append(
        "    .article-body { display: flex; gap: 0.85rem; align-items: flex-start; flex-wrap: wrap; }"
    )
    parts.append(
        "    .summary-column { flex: 1 1 0; min-width: 0; }"
    )
    parts.append(
        "    .article-image { flex: 0 1 320px; width: clamp(170px, 30vw, 320px); height: auto; max-height: 320px; object-fit: cover; border-radius: 10px; border: 1px solid #e5e7eb; margin-left: 0; align-self: flex-start; }"
    )
    parts.append("    .summary-list { margin: 0; padding-left: 1.15rem; color: #0f172a; }")
    parts.append("    .summary-list li { margin-bottom: 0.35rem; }")
    parts.append(
        "    .highlight { background-color: %s; padding: 3px 5px; border-radius: 4px; }"
        % HIGHLIGHT_COLOR
    )
    parts.append("    @media (max-width: 768px) {")
    parts.append("      .article-body { flex-direction: column; gap: 0.75rem; }")
    parts.append(
        "      .article-image { order: 2; width: clamp(160px, 75%, 260px); max-width: 260px; max-height: 220px; flex: 0 0 auto; align-self: flex-start; }"
    )
    parts.append("      .summary-column { width: 100%; }")
    parts.append("    }")
    parts.append("  </style>")
    parts.append("</head>")
    parts.append("<body>")
    parts.append("  <div class='nav'>")
    parts.append("    <a href='../../index.html'>🏠 홈으로</a>")
    parts.append("    <a href='../index.html'>📅 날짜별 목록</a>")
    parts.append("  </div>")
    parts.append(f"  <h1>{date_str} {config.display_name} News</h1>")
    parts.append(f"  <p class='meta'>Updated at {time_str} (KST)</p>")
    parts.append("  <section class='articles'>")

    for art in articles:
        summary_html = markdown_bold_to_highlight(art["summary"])
        display_title = translate_title_to_korean(art["title"])
        original_hint = (
            f"<span class='original-title'>원문 제목: {art['title']}</span>"
            if display_title != art["title"]
            else ""
        )

        parts.append("    <article class='article-card'>")
        parts.append(
            "      <h2>"
            f"<a href='{art['link']}' target='_blank'>{display_title}</a>"
            f"{original_hint}"
            "</h2>"
        )

        meta_bits = [bit for bit in [art.get("published_display"), art.get("source_name")] if bit]
        if meta_bits:
            extra_meta = " · ".join(meta_bits[1:]) if len(meta_bits) > 1 else ""
            extra_span = f"<span>{extra_meta}</span>" if extra_meta else ""
            parts.append(
                "      <p class='article-meta'>"
                f"<span class='meta-pill'>{meta_bits[0]}</span>"
                f"{extra_span}"
                "</p>"
            )

        if summary_html or art.get("image_url"):
            parts.append("      <div class='article-body'>")
            parts.append("        <div class='summary-column'>")
            if summary_html:
                parts.append(f"          {summary_html}")
            parts.append("        </div>")

            if art.get("image_url"):
                parts.append(
                    f"        <img src='{art['image_url']}' alt='기사 이미지' class='article-image' loading='lazy'/>"
                )

            parts.append("      </div>")
        parts.append("    </article>")

    parts.append("  </section>")
    parts.append("</body>")
    parts.append("</html>")

    return "\n".join(parts)


# 4) index.html 목록 페이지 재생성 (여러 번/하루 여러 회 실행 포함)
def collect_run_entries(config: CategoryConfig):
    os.makedirs(config.archive_dir, exist_ok=True)

    files = [f for f in os.listdir(config.archive_dir) if f.endswith(".html")]

    run_entries = []
    for fname in files:
        base = fname.replace(".html", "")
        date_str = base
        time_str = ""

        if "_" in base:
            date_part, time_part = base.split("_", 1)
            date_str = date_part
            if len(time_part) >= 6:
                hh = time_part[0:2]
                mm = time_part[2:4]
                ss = time_part[4:6]
                time_str = f"{hh}:{mm}:{ss}"
            else:
                time_str = time_part
        run_entries.append((base, date_str, time_str, fname))

    run_entries.sort(key=lambda x: x[0], reverse=True)
    return run_entries


def rebuild_index_html(config: CategoryConfig):
    run_entries = collect_run_entries(config)

    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append("<html lang='ko'>")
    parts.append("<head>")
    parts.append("  <meta charset='utf-8' />")
    parts.append(f"  <title>Daily {config.display_name} News Archive</title>")
    parts.append(
        "  <meta name='viewport' content='width=device-width, initial-scale=1' />"
    )
    parts.append("  <style>")
    parts.append(
        "    body { font-family: 'Noto Sans KR', 'Pretendard', sans-serif; margin: 1.25rem; line-height: 1.6; background: #f9fafb; color: #0f172a; }"
    )
    parts.append("    h1 { margin-bottom: 0.35rem; }")
    parts.append(
        "    .nav { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1rem; }"
    )
    parts.append(
        "    .nav a { padding: 0.45rem 0.85rem; border: 1px solid #e5e7eb; border-radius: 8px; text-decoration: none; color: #0f172a; background: #fff; font-weight: 600; box-shadow: 0 1px 2px rgba(0,0,0,0.04); }"
    )
    parts.append(
        "    .run-list { list-style: none; padding: 0; display: grid; gap: 0.75rem; margin-top: 1rem; }"
    )
    parts.append(
        "    .run-item { background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 0.9rem 1rem; box-shadow: 0 8px 18px rgba(15,23,42,0.05); }"
    )
    parts.append(
        "    .run-item a { color: #0f172a; text-decoration: none; font-weight: 700; }"
    )
    parts.append("    .run-item a:hover { text-decoration: underline; }")
    parts.append(
        "    .timestamp { color: #475569; font-size: 0.95rem; display: block; margin-top: 0.2rem; }"
    )
    parts.append("  </style>")
    parts.append("</head>")
    parts.append("<body>")
    parts.append("  <div class='nav'>")
    parts.append("    <a href='../index.html'>🏠 홈으로</a>")
    parts.append("  </div>")
    parts.append(f"  <h1>Daily {config.display_name} News Archive</h1>")
    parts.append(
        f"  <p>실행 시점(날짜+시간, KST)별로 저장된 {config.display_name} 기사 요약 목록입니다.</p>"
    )

    if not run_entries:
        parts.append("  <p>아직 저장된 뉴스가 없습니다.</p>")
    else:
        parts.append("  <ul class='run-list'>")
        for base, date_str, time_str, fname in run_entries:
            if time_str:
                label = f"{date_str} {time_str} {config.display_name} News"
            else:
                label = f"{date_str} {config.display_name} News"
            parts.append(
                "    <li class='run-item'>"
                f"<a href='daily/{fname}'>{label}</a>"
                f"<span class='timestamp'>원본 생성 시간: {date_str} {time_str or ''} (KST)</span>"
                "</li>"
            )
        parts.append("  </ul>")

    parts.append("</body>")
    parts.append("</html>")

    os.makedirs(os.path.dirname(config.index_path), exist_ok=True)
    with open(config.index_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


def build_root_index(categories: Dict[str, CategoryConfig]):
    categorized_runs = {cfg.key: collect_run_entries(cfg) for cfg in categories.values()}

    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append("<html lang='ko'>")
    parts.append("<head>")
    parts.append("  <meta charset='utf-8' />")
    parts.append("  <title>AI & XR News Archives</title>")
    parts.append("  <meta name='viewport' content='width=device-width, initial-scale=1' />")
    parts.append("  <style>")
    parts.append(
        "    body { font-family: 'Noto Sans KR', 'Pretendard', sans-serif; margin: 1.25rem; line-height: 1.6; background: #f9fafb; color: #0f172a; }"
    )
    parts.append("    h1 { margin-bottom: 0.5rem; }")
    parts.append("    .subtitle { color: #4b5563; margin-bottom: 1rem; }")
    parts.append("    .tabs { display: flex; gap: 0.5rem; margin-bottom: 1rem; flex-wrap: wrap; }")
    parts.append(
        "    .tab-btn { padding: 0.45rem 0.9rem; border: 1px solid #d1d5db; border-radius: 8px; background: #f3f4f6; cursor: pointer; font-weight: 600; }")
    parts.append(
        "    .tab-btn.active { background: #111827; color: #f9fafb; border-color: #111827; }"
    )
    parts.append("    .tab-panel { display: none; }")
    parts.append("    .tab-panel.active { display: block; }")
    parts.append(
        "    .panel-card { background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 1rem 1.1rem; box-shadow: 0 8px 18px rgba(15,23,42,0.05); }"
    )
    parts.append("    ul { padding-left: 1.1rem; margin: 0; }")
    parts.append("    li + li { margin-top: 0.35rem; }")
    parts.append("    .timestamp { color: #6b7280; font-size: 0.95rem; margin-left: 0.35rem; }")
    parts.append("    .archive-link { margin: 0 0 0.5rem; font-weight: 700; }")
    parts.append("  </style>")
    parts.append("</head>")
    parts.append("<body>")
    parts.append("  <h1>AI & XR Daily News Archives</h1>")
    parts.append("  <p class='subtitle'>탭을 눌러 AI/XR 뉴스를 구분해 확인하세요. 모든 시각은 한국 표준시(KST) 기준이며, 과거 실행 결과도 누적해 보여줍니다.</p>")

    parts.append("  <div class='tabs'>")
    for cfg in categories.values():
        parts.append(
            f"    <button class='tab-btn' data-target='{cfg.key}'>{cfg.display_name} 뉴스</button>"
        )
    parts.append("  </div>")

    for cfg in categories.values():
        runs = categorized_runs.get(cfg.key, [])
        parts.append(
            f"  <div class='tab-panel' id='{cfg.key}'>"
        )
        parts.append("    <div class='panel-card'>")
        parts.append(
            f"      <p class='archive-link'><a href='{cfg.key}/index.html'>{cfg.display_name} 아카이브 전체 보기 →</a></p>"
        )

        if not runs:
            parts.append("      <p>아직 저장된 뉴스가 없습니다.</p>")
        else:
            parts.append("      <ul>")
            for base, date_str, time_str, fname in runs:
                label = f"{date_str} {time_str} KST" if time_str else f"{date_str} KST"
                parts.append(
                    "        <li>"
                    f"<a href='{cfg.key}/daily/{fname}'>{cfg.display_name} 뉴스</a>"
                    f" <span class='timestamp'>{label}</span>"
                    "</li>"
                )
            parts.append("      </ul>")

        parts.append("    </div>")
        parts.append("  </div>")

    parts.append("  <script>")
    parts.append(
        "    const tabs = document.querySelectorAll('.tab-btn'); const panels = document.querySelectorAll('.tab-panel');"
    )
    parts.append(
        "    function activateTab(key) { panels.forEach(p => p.classList.toggle('active', p.id === key)); tabs.forEach(t => t.classList.toggle('active', t.dataset.target === key)); }"
    )
    parts.append(
        "    tabs.forEach(btn => btn.addEventListener('click', () => activateTab(btn.dataset.target)));"
    )
    parts.append("    if (tabs.length) { activateTab(tabs[0].dataset.target); }")
    parts.append("  </script>")
    parts.append("</body>")
    parts.append("</html>")

    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


# 5) main 실행 함수
def main():
    # GitHub Actions는 UTC이므로, UTC + 9시간 = KST
    now_utc = datetime.datetime.utcnow()
    now = now_utc + datetime.timedelta(hours=9)

    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    # 파일 이름용 ID (YYYY-MM-DD_HHMMSS, KST 기준)
    run_id = now.strftime("%Y-%m-%d_%H%M%S")

    for cfg in CATEGORIES.values():
        articles = fetch_and_summarize(cfg)
        daily_html = build_daily_page(articles, date_str, time_str, cfg)

        os.makedirs(cfg.archive_dir, exist_ok=True)
        daily_path = os.path.join(cfg.archive_dir, f"{run_id}.html")

        # 매 실행마다 새로운 파일 생성
        with open(daily_path, "w", encoding="utf-8") as f:
            f.write(daily_html)

        rebuild_index_html(cfg)

    build_root_index(CATEGORIES)


if __name__ == "__main__":
    main()
