import os
import datetime
import feedparser
import google.generativeai as genai

# --- 설정 ---
RSS_FEEDS = [
    "https://www.aitimes.com/rss/allArticle.xml",
    "https://www.bloter.net/archives/category/ai/feed",
    "https://venturebeat.com/category/ai/feed/",
]
MAX_ARTICLES = 5  # 하루에 요약할 기사 수
ARCHIVE_DIR = "docs/daily"
INDEX_PATH = "docs/index.html"


# 1) Gemini 요약 함수
def summarize(text: str, title: str) -> str:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-1.5-pro")

    prompt = f"""
아래 AI 관련 기사 내용을 5줄 이내 한국어로 핵심만 요약해줘.
가능하면 수치, 회사명, 핵심 이슈 위주로.

제목: {title}
내용:
{text[:2000]}
"""

    res = model.generate_content(prompt)
    return res.text.strip()


# 2) RSS에서 기사 가져와 요약 리스트 만들기
def fetch_and_summarize():
    items = []

    for feed_url in RSS_FEEDS:
        d = feedparser.parse(feed_url)
        for entry in d.entries[:MAX_ARTICLES]:
            title = entry.title
            link = entry.link
            content = getattr(entry, "summary", "")
            items.append((title, link, content))

    # 여러 RSS 합쳐서 앞에서 MAX_ARTICLES개만 사용
    items = items[:MAX_ARTICLES]

    summarized = []
    for title, link, content in items:
        summary = summarize(content, title)
        summarized.append({
            "title": title,
            "link": link,
            "summary": summary
        })

    return summarized


# 3) "하루치 기사 페이지" HTML 생성
def build_daily_page(articles, date_str: str, time_str: str) -> str:
    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append("<html lang='ko'>")
    parts.append("<head>")
    parts.append("  <meta charset='utf-8' />")
    parts.append(f"  <title>AI News - {date_str}</title>")
    parts.append("  <meta name='viewport' content='width=device-width, initial-scale=1' />")
    parts.append("</head>")
    parts.append("<body>")
    parts.append(f"  <h1>{date_str} AI News</h1>")
    parts.append(f"  <p>Updated at {time_str}</p>")
    parts.append("  <p><a href='../index.html'>← 전체 날짜 목록으로 돌아가기</a></p>")
    parts.append("  <hr/>")
    parts.append("  <ul>")

    for art in articles:
        parts.append("    <li style='margin-bottom:1.5rem;'>")
        parts.append(f"      <h2><a href='{art['link']}' target='_blank'>{art['title']}</a></h2>")
        parts.append(f"      <p>{art['summary'].replace('\n', '<br/>')}</p>")
        parts.append("    </li>")

    parts.append("  </ul>")
    parts.append("</body>")
    parts.append("</html>")

    return "\n".join(parts)


# 4) index.html (목록 페이지) 생성/갱신
def rebuild_index_html():
    os.makedirs(ARCHIVE_DIR, exist_ok=True)

    # daily 폴더 내의 html 파일 목록
    files = [f for f in os.listdir(ARCHIVE_DIR) if f.endswith(".html")]

    # 파일명에서 날짜 추출 (예: 2025-12-01.html → 2025-12-01)
    date_file_pairs = []
    for fname in files:
        date_str = fname.replace(".html", "")
        date_file_pairs.append((date_str, fname))

    # 날짜 내림차순 정렬 (최신이 위로)
    date_file_pairs.sort(key=lambda x: x[0], reverse=True)

    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append("<html lang='ko'>")
    parts.append("<head>")
    parts.append("  <meta charset='utf-8' />")
    parts.append("  <title>Daily AI News Archive</title>")
    parts.append("  <meta name='viewport' content='width=device-width, initial-scale=1' />")
    parts.append("</head>")
    parts.append("<body>")
    parts.append("  <h1>Daily AI News Archive</h1>")
    parts.append("  <p>날짜별로 저장된 AI 기사 요약 목록입니다.</p>")
    parts.append("  <hr/>")

    if not date_file_pairs:
        parts.append("  <p>아직 저장된 뉴스가 없습니다.</p>")
    else:
        parts.append("  <ul>")
        for date_str, fname in date_file_pairs:
            parts.append(
                f"    <li><a href='daily/{fname}'>{date_str} AI News</a></li>"
            )
        parts.append("  </ul>")

    parts.append("</body>")
    parts.append("</html>")

    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


# 5) 메인 실행
def main():
    today = datetime.date.today().strftime("%Y-%m-%d")
    now_time = datetime.datetime.now().strftime("%H:%M")

    articles = fetch_and_summarize()
    daily_html = build_daily_page(articles, today, now_time)

    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    daily_path = os.path.join(ARCHIVE_DIR, f"{today}.html")

    # 날짜별 페이지 저장 (같은 날 여러 번 실행되면 덮어씀)
    with open(daily_path, "w", encoding="utf-8") as f:
        f.write(daily_html)

    # index.html 목록 페이지 재생성
    os.makedirs("docs", exist_ok=True)
    rebuild_index_html()


if __name__ == "__main__":
    main()
