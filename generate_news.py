import os
import time
import datetime
import feedparser
import google.generativeai as genai
import re
import random
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List

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
    display_order: str = "time"  # "time" or "random"


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
    ),
}

# Gemini 호출 간격 (무료 플랜이면 6~7초 이상 권장, 유료/여유 있으면 줄여도 됨)
REQUEST_INTERVAL_SECONDS = 2
HIGHLIGHT_COLOR = "#fff6b0"


# **텍스트** → 노란색 강조 span + 줄바꿈 처리
def markdown_bold_to_highlight(html_text: str) -> str:
    """
    요약문 안의 **텍스트**를
    <span style='background-color: yellow;'>텍스트</span>
    로 바꾼 뒤, 줄바꿈(\n)을 <br/>로 변환
    """

    lines = []

    for raw_line in html_text.splitlines():
        # **...** → <strong>...</strong>
        converted = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", raw_line)

        # 문장 단위로 옅은 노란색 배경을 적용
        wrapped = (
            f"<span class='highlight-line' style='background-color: {HIGHLIGHT_COLOR};"
            " padding: 4px 6px; border-radius: 4px; display: inline-block;'>"
            f"{converted.strip()}"
            "</span>"
        )
        lines.append(wrapped)

    # 줄바꿈을 <br/>로 변환
    return "<br/>".join(lines)


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


# 1) Gemini 요약 함수
def summarize(text: str, title: str, display_name: str) -> str:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])

    # 사용 중인 모델 (필요시 다른 ID로 교체)
    model = genai.GenerativeModel("gemini-2.5-flash-preview-09-2025")

    prompt = f"""
아래 {display_name} 관련 기사 내용을 5줄 이내 한국어로 핵심만 요약해줘.
가능하면 수치, 회사명, 핵심 이슈 위주로 하고, 각 줄은 불릿 기호 "□"으로 시작해줘.
핵심 키워드는 강조(**굵게**) 처리해줘.
마지막 줄에는 "URL: ... / 출처: ..." 형식으로 기사 URL과 출처를 명시해줘.

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

            raw_items.append((ts, title, link, content))

    # 기사 정렬/선택 방식
    if config.display_order == "time":
        # 최신 기사 순으로 정렬 (ts 내림차순)
        raw_items.sort(key=lambda x: x[0], reverse=True)
    elif config.display_order == "random":
        random.shuffle(raw_items)
    else:
        # 잘못된 설정이면 기본은 time
        raw_items.sort(key=lambda x: x[0], reverse=True)

    # 상위 N개만 선택
    selected = raw_items[: config.max_articles]

    summarized = []
    for idx, (ts, title, link, content) in enumerate(selected):
        text_with_url = content + f"\n\n기사 URL: {link}"

        summary = summarize(text_with_url, title, config.display_name)
        summarized.append(
            {
                "title": title,
                "link": link,
                "summary": summary,
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
        "    body { font-family: 'Noto Sans KR', 'Pretendard', sans-serif; line-height: 1.6; margin: 1.5rem; }"
    )
    parts.append("    h1 { margin-bottom: 0.4rem; }")
    parts.append("    .meta { color: #4b5563; margin-bottom: 1rem; }")
    parts.append("    .article { margin-bottom: 1.75rem; }")
    parts.append("    .article h2 { margin: 0 0 0.35rem; }")
    parts.append("    .original-title { display: block; font-size: 0.9rem; color: #6b7280; margin-top: 4px; }")
    parts.append(
        "    .highlight-line { background-color: %s; padding: 4px 6px; border-radius: 4px; display: inline-block; margin: 0.15rem 0; }"
        % HIGHLIGHT_COLOR
    )
    parts.append("  </style>")
    parts.append("</head>")
    parts.append("<body>")
    parts.append(f"  <h1>{date_str} {config.display_name} News</h1>")
    parts.append(f"  <p class='meta'>Updated at {time_str} (KST)</p>")
    parts.append(
        "  <p><a href='../index.html'>← 전체 날짜/시간 목록으로 돌아가기</a></p>"
    )
    parts.append("  <hr/>")
    parts.append("  <ul>")

    for art in articles:
        summary_html = markdown_bold_to_highlight(art["summary"])
        display_title = translate_title_to_korean(art["title"])
        original_hint = (
            f"<span class='original-title'>원문 제목: {art['title']}</span>"
            if display_title != art["title"]
            else ""
        )

        parts.append("    <li class='article'>")
        parts.append(
            "      <h2>"
            f"<a href='{art['link']}' target='_blank'>{display_title}</a>"
            f"{original_hint}"
            "</h2>"
        )
        parts.append(f"      <p>{summary_html}</p>")
        parts.append("    </li>")

    parts.append("  </ul>")
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
    parts.append("</head>")
    parts.append("<body>")
    parts.append(f"  <h1>Daily {config.display_name} News Archive</h1>")
    parts.append(
        f"  <p>실행 시점(날짜+시간, KST)별로 저장된 {config.display_name} 기사 요약 목록입니다.</p>"
    )
    parts.append("  <hr/>")

    if not run_entries:
        parts.append("  <p>아직 저장된 뉴스가 없습니다.</p>")
    else:
        parts.append("  <ul>")
        for base, date_str, time_str, fname in run_entries:
            if time_str:
                label = f"{date_str} {time_str} {config.display_name} News"
            else:
                label = f"{date_str} {config.display_name} News"
            parts.append(f"    <li><a href='daily/{fname}'>{label}</a></li>")
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
    parts.append("    body { font-family: 'Noto Sans KR', 'Pretendard', sans-serif; margin: 1.25rem; line-height: 1.6; }")
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
    parts.append("    ul { padding-left: 1.1rem; }")
    parts.append("    li + li { margin-top: 0.35rem; }")
    parts.append("    .timestamp { color: #6b7280; font-size: 0.95rem; margin-left: 0.35rem; }")
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
        parts.append(
            f"    <p><a href='{cfg.key}/index.html'>{cfg.display_name} 아카이브 전체 보기 →</a></p>"
        )

        if not runs:
            parts.append("    <p>아직 저장된 뉴스가 없습니다.</p>")
        else:
            parts.append("    <ul>")
            for base, date_str, time_str, fname in runs:
                label = f"{date_str} {time_str} KST" if time_str else f"{date_str} KST"
                parts.append(
                    "      <li>"
                    f"<a href='{cfg.key}/daily/{fname}'>{cfg.display_name} 뉴스</a>"
                    f" <span class='timestamp'>{label}</span>"
                    "</li>"
                )
            parts.append("    </ul>")

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
