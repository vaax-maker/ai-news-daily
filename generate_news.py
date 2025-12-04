import os
import time
import datetime
import feedparser
import google.generativeai as genai
import re
import random
from dataclasses import dataclass
from typing import Dict, List

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


# **텍스트** → 노란색 강조 span + 줄바꿈 처리
def markdown_bold_to_highlight(html_text: str) -> str:
    """
    요약문 안의 **텍스트**를
    <span style='background-color: yellow;'>텍스트</span>
    로 바꾼 뒤, 줄바꿈(\n)을 <br/>로 변환
    """

    def repl(match: re.Match) -> str:
        inner = match.group(1)
        return f"<span style='background-color: yellow;'>{inner}</span>"

    # **...** → <span ...>...</span>
    converted = re.sub(r"\*\*(.+?)\*\*", repl, html_text)

    # 줄바꿈을 <br/>로
    converted = converted.replace("\n", "<br/>")
    return converted


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
    parts.append("</head>")
    parts.append("<body>")
    parts.append(f"  <h1>{date_str} {config.display_name} News</h1>")
    parts.append(f"  <p>Updated at {time_str} (KST)</p>")
    parts.append(
        "  <p><a href='../index.html'>← 전체 날짜/시간 목록으로 돌아가기</a></p>"
    )
    parts.append("  <hr/>")
    parts.append("  <ul>")

    for art in articles:
        summary_html = markdown_bold_to_highlight(art["summary"])
        parts.append("    <li style='margin-bottom:1.5rem;'>")
        parts.append(
            f"      <h2><a href='{art['link']}' target='_blank'>{art['title']}</a></h2>"
        )
        parts.append(f"      <p>{summary_html}</p>")
        parts.append("    </li>")

    parts.append("  </ul>")
    parts.append("</body>")
    parts.append("</html>")

    return "\n".join(parts)


# 4) index.html 목록 페이지 재생성 (여러 번/하루 여러 회 실행 포함)
def rebuild_index_html(config: CategoryConfig):
    os.makedirs(config.archive_dir, exist_ok=True)

    files = [f for f in os.listdir(config.archive_dir) if f.endswith(".html")]

    # 파일명: YYYY-MM-DD_HHMMSS.html
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

    # base(= 날짜+시간 문자열) 기준 내림차순 정렬 → 최신 실행이 위로
    run_entries.sort(key=lambda x: x[0], reverse=True)

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
    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append("<html lang='ko'>")
    parts.append("<head>")
    parts.append("  <meta charset='utf-8' />")
    parts.append("  <title>AI & XR News Archives</title>")
    parts.append("  <meta name='viewport' content='width=device-width, initial-scale=1' />")
    parts.append("</head>")
    parts.append("<body>")
    parts.append("  <h1>AI & XR Daily News Archives</h1>")
    parts.append(
        "  <p>카테고리별 최신 실행 결과를 확인하려면 아래 링크를 클릭하세요.</p>"
    )
    parts.append("  <ul>")

    for cfg in categories.values():
        parts.append(
            f"    <li><a href='{cfg.key}/index.html'>{cfg.display_name} 뉴스 아카이브</a></li>"
        )

    parts.append("  </ul>")
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
