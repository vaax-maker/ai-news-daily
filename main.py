import os
import datetime
import argparse
from src.config import load_categories
from src.fetchers.rss import fetch_rss_items
from src.fetchers.gov import fetch_gov_announcements
from src.generators.llm import summarize_article, rank_items_with_ai
from src.generators.html import (
    render_daily_page, render_archive_index, render_gov_archive,
    render_member_page, render_dashboard, render_member_index
)
from src.utils.common import (
    extract_source_name,
    extract_image_url,
    format_timestamp,
    markdown_bold_to_highlight,
    sanitize_summary,
    shorten_korean_title,
    trim_summary_lines,
)
from src.utils.storage import MemberStorage, GovStorage
from collections import Counter
import re

def process_category(config, now_utc, kst_timezone_offset=9):
    print(f"[{config.key.upper()}] Processing...")
    
    # 1. Fetch
    if config.key == "gov":
        gov_items = fetch_gov_announcements(limit=30)
        storage = GovStorage()
        summarized_items = storage.save_announcements(gov_items)
    else:
        # RSS Fetch
        raw_items = fetch_rss_items(
            config.rss_feeds, 
            selection_mode=config.selection_mode, 
            keyword_filters=config.keyword_filters
        )
        
        # Rankings (if enabled)
        if config.use_ai_ranking:
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
                summary = trim_summary_lines(summary)
            except Exception as e:
                print(f"[{config.key}] Summarization error: {e}")
                summary = "요약 실패"

            summarized_items.append({
                "title": shorten_korean_title(title),
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
        "items": summarized_items
    }


def latest_daily_page_path(config):
    """Return the most recent generated daily page for a category (relative to docs root)."""
    if not os.path.isdir(config.archive_dir):
        return None

    html_files = sorted(
        [f for f in os.listdir(config.archive_dir) if f.endswith(".html")],
        reverse=True
    )
    if not html_files:
        return None

    latest_filename = html_files[0]
    rel_dir = os.path.relpath(config.archive_dir, "docs")
    return f"{rel_dir}/{latest_filename}"

def rebuild_indexes(categories):
    # Daily Archives Index Generation
    weekday_map = {0:'월', 1:'화', 2:'수', 3:'목', 4:'금', 5:'토', 6:'일'}

    for key, cfg in categories.items():
        if key == "gov":
            storage = GovStorage()
            announcements = storage.load_announcements()

            def sort_key(item):
                date_str = item.get("date") or item.get("published_display") or ""
                try:
                    return datetime.datetime.strptime(date_str, "%Y-%m-%d")
                except Exception:
                    return datetime.datetime.min

            announcements.sort(key=sort_key, reverse=True)

            index_html = render_gov_archive(announcements)
            with open(cfg.index_path, "w", encoding="utf-8") as f:
                f.write(index_html)
            continue

        daily_dir = cfg.archive_dir
        if not os.path.exists(daily_dir):
            continue
            
        files = sorted([f for f in os.listdir(daily_dir) if f.endswith(".html")], reverse=True)
        entries = []
        for f in files:
            name_part = f.replace(".html", "")
            try:
                dt = datetime.datetime.strptime(name_part, "%Y-%m-%d_%H%M%S")
                # Add Weekday
                wd = weekday_map[dt.weekday()]
                
                entries.append({
                    "filename": f,
                    "date_str": dt.strftime("%Y-%m-%d"),
                    "time_str": dt.strftime("%H:%M:%S"),
                    "day_of_week": wd
                })
            except:
                entries.append({"filename": f, "date_str": f, "time_str": "", "day_of_week": ""})
        
        index_html = render_archive_index(entries, cfg)
        with open(cfg.index_path, "w", encoding="utf-8") as f:
            f.write(index_html)


def process_members(limit_per_member=None):
    from src.config import load_members
    from src.fetchers.search import fetch_search_news
    
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
                summary = sanitize_summary(content)
                summary = trim_summary_lines(summary)
                formatted_summary = markdown_bold_to_highlight(summary)

                new_articles.append({
                    "member_name": member.name,
                    "title": shorten_korean_title(title),
                    "link": link,
                    "published_display": format_timestamp(ts),
                    "summary_html": formatted_summary, # Search returns snippet
                    "source_name": extract_source_name(entry, link),
                    "image_url": extract_image_url(entry),
                    "timestamp": ts,
                    "original_title": title
                })
            
            # 3. Save/Merge with persistence
            updated_history = storage.save_news(m_key, new_articles)
            
            # 4. Generate Individual Member Page
            now_str = datetime.datetime.now().strftime("%Y-%m-%d")
            
            # Sort by timestamp desc
            updated_history.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            
            html = render_member_page(member, updated_history, now_str)
            
            safe_name = re.sub(r'[<>:"/\\|?*]', '_', m_key).strip()
            page_filename = f"{safe_name}.html" 
            
            with open(os.path.join(member_page_dir, page_filename), "w", encoding="utf-8") as f:
                f.write(html)
            
            all_latest_news.extend(updated_history[:2])
            
        except Exception as e:
            print(f"  - Error {member.name}: {e}")
            
    # Sort all collected news by timestamp and take top 5
    all_latest_news.sort(key=lambda x: x.get("timestamp", 0), reverse=True)

    # Generate Members Index
    member_entries = []
    weekday_map = {0:'월', 1:'화', 2:'수', 3:'목', 4:'금', 5:'토', 6:'일'}
    
    for m_key, member in members.items():
        history = storage.load_news(m_key)
        count = len(history)
        
        # Safe name
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', m_key).strip()
        
        # Latest date
        latest_str = "-"
        if history:
            # Sort ensure
            history.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            latest = history[0]
            ts = latest.get("timestamp", 0)
            if ts:
                dt = datetime.datetime.fromtimestamp(ts)
                wd = weekday_map[dt.weekday()]
                latest_str = f"{dt.strftime('%Y-%m-%d')}({wd}) {dt.strftime('%H:%M')}"
            else:
                latest_str = latest.get("published_display", "-")

        member_entries.append({
            "filename": f"{safe_name}.html", 
            "name": member.name, 
            "count": count,
            "latest_date": latest_str
        })
        
    # Sort by Count (Desc)
    member_entries.sort(key=lambda x: (-x["count"], x["name"]))
    
    # Cleanup stale files
    existing_files = set(os.listdir(member_page_dir))
    generated_files = {entry["filename"] for entry in member_entries}
    generated_files.add("index.html")
    
    for filename in existing_files:
        if filename.endswith(".html") and filename not in generated_files:
            file_path = os.path.join(member_page_dir, filename)
            try:
                os.remove(file_path)
            except: pass
    
    idx_html = render_member_index(member_entries)
    with open("docs/members/index.html", "w", encoding="utf-8") as f:
        f.write(idx_html)
        
    return all_latest_news[:5]

def main():
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Limit number of articles per category for testing")
    args = parser.parse_args()

    dashboard_data = {
        "ai": [],
        "xr": [],
        "gov": [],
        "members": [],
        "links": {} # To store latest filenames
    }

    # 1. Process Categories
    categories = load_categories()
    for key, config in categories.items():
        if args.limit:
            config.max_articles = args.limit

        try:
            res = process_category(config, now_utc)
            print(f"[{key}] Generated: {res['filename']}")
            dashboard_data[key] = res.get("items", [])
            # Store latest filename relative to docs root
            # docs/ai/daily/xyz.html -> ai/daily/xyz.html
            # config.archive_dir is "docs/ai/daily"
            rel_path = f"{key}/daily/{res['filename']}"
            dashboard_data["links"][key] = rel_path

        except Exception as e:
            print(f"[{key}] Failed: {e}")
            import traceback
            traceback.print_exc()

        # Ensure the dashboard has a path to the newest available daily page
        fallback_path = latest_daily_page_path(config)
        if fallback_path:
            dashboard_data["links"].setdefault(key, fallback_path)

        if key == "gov":
            dashboard_data["links"]["gov"] = "gov/index.html"

    # 2. Process Members
    try:
        members_latest = process_members(limit_per_member=1 if args.limit else None)
        dashboard_data["members"] = members_latest
        dashboard_data["links"]["members"] = "members/index.html" # Members always goes to index
    except Exception as e:
        print(f"[Members] Process failed: {e}")
        import traceback
        traceback.print_exc()

    # 3. Rebuild Indexes
    rebuild_indexes(categories)

    # 4. Render Dashboard
    try:
        dash_html = render_dashboard(
            ai_latest=dashboard_data.get("ai", [])[:5],
            xr_latest=dashboard_data.get("xr", [])[:5],
            gov_latest=dashboard_data.get("gov", [])[:5],
            members_latest=dashboard_data.get("members", [])[:5],
            section_links=dashboard_data.get("links", {})
        )
        with open("docs/index.html", "w", encoding="utf-8") as f:
            f.write(dash_html)
        print("[Dashboard] Index generated.")
        
        # 5. Asset Deployment
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
