import os
import datetime
import argparse
from src.config import load_categories
from src.fetchers.rss import fetch_rss_items
from src.fetchers.gov import fetch_gov_announcements
from src.generators.llm import summarize_article, rank_items_with_ai
from src.generators.html import (
    render_daily_page, render_archive_index,
    render_member_page, render_dashboard, render_member_index
)
from src.utils.common import extract_source_name, extract_image_url, sanitize_summary, translate_title_to_korean, format_timestamp, markdown_bold_to_highlight
from src.utils.storage import MemberStorage
from collections import Counter
import re

def process_category(config, now_utc, kst_timezone_offset=9):
    print(f"[{config.key.upper()}] Processing...")
    
    # 1. Fetch
    if config.key == "gov":
        gov_items = fetch_gov_announcements(limit=30)
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
                "summary_html": summary, 
                "published_display": format_timestamp(ts),
                "source_name": extract_source_name(entry, link),
                "image_url": extract_image_url(entry),
                "original_title": title 
            })
            
    # Markdown processing for AI items
    if config.key != "gov":
         for item in summarized_items:
             item["summary_html"] = markdown_bold_to_highlight(item["summary_html"])

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
        "time_str": time_str,
        "items": summarized_items # Return items for dashboard
    }

def rebuild_indexes(categories):
    # Daily Archives Index Generation
    for key, cfg in categories.items():
        daily_dir = cfg.archive_dir
        if not os.path.exists(daily_dir):
            continue
            
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
                entries.append({"filename": f, "date_str": f, "time_str": ""})
        
        index_html = render_archive_index(entries, cfg)
        with open(cfg.index_path, "w", encoding="utf-8") as f:
            f.write(index_html)


def process_members(limit_per_member=None):
    from src.config import load_members
    from src.fetchers.search import fetch_search_news
    from src.utils.common import format_timestamp
    
    # Setup paths
    member_page_dir = "docs/members"
    os.makedirs(member_page_dir, exist_ok=True)
    
    members = load_members()
    storage = MemberStorage()
    print(f"[Members] Found {len(members)} companies. Fetching news...")

    all_latest_news = []
    
    for m_key, member in members.items():
        try:
            # 1. Fetch Request
            limit = limit_per_member if limit_per_member else 3
            raw_items = fetch_search_news(member.keywords, limit=limit)
             
            if raw_items:
                print(f"  - Found {len(raw_items)} for {member.name}")
            
            # 2. Format
            new_articles = []
            for ts, title, link, content, entry in raw_items:
                new_articles.append({
                    "member_name": member.name, 
                    "title": title,
                    "link": link,
                    "published_display": format_timestamp(ts),
                    "summary_html": content, # Search returns snippet
                    "source_name": extract_source_name(entry, link),
                    "image_url": extract_image_url(entry),
                    "timestamp": ts
                })
            
            # 3. Save/Merge with persistence
            # Key: Storage uses member key
            updated_history = storage.save_news(m_key, new_articles)
            
            # 4. Generate Individual Member Page
            # We want to show the full history
            # Date for page generation
            now_str = datetime.datetime.now().strftime("%Y-%m-%d")
            
            # Sort by timestamp desc
            updated_history.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            
            html = render_member_page(member, updated_history, now_str)
            
            safe_name = m_key.replace("/", "_").replace("\\", "_")
            page_filename = f"{safe_name}.html" 
            
            with open(os.path.join(member_page_dir, page_filename), "w", encoding="utf-8") as f:
                f.write(html)
            
            # 5. Collect for Dashboard (Top items from this member's *new* or *latest*)
            # We want global top 5 across all members.
            # So add top 1 from each member to the pot? 
            # Or add ALL updated items to a list and sort later?
            # Let's add top 3 latest from this member to global list
            all_latest_news.extend(updated_history[:2])
            
        except Exception as e:
            print(f"  - Error {member.name}: {e}")
            
    # Sort all collected news by timestamp and take top 5
    all_latest_news.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    
    # Collect for Word Cloud (Titles only) -> REMOVED per user request
    # word_cloud_data calculation removed.

    # Generate Members Index (Just a list of links to member pages)
    
    # Sort members by accumulated news count (descending)
    member_entries = []
    
    # Clean up existing member pages to remove stale English files
    # Only if we are doing a full run or just always? Always is safer for "unused files" requirement.
    # But wait, we just generated them. If I delete them now, I lose what I generated in the loop above?
    # No, the loop above generated them. 
    # STRICTLY SPEAKING: I should have cleaned `docs/members` BEFORE the loop.
    # But since I can't easily edit the top of the function without large replace, 
    # I will rely on the user manually deleting or I will use a separate script?
    # Actually, I can just walk `docs/members` and delete files that are NOT in `member_entries`.
    
    for m_key, member in members.items():
        # Load accumulated news from storage
        history = storage.load_news(m_key)
        count = len(history)
        
        # Sanitize filename
        safe_name = m_key.replace("/", "_").replace("\\", "_")
        member_entries.append({
            "filename": f"{safe_name}.html", 
            "name": member.name, 
            "count": count
        })
        
    # Sort by Count (Desc) then Name (Asc)
    member_entries.sort(key=lambda x: (-x["count"], x["name"]))
    
    # Cleanup: Delete files in docs/members that are not in member_entries
    existing_files = set(os.listdir(member_page_dir))
    generated_files = {entry["filename"] for entry in member_entries}
    generated_files.add("index.html") # Don't delete index
    
    for filename in existing_files:
        if filename.endswith(".html") and filename not in generated_files:
            file_path = os.path.join(member_page_dir, filename)
            try:
                os.remove(file_path)
                print(f"[Cleanup] Removed stale file: {filename}")
            except OSError as e:
                print(f"[Cleanup] Error deleting {filename}: {e}")
    
    idx_html = render_member_index(member_entries)
    with open("docs/members/index.html", "w", encoding="utf-8") as f:
        f.write(idx_html)
        
    return all_latest_news[:5]

def main():
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Limit number of articles per category for testing")
    args = parser.parse_args()

    # Data holders for dashboard
    dashboard_data = {
        "ai": [],
        "xr": [],
        "gov": [],
        "members": []
    }

    # 1. Process Categories
    categories = load_categories()
    for key, config in categories.items():
        if args.limit:
            config.max_articles = args.limit
            
        try:
           res = process_category(config, now_utc)
           print(f"[{key}] Generated: {res['filename']}")
           # Store items for dashboard
           dashboard_data[key] = res.get("items", [])
        except Exception as e:
           print(f"[{key}] Failed: {e}")
           import traceback
           traceback.print_exc()
    
    # 2. Process Members
    try:
        members_latest = process_members(limit_per_member=1 if args.limit else None)
        dashboard_data["members"] = members_latest
    except Exception as e:
        print(f"[Members] Process failed: {e}")
        import traceback
        traceback.print_exc()

    # 3. Rebuild Indexes (Category Archives)
    rebuild_indexes(categories)

    # 4. Render Dashboard (Root Index)
    try:
        dash_html = render_dashboard(
            ai_latest=dashboard_data.get("ai", [])[:5],
            xr_latest=dashboard_data.get("xr", [])[:5],
            gov_latest=dashboard_data.get("gov", [])[:5],
            members_latest=dashboard_data.get("members", [])[:5]
        )
        with open("docs/index.html", "w", encoding="utf-8") as f:
            f.write(dash_html)
        print("[Dashboard] Index generated.")
        
        # 5. Asset Deployment
        # Copy static/ to docs/static/ so GitHub Pages can serve it
        import shutil
        src_static = "static"
        dst_static = "docs/static"
        if os.path.exists(src_static):
            if os.path.exists(dst_static):
                shutil.rmtree(dst_static)
            shutil.copytree(src_static, dst_static)
            print(f"[Deployment] Copied {src_static} -> {dst_static}")
            
    except Exception as e:
        print(f"[Dashboard] Failed to render: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
