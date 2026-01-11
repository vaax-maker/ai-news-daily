#!/usr/bin/env python3
"""
Generate daily briefing page with Key Message and AI/XR articles.
Combines 8AM and 4PM runs into a single daily briefing.
"""
import os
import sys
import datetime
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import load_categories
from src.generators.html import render_daily_briefing, render_briefing_archive
from src.generators.llm import generate_key_message_and_keywords
from src.utils.wordcloud_generator import extract_weekly_keywords, create_wordcloud_image
from src.utils.common import get_kst_now
from bs4 import BeautifulSoup


def parse_articles_from_html(html_path: str) -> list:
    """Parse articles from a daily archive HTML file."""
    if not os.path.exists(html_path):
        return []
    
    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")
    
    articles = []
    for article in soup.select("article.news-item"):
        title_el = article.select_one(".news-title a")
        summary_el = article.select_one(".news-summary")
        source_el = article.select_one(".source-link")
        
        if not title_el:
            continue
        
        articles.append({
            "title": title_el.get_text(strip=True),
            "link": title_el.get("href", ""),
            "summary_html": summary_el.decode_contents().strip() if summary_el else "",
            "source_name": source_el.get_text(strip=True) if source_el else "",
            "is_new": True
        })
    
    return articles


def get_today_articles(category_key: str, run_type: str = "morning") -> list:
    """Get articles from today's archive for a specific category and run type."""
    categories = load_categories()
    if category_key not in categories:
        return []
    
    config = categories[category_key]
    archive_dir = config.archive_dir
    
    if not os.path.isdir(archive_dir):
        return []
    
    now = get_kst_now()
    date_str = now.strftime("%Y-%m-%d")
    
    # Find files for today
    files = sorted([f for f in os.listdir(archive_dir) if f.startswith(date_str) and f.endswith(".html")])
    
    if not files:
        return []
    
    # Morning = first file, Afternoon = second file (if exists)
    if run_type == "morning" and files:
        return parse_articles_from_html(os.path.join(archive_dir, files[0]))
    elif run_type == "afternoon" and len(files) > 1:
        return parse_articles_from_html(os.path.join(archive_dir, files[1]))
    elif run_type == "afternoon" and len(files) == 1:
        # If only one file, check if it's afternoon run
        now_hour = now.hour
        if now_hour >= 12:
            return parse_articles_from_html(os.path.join(archive_dir, files[0]))
    
    return []


def load_briefing_state(state_file: str) -> dict:
    """Load previous briefing state (morning articles)."""
    if os.path.exists(state_file):
        with open(state_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"morning_ai": [], "morning_xr": [], "date": ""}


def save_briefing_state(state_file: str, state: dict):
    """Save briefing state for combining with afternoon run."""
    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def generate_briefing():
    """Generate daily briefing page."""
    now = get_kst_now()
    date_str = now.strftime("%Y-%m-%d")
    date_display = now.strftime("%Y년 %m월 %d일")
    is_afternoon = now.hour >= 12
    
    briefing_dir = "docs/briefing"
    os.makedirs(briefing_dir, exist_ok=True)
    
    state_file = os.path.join(briefing_dir, ".state.json")
    
    # Determine run type
    if is_afternoon:
        run_type = "afternoon"
        print(f"[Briefing] Afternoon run ({now.strftime('%H:%M')})")
    else:
        run_type = "morning"
        print(f"[Briefing] Morning run ({now.strftime('%H:%M')})")
    
    # Load previous state
    state = load_briefing_state(state_file)
    
    # Reset state if different day
    if state.get("date") != date_str:
        state = {"morning_ai": [], "morning_xr": [], "date": date_str}
    
    # Get current articles
    categories = load_categories()
    
    if run_type == "morning":
        # Morning run: fetch and save
        ai_file = None
        xr_file = None
        
        if "ai" in categories and os.path.isdir(categories["ai"].archive_dir):
            files = sorted([f for f in os.listdir(categories["ai"].archive_dir) 
                          if f.startswith(date_str) and f.endswith(".html")])
            if files:
                ai_file = os.path.join(categories["ai"].archive_dir, files[0])
        
        if "xr" in categories and os.path.isdir(categories["xr"].archive_dir):
            files = sorted([f for f in os.listdir(categories["xr"].archive_dir) 
                          if f.startswith(date_str) and f.endswith(".html")])
            if files:
                xr_file = os.path.join(categories["xr"].archive_dir, files[0])
        
        morning_ai = parse_articles_from_html(ai_file) if ai_file else []
        morning_xr = parse_articles_from_html(xr_file) if xr_file else []
        
        # Save state for afternoon
        state["morning_ai"] = morning_ai
        state["morning_xr"] = morning_xr
        state["date"] = date_str
        save_briefing_state(state_file, state)
        
        afternoon_ai = []
        afternoon_xr = []
        
    else:
        # Afternoon run: load morning state and get current
        morning_ai = state.get("morning_ai", [])
        morning_xr = state.get("morning_xr", [])
        
        # Get afternoon articles (latest files)
        ai_file = None
        xr_file = None
        
        if "ai" in categories and os.path.isdir(categories["ai"].archive_dir):
            files = sorted([f for f in os.listdir(categories["ai"].archive_dir) 
                          if f.startswith(date_str) and f.endswith(".html")], reverse=True)
            if files:
                ai_file = os.path.join(categories["ai"].archive_dir, files[0])
        
        if "xr" in categories and os.path.isdir(categories["xr"].archive_dir):
            files = sorted([f for f in os.listdir(categories["xr"].archive_dir) 
                          if f.startswith(date_str) and f.endswith(".html")], reverse=True)
            if files:
                xr_file = os.path.join(categories["xr"].archive_dir, files[0])
        
        afternoon_ai = parse_articles_from_html(ai_file) if ai_file else []
        afternoon_xr = parse_articles_from_html(xr_file) if xr_file else []
        
        # Remove duplicates (articles in morning)
        morning_links = {a.get("link") for a in morning_ai + morning_xr}
        afternoon_ai = [a for a in afternoon_ai if a.get("link") not in morning_links]
        afternoon_xr = [a for a in afternoon_xr if a.get("link") not in morning_links]
    
    # Generate Key Message and Keywords (unified LLM call)
    print("[Briefing] Generating Key Message and Keywords...")
    all_articles = afternoon_ai + afternoon_xr + morning_ai + morning_xr
    result = generate_key_message_and_keywords(
        afternoon_ai + morning_ai,  # All AI articles
        afternoon_xr + morning_xr   # All XR articles
    )
    key_message = result["key_message"]
    briefing_keywords = result["keywords"]
    print(f"[Briefing] Key Message: {key_message[:100]}...")
    print(f"[Briefing] Keywords extracted: {len(briefing_keywords)}")
    
    # Save keywords for wordcloud (legacy, kept for reference if needed)
    keywords_path = "data/briefing_keywords.json"
    os.makedirs(os.path.dirname(keywords_path), exist_ok=True)
    with open(keywords_path, "w", encoding="utf-8") as f:
        json.dump({"keywords": briefing_keywords, "date": now.strftime("%Y-%m-%d")}, f, ensure_ascii=False, indent=2)

    # Save Key Message for Dashboard (New)
    key_message_path = "data/latest_key_message.json"
    with open(key_message_path, "w", encoding="utf-8") as f:
        json.dump({"key_message": key_message, "date": now.strftime("%Y-%m-%d")}, f, ensure_ascii=False, indent=2)
    print(f"[Briefing] Saved Key Message to {key_message_path}")

    # WordCloud Generation Disabled (Replaced by Key Message on Dashboard)
    wordcloud_rel_path = None
    # print("[Briefing] Generating WordCloud image...")
    # ... (Logic removed/commented out) ...

    
    # Fetch Government Projects (new)
    from src.fetchers.gov import fetch_gov_announcements
    print("[Briefing] Fetching government announcements...")
    raw_gov_items = fetch_gov_announcements(limit=50)
    
    # Filter for recent items (last 3 days to cover weekends)
    gov_items = []
    threshold_date = (now - datetime.timedelta(days=3)).strftime("%Y-%m-%d")
    today_str = now.strftime("%Y-%m-%d")
    
    for item in raw_gov_items:
        if item.get("date", "") >= threshold_date:
            # Set is_new flag for today's items
            item["is_new"] = (item.get("date") == today_str)
            gov_items.append(item)
            
    # Limit to top 10 after filtering
    gov_items = gov_items[:10]
    print(f"[Briefing] Found {len(gov_items)} recent government items.")
    
    # Render briefing page
    html = render_daily_briefing(
        key_message=key_message,
        morning_ai=morning_ai,
        morning_xr=morning_xr,
        afternoon_ai=afternoon_ai,
        afternoon_xr=afternoon_xr,
        gov_items=gov_items,
        date_display=date_display,
        wordcloud_image=wordcloud_rel_path
    )
    
    # Save briefing file
    briefing_filename = f"{date_str.replace('-', '')}.html"
    briefing_path = os.path.join(briefing_dir, briefing_filename)
    
    with open(briefing_path, "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"[Briefing] Saved: {briefing_path}")
    print(f"[Briefing] Articles: Morning AI={len(morning_ai)}, XR={len(morning_xr)}, Afternoon AI={len(afternoon_ai)}, XR={len(afternoon_xr)}")
    
    # Update briefing index
    update_briefing_archive(briefing_dir)
    
    # Also update main briefing.html (at docs root level, needs root_path=".")
    main_briefing = "docs/briefing.html"
    html_root = render_daily_briefing(
        key_message=key_message,
        morning_ai=morning_ai,
        morning_xr=morning_xr,
        afternoon_ai=afternoon_ai,
        afternoon_xr=afternoon_xr,
        gov_items=gov_items,
        date_display=date_display,
        root_path="."  # docs/briefing.html -> root is .
    )
    with open(main_briefing, "w", encoding="utf-8") as f:
        f.write(html_root)
    print(f"[Briefing] Updated: {main_briefing}")
    
    return briefing_path


def update_briefing_archive(briefing_dir: str):
    """Update the briefing archive index page."""
    entries = []
    today_str = get_kst_now().strftime("%Y%m%d")
    
    weekday_map = {0:'월', 1:'화', 2:'수', 3:'목', 4:'금', 5:'토', 6:'일'}
    
    for filename in sorted(os.listdir(briefing_dir), reverse=True):
        if not filename.endswith(".html") or filename == "index.html":
            continue
        
        date_part = filename.replace(".html", "")
        try:
            dt = datetime.datetime.strptime(date_part, "%Y%m%d")
            wd = weekday_map[dt.weekday()]
            date_display = f"{dt.strftime('%Y년 %m월 %d일')} ({wd})"
            
            entries.append({
                "filename": filename,
                "date_str": date_part,
                "date_display": date_display,
                "is_today": date_part == today_str,
                "article_count": 0  # Could parse and count if needed
            })
        except ValueError:
            continue
    
    # Render archive index
    html = render_briefing_archive(entries)
    index_path = os.path.join(briefing_dir, "index.html")
    
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"[Briefing] Updated archive index: {index_path}")


if __name__ == "__main__":
    generate_briefing()
