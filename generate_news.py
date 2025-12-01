import os
import datetime
import feedparser
import google.generativeai as genai

RSS_FEEDS = [
    "https://www.aitimes.com/rss/allArticle.xml",
    "https://www.bloter.net/archives/category/ai/feed",
    "https://venturebeat.com/category/ai/feed/", "https://news.mit.edu/rss/feed"
]

MAX_ARTICLES = 10  # 하루에 요약할 기사 수 (원하는대로 변경)

def summarize(text: str, title: str) -> str:
    genai.configure(api_key=os.environ["AIzaSyBZ-xeEfA0mqOCInqh3ib7jqfiuVbIW-tQ"])
    model = genai.GenerativeModel("gemini-2.5-flash-preview-09-2025")

    prompt = f"""
    아래 AI 관련 기사 내용을 5줄 이내 한국어로 핵심만 요약해줘.
    가능하면 수치, 회사명, 핵심 이슈 위주로.

    제목: {title}
    내용:
    {text[:2000]}  # 너무 길면 잘라서 보냄
    """

    res = model.generate_content(prompt)
    return res.text.strip()

def fetch_and_summarize():
    items = []

    for feed_url in RSS_FEEDS:
        d = feedparser.parse(feed_url)
        for entry in d.entries[:MAX_ARTICLES]:
            title = entry.title
            link = entry.link
            # RSS description/summary만 사용 (간단 버전)
            content = getattr(entry, "summary", "")
            items.append((title, link, content))

    # 중복 제거/정렬 등 필요 시 처리
    # 여기서는 앞에서 MAX_ARTICLES만 사용
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

def build_html(articles):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    # 심플한 HTML (나중에 스타일링 추가 가능)
    html_parts = [
        "<!DOCTYPE html>",
        "<html lang='ko'>",
        "<head>",
        "  <meta charset='utf-8' />",
        "  <title>Daily AI News</title>",
        "  <meta name='viewport' content='width=device-width, initial-scale=1' />",
        "</head>",
        "<body>",
        f"<h1>Daily AI News</h1>",
        f"<p>Last update: {now}</p>",
        "<hr/>"
    ]

    for art in articles:
        html_parts.append("<section style='margin-bottom: 2rem;'>")
        html_parts.append(f"<h2><a href='{art['link']}' target='_blank'>{art['title']}</a></h2>")
        html_parts.append(f"<p>{art['summary'].replace('\n', '<br/>')}</p>")
        html_parts.append("</section>")

    html_parts.append("</body></html>")
    return "\n".join(html_parts)

def main():
    articles = fetch_and_summarize()
    html = build_html(articles)

    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    main()
