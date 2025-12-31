import sys
import os
import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import load_categories
from src.generators.html import render_mobile_landing
from src.utils.common import parse_article_datetime
from bs4 import BeautifulSoup

def parse_existing_articles(html_path):
    if not os.path.exists(html_path):
        return []
        
    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")
        
    parsed = []
    # Similar to main.py's parse_existing_articles but focused on simple preview info
    # We need title, link, source_name, date/timestamp
    
    # Try parsing daily page format
    news_articles = soup.select("article.news-item")
    for article in news_articles:
        title_el = article.select_one(".news-title a")
        if not title_el: continue
        
        parsed.append({
            "title": title_el.get_text(strip=True),
            "link": title_el.get("href", ""),
            "source_name": article.select_one(".source-link").get_text(strip=True) if article.select_one(".source-link") else "",
            # We don't easily have timestamp from HTML unless we parse published-date text
            # But for visual check of spacing, this is fine.
            # Timestamp will be missing, so no NEW badge, which is correct for old data.
            "timestamp": 0 
        })
    return parsed

def get_latest_file(archive_dir):
    if not os.path.isdir(archive_dir): return None
    files = sorted([f for f in os.listdir(archive_dir) if f.endswith(".html")], reverse=True)
    if not files: return None
    return os.path.join(archive_dir, files[0])

def main():
    categories = load_categories()
    
    data = {"ai": [], "xr": [], "gov": [], "links": {}}
    
    # AI
    ai_file = get_latest_file(categories["ai"].archive_dir)
    if ai_file:
        data["ai"] = parse_existing_articles(ai_file)[:10]
        data["links"]["ai"] = "ai/index.html"
        
    # XR
    xr_file = get_latest_file(categories["xr"].archive_dir)
    if xr_file:
        data["xr"] = parse_existing_articles(xr_file)[:10]
        data["links"]["xr"] = "xr/index.html"
        
    # Gov - simplified, just link
    data["links"]["gov"] = "gov/index.html"
    
    print("Regenerating docs/briefing.html with REAL data...")
    html = render_mobile_landing(data["ai"], data["xr"], data["gov"], data["links"])
    
    with open("docs/briefing.html", "w", encoding="utf-8") as f:
        f.write(html)
        
    print("Done.")

if __name__ == "__main__":
    main()
