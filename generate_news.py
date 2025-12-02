import os
import time
import datetime
import feedparser
import google.generativeai as genai

# --- 설정 ---
RSS_FEEDS = [
    "https://www.aitimes.com/rss/allArticle.xml",
    "https://www.bloter.net/archives/category/ai/feed",
    "https://venturebeat.com/category/ai/feed/",
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://www.technologyreview.com/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://news.hada.io/rss/news",
    "https://news.ycombinator.com/rss",
]

MAX_ARTICLES = 15
ARCHIVE_DIR = "docs/daily"
INDEX_PATH = "docs/index.html"


# 1) Gemini 요약 함수
def summarize(text: str, title: str) -> str:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])

    # 사용 가능한 모델 ID로 맞춰 사용 (예: gemini-1.5-flash)
    model = genai.GenerativeModel("gemini-2.5-flash-preview-09-2025")

    prompt = f"""
아래 AI 관련 기사 내용을 5줄 이내 한국어로 핵심만 요약해줘.
가능하면 수치, 회사명, 핵심 이슈 위주로 하고, 불릿"□"으로 시작하고 핵심내용은 강조처리해줘
끝부분에는 기사 URL과 출처를 명시해줘

제목: {title}
내용:
{text[:2000]}
"""

    res = model.generate_content(prompt)
    return res.text.strip()


# 2) RSS → 요약 리스트 만들기
def fetch_and_summarize():
    items = []

    for feed_url in RSS_FEEDS:
        d = feedparser.parse(feed_url)
        for entry in d.entries[:MAX_ARTICLES]:
            title = entry.title
            link = entry.link
            content = getattr(entry, "summary", "")
            items.append((title, link, content))

    items = items[:MAX_ARTICLES]

    summarized = []
    for idx, (title, link, content) in enumerate(items):
        summary = summarize(content, title)
        summarized.append(
            {
                "title": title,
                "link": link,
                "summary": summary,
            }
        )
        # 한도 보호용 딜레이 (필요시)
        time.sleep(2)  # 2초씩 쉬면 20개 기준 40초 → 분당 호출 분산

    return summarized


# 3) 개별 실행(날짜+시간) 페이지 생성
def build_daily_page(articles, date_str: str, time_str: str) -> str:
    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append("<html lang='ko'>")
    parts.append("<head>")
    parts.append("  <meta charset='utf-8' />")
    parts.append(f"  <title>AI News - {date_str} {time_str}</title>")
    parts.append(
        "  <meta name='viewport' content='width=device-width, initial-scale=1' />"
    )
    parts.append("</head>")
    parts.append("<body>")
    parts.append(f"  <h1>{date_str} AI News</h1>")
    parts.append(f"  <p>Updated at {time_str}</p>")
    parts.append(
        "  <p><a href='../index.html'>← 전체 날짜/시간 목록으로 돌아가기</a></p>"
    )
    parts.append("  <hr/>")
    parts.append("  <ul>")

    for art in articles:
        summary_html = art["summary"].replace("\n", "<br/>")
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
def rebuild_index_html():
    os.makedirs(ARCHIVE_DIR, exist_ok=True)

    files = [f for f in os.listdir(ARCHIVE_DIR) if f.endswith(".html")]

    # 파일명: YYYY-MM-DD_HHMMSS.html
    run_entries = []
    for fname in files:
        base = fname.replace(".html", "")
        # 기본값
        date_str = base
        time_str = ""

        if "_" in base:
            date_part, time_part = base.split("_", 1)
            date_str = date_part
            # HHMMSS → HH:MM:SS 형태로
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
    parts.append("  <title>Daily AI News Archive</title>")
    parts.append(
        "  <meta name='viewport' content='width=device-width, initial-scale=1' />"
    )
    parts.append("</head>")
    parts.append("<body>")
    parts.append("  <h1>Daily AI News Archive</h1>")
    parts.append(
        "  <p>실행 시점(날짜+시간)별로 저장된 AI 기사 요약 목록입니다.</p>"
    )
    parts.append("  <hr/>")

    if not run_entries:
        parts.append("  <p>아직 저장된 뉴스가 없습니다.</p>")
    else:
        parts.append("  <ul>")
        for base, date_str, time_str, fname in run_entries:
            if time_str:
                label = f"{date_str} {time_str} AI News"
            else:
                label = f"{date_str} AI News"
            parts.append(f"    <li><a href='daily/{fname}'>{label}</a></li>")
        parts.append("  </ul>")

    parts.append("</body>")
    parts.append("</html>")

    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


# 5) main 실행 함수
def main():
    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    # 파일 이름용 ID (YYYY-MM-DD_HHMMSS) → 같은 날 여러 번 실행해도 매번 다른 파일
    run_id = now.strftime("%Y-%m-%d_%H%M%S")

    articles = fetch_and_summarize()
    daily_html = build_daily_page(articles, date_str, time_str)

    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    daily_path = os.path.join(ARCHIVE_DIR, f"{run_id}.html")

    # 매 실행마다 새로운 파일 생성
    with open(daily_path, "w", encoding="utf-8") as f:
        f.write(daily_html)

    os.makedirs("docs", exist_ok=True)
    rebuild_index_html()


if __name__ == "__main__":
    main()
