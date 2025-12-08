import os
import datetime
import argparse
from src.config import load_categories
from src.fetchers.rss import fetch_rss_items
from src.fetchers.gov import fetch_gov_announcements
from src.generators.llm import summarize_article, rank_items_with_ai
from src.generators.html import render_daily_page, render_archive_index, render_dashboard
from src.utils.common import extract_source_name, extract_image_url, sanitize_summary, translate_title_to_korean, format_timestamp

def process_category(config, now_utc, kst_timezone_offset=9):
    print(f"[{config.key.upper()}] Processing...")
    
    # 1. Fetch
    if config.key == "gov":
        raw_items = [] # Not used for table
        gov_items = fetch_gov_announcements(limit=30)
        # Gov items are already dicts, no summarization needed
        summarized_items = gov_items
    else:
        # RSS Fetch
        raw_items = fetch_rss_items(
            config.rss_feeds, 
            selection_mode=config.selection_mode, 
            keyword_filters=config.keyword_filters
        )
        
        # Rankings (if enabled)
        if config.use_ai_ranking and config.selection_mode != "random":
             print(f"[{config.key.upper()}] AI Ranking...")
             selected_raw = rank_items_with_ai(raw_items, config.max_articles)
        else:
             selected_raw = raw_items[:config.max_articles]
             
        # Summarize
        summarized_items = []
        for idx, (ts, title, link, content, entry) in enumerate(selected_raw):
            text_with_url = content + f"\n\nURL: {link}"
            try:
                summary = summarize_article(text_with_url, title, config.display_name)
                summary = sanitize_summary(summary)
            except Exception as e:
                print(f"[{config.key}] Summarization error: {e}")
                summary = "요약 실패"

            summarized_items.append({
                "title": title,
                "link": link,
                "summary_html": summary, # Assuming markdown to bold conversion happens in template or here? 
                # Template expects 'summary_html' or processed summary.
                # Use utils.markdown_bold_to_highlight in template?
                # Actually, let's keep it simple: processed in util, passed as HTML
                "published_display": format_timestamp(ts),
                "source_name": extract_source_name(entry, link),
                "image_url": extract_image_url(entry),
                "original_title": title 
            })
            
    # Markdown processing for AI items (utils import needed for markdown_bold_to_highlight?)
    # Let's import it here to keep main logic clean or better yet, move that logic to html generator filter?
    # For now, let's import it.
    from src.utils.common import markdown_bold_to_highlight
    if config.key != "gov":
         for item in summarized_items:
             item["summary_html"] = markdown_bold_to_highlight(item["summary_html"])
             # title translation?
             # item["display_title"] = translate_title_to_korean(item["title"])
             # Template handles original title logic

    # 2. Render Page
    kst_now = now_utc + datetime.timedelta(hours=kst_timezone_offset)
    date_str = kst_now.strftime("%Y-%m-%d")
    time_str = kst_now.strftime("%H:%M:%S")
    run_id = kst_now.strftime("%Y-%m-%d_%H%M%S")
    
    html = render_daily_page(summarized_items, date_str, time_str, config)
    
    # 3. Save
    os.makedirs(config.archive_dir, exist_ok=True)
    filename = f"{run_id}.html"
    with open(os.path.join(config.archive_dir, filename), "w", encoding="utf-8") as f:
        f.write(html)
        
    return {
        "filename": filename,
        "date_str": date_str,
        "time_str": time_str
    }

def rebuild_indexes(categories):
    # Daily Archives
    for key, cfg in categories.items():
        daily_dir = cfg.archive_dir
        if not os.path.exists(daily_dir):
            continue
            
        files = sorted([f for f in os.listdir(daily_dir) if f.endswith(".html")], reverse=True)
        entries = []
        for f in files:
            # Parse date/time from filename: YYYY-MM-DD_HHMMSS.html
            name_part = f.replace(".html", "")
            try:
                dt = datetime.datetime.strptime(name_part, "%Y-%m-%d_%H%M%S")
                entries.append({
                    "filename": f,
                    "date_str": dt.strftime("%Y-%m-%d"),
                    "time_str": dt.strftime("%H:%M:%S")
                })
            except:
                entries.append({"filename": f, "date_str": f, "time_str": ""})
        
        index_html = render_archive_index(entries, cfg)
        with open(cfg.index_path, "w", encoding="utf-8") as f:
            f.write(index_html)
            
        # Update run info for dashboard
        cfg.runs = entries

    # Dashboard
    dash_html = render_dashboard(categories)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(dash_html)

def main():
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Limit number of articles per category for testing")
    args = parser.parse_args()

    categories = load_categories()
    
    for key, config in categories.items():
        # Apply limit if provided
        if args.limit:
            config.max_articles = args.limit
            
        try:
           res = process_category(config, now_utc)
def process_members(limit_per_member=None):
    from src.config import load_members, CategoryConfig
    from src.fetchers.search import fetch_search_news
    from src.generators.html import render_member_daily_page, render_archive_index
    from src.utils.common import format_timestamp
    
    # Setup paths
    daily_dir = "docs/members/daily"
    os.makedirs(daily_dir, exist_ok=True)
    
    members = load_members()
    print(f"[Members] Found {len(members)} companies. Fetching news...")

    all_articles = []
    
    # Use ThreadPool? For simplicity and safety against rate limits, stick to loop or simplified concurrency.
    # Given the user wants "Daily" run, sequential is fine effectively. 169 * 0.5s = ~1.5 min.
    
    for m_key, member in members.items():
        try:
            # If testing with --limit, we might want to restrict items PER member
            limit = limit_per_member if limit_per_member else 3
            
            raw_items = fetch_search_news(member.keywords, limit=limit)
             
            if raw_items:
                print(f"  - Found {len(raw_items)} for {member.name}")
                
            for ts, title, link, content, entry in raw_items:
                # Basic dedup could go here if needed
                all_articles.append({
                    "member_name": member.name,
                    "title": title,
                    "link": link,
                    "published_display": format_timestamp(ts),
                    "timestamp": ts, # For sorting
                    # "summary_html": content # Not using summary in table view for compactness
                })
            
            # rate limit courtesy
            # time.sleep(0.1) 
            
        except Exception as e:
            print(f"  - Error {member.name}: {e}")
            
    # Sort all by date desc
    all_articles.sort(key=lambda x: x["timestamp"], reverse=True)
    print(f"[Members] Total articles found: {len(all_articles)}")

    # Generate Daily Page
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    kst_now = now_utc + datetime.timedelta(hours=9)
    date_str = kst_now.strftime("%Y-%m-%d")
    time_str = kst_now.strftime("%H:%M:%S")
    run_id = kst_now.strftime("%Y-%m-%d_%H%M%S")
    
    html = render_member_daily_page(all_articles, date_str, time_str)
    
    filename = f"{run_id}.html"
    with open(os.path.join(daily_dir, filename), "w", encoding="utf-8") as f:
        f.write(html)
        
    print(f"[Members] Generated daily report: {filename}")

    # Rebuild Index for Members (using same logic as Categories but ad-hoc config)
    # create a dummy config to reuse rebuild logic or just custom logic?
    # Let's reuse render_archive_index if possible, but it expects CategoryConfig.
    # We can create a lightweight Mock object or just struct.
    
    # Or simpler:
    files = sorted([f for f in os.listdir(daily_dir) if f.endswith(".html")], reverse=True)
    entries = []
    for f in files:
        name_part = f.replace(".html", "")
        try:
            dt = datetime.datetime.strptime(name_part, "%Y-%m-%d_%H%M%S")
            entries.append({
                "filename": f,
                "date_str": dt.strftime("%Y-%m-%d"),
                "time_str": dt.strftime("%H:%M:%S")
            })
        except:
             pass
             
    # Reuse render_archive_index by mocking config
    class MockConfig:
        display_name = "Members News"
        key = "members"
        
    index_html = render_archive_index(entries, MockConfig())
    with open("docs/members/index.html", "w", encoding="utf-8") as f:
        f.write(index_html)
        
    # Also we need to ADD Members to the Dashboard (index.html) of the root.
    # main() calls rebuild_indexes(categories). 'categories' config doesn't include 'members'.
    # We should probably add 'members' to the logic in rebuild_indexes?
    # Or just let it be handled separately? 
    # Current 'rebuild_indexes' iterates 'categories'. Members is separate.
    # We should probably update 'load_categories' to include members? No, structure is different.
    # Let's Modify 'rebuild_indexes' to include members manually or update 'render_dashboard'.

def main():
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Limit number of articles per category for testing")
    args = parser.parse_args()

    # 1. Process Categories
    categories = load_categories()
    for key, config in categories.items():
        if args.limit:
            config.max_articles = args.limit
            
        try:
           res = process_category(config, now_utc)
           print(f"[{key}] Generated: {res['filename']}")
        except Exception as e:
           print(f"[{key}] Failed: {e}")
    
    # 2. Process Members
    try:
        # Pass limit if testing
        process_members(limit_per_member=1 if args.limit else None)
    except Exception as e:
        print(f"[Members] Process failed: {e}")
        import traceback
        traceback.print_exc()

    # 3. Rebuild Indexes (Root Dashboard)
    # We need to inject Members data into dashboard.
    # Let's cheat and add a fake category for Dashboard rendering
    
    # Check members run history
    m_daily_dir = "docs/members/daily"
    m_runs = []
    if os.path.exists(m_daily_dir):
        m_files = sorted([f for f in os.listdir(m_daily_dir) if f.endswith(".html")], reverse=True)
        for f in m_files[:5]:
             try:
                dt = datetime.datetime.strptime(f.replace(".html",""), "%Y-%m-%d_%H%M%S")
                m_runs.append({
                    "filename": f,
                    "date_str": dt.strftime("%Y-%m-%d"),
                    "time_str": dt.strftime("%H:%M:%S")
                })
             except: pass

    # Add to categories dict for dashboard rendering
    # We need a dict-like object
    class MemberCatData:
        display_name = "Startups"
        runs = m_runs
    
    categories["members"] = MemberCatData()

    rebuild_indexes(categories)

if __name__ == "__main__":
    main()
