import os
import datetime
import argparse
import logging
from src.config import load_categories
from bs4 import BeautifulSoup
from src.fetchers.rss import fetch_rss_items
from src.fetchers.gov import fetch_gov_announcements
from src.generators.llm import summarize_article, rank_items_with_ai
from src.generators.html import (
    render_daily_page, render_archive_index, render_gov_archive,
    render_member_page, render_dashboard, render_member_index, render_board_page,
    render_mobile_landing
)
from src.utils.common import (
    extract_source_name,
    extract_image_url,
    get_fallback_image,
    format_timestamp,
    markdown_bold_to_highlight,
    parse_article_datetime,
    sanitize_summary,
    shorten_korean_title,
    trim_summary_lines,
)
from src.utils.notifier import send_daily_briefing
from src.utils.storage import MemberStorage, GovStorage
from src.utils.wordcloud_generator import extract_weekly_keywords, create_wordcloud_image
from collections import Counter
import re

# Configure logging for the entire application
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)



def str_to_bool(value: str) -> bool:
    return str(value).strip().lower() in ["true", "1", "yes", "y", "on"]

def parse_existing_articles(html_path: str):
    if not os.path.exists(html_path):
        return []

    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    parsed = []
    news_articles = soup.select("article.news-item")

    if news_articles:
        for article in news_articles:
            title_el = article.select_one(".news-title a")
            summary_el = article.select_one(".news-summary")

            item = {
                "title": title_el.get_text(strip=True) if title_el else "",
                "link": title_el.get("href", "") if title_el else "",
                "summary_html": summary_el.decode_contents().strip() if summary_el else "",
                "published_display": article.select_one(".published-date").get_text(strip=True) if article.select_one(".published-date") else "",
                "source_name": article.select_one(".source-link").get_text(strip=True) if article.select_one(".source-link") else "",
                "image_url": article.select_one(".news-image img").get("src", "") if article.select_one(".news-image img") else "",
            }
            dt = parse_article_datetime(item)
            if dt != datetime.datetime.min:
                item["timestamp"] = dt.timestamp()
            parsed.append(item)

        return parsed

    for row in soup.select("table.styled-table tbody tr"):
        title_el = row.select_one(".col-title a")
        parsed.append({
            "title": title_el.get_text(strip=True) if title_el else "",
            "link": title_el.get("href", "") if title_el else "",
            "dept": row.select_one(".col-dept").get_text(strip=True) if row.select_one(".col-dept") else "",
            "manager": row.select(".col-dept")[-1].get_text(strip=True) if row.select(".col-dept") else "",
            "date": row.select_one(".col-date").get_text(strip=True) if row.select_one(".col-date") else "",
        })

    return parsed

def merge_articles(primary_items, secondary_items):
    merged = []
    seen_links = set()

    for item in primary_items + secondary_items:
        link = item.get("link")
        if link and link in seen_links:
            continue
        if link:
            seen_links.add(link)
        merged.append(item)

    return merged

def consolidate_daily_archives(config):
    daily_dir = config.archive_dir
    if not os.path.isdir(daily_dir):
        return

    files = [f for f in os.listdir(daily_dir) if f.endswith(".html")]
    grouped = {}

    for fname in files:
        date_key = fname.split("_")[0]
        grouped.setdefault(date_key, []).append(fname)

    for date_key, date_files in grouped.items():
        if len(date_files) < 2:
            continue

        date_files.sort() # Sorted chronologically
        primary = date_files[0]
        duplicates = date_files[1:]

        combined = []
        # Load oldest to newest to keep the first version of each article
        for fname in date_files:
            path = os.path.join(daily_dir, fname)
            combined.extend(parse_existing_articles(path))

        # merge_articles(older, newer) keeps older version
        merged_articles = merge_articles(combined, [])

        primary_name = primary.replace(".html", "")
        # ... (rest of logic for time extraction)
        try:
            dt = datetime.datetime.strptime(primary_name, "%Y-%m-%d_%H%M%S")
            date_str = dt.strftime("%Y-%m-%d")
            time_str = dt.strftime("%H:%M:%S")
        except Exception:
            date_str = date_key
            time_str = "00:00:00"

        html = render_daily_page(merged_articles, date_str, time_str, config)

        with open(os.path.join(daily_dir, primary), "w", encoding="utf-8") as f:
            f.write(html)

        for dup in duplicates:
            try:
                os.remove(os.path.join(daily_dir, dup))
            except Exception:
                pass

def process_category(config, now_utc, kst_timezone_offset=9):
    print(f"[{config.key.upper()}] Processing...")
    
    # Resolve current day's info
    kst_now = now_utc + datetime.timedelta(hours=kst_timezone_offset)
    date_str = kst_now.strftime("%Y-%m-%d")
    time_str = kst_now.strftime("%H:%M:%S")
    run_id = kst_now.strftime("%Y-%m-%d_%H%M%S")

    # 1. Fetch
    new_summarized_count = 0
    
    if config.key == "gov":
        gov_items = fetch_gov_announcements(limit=30)
        storage = GovStorage()
        existing_before = storage.load_announcements()
        summarized_items = storage.save_announcements(gov_items)
        # Simple Logic: Only increase count if total count increased.
        # This is a safe approximation.
        if len(summarized_items) > len(existing_before):
            new_summarized_count = len(summarized_items) - len(existing_before)
            
        # Ensure items have timestamp for badge
        # Gov items usually have "date" string, convert to ts if needed?
        # Or just let them be without new badge if not robust.
        # However, plan asked for NEW badge generally.
        # Gov items are "announcements.json", usually don't have unix timestamp field "timestamp".
        # We can try to parse date.
        for item in summarized_items:
            if "timestamp" not in item:
                try:
                    dt = datetime.datetime.strptime(item.get("date", ""), "%Y-%m-%d")
                    item["timestamp"] = dt.timestamp()
                except:
                    item["timestamp"] = 0
            
    else:
        # RSS Fetch
        raw_items = fetch_rss_items(
            config.rss_feeds, 
            selection_mode=config.selection_mode, 
            keyword_filters=config.keyword_filters
        )
        
        if not raw_items:
            print(f"[{config.key.upper()}] WARNING: No items fetched from RSS feeds.")
        else:
            print(f"[{config.key.upper()}] Fetched {len(raw_items)} items.")
        
        # Rankings (if enabled)
        if config.use_ai_ranking:
            print(f"[{config.key.upper()}] AI Ranking...")
            selected_raw = rank_items_with_ai(raw_items, config.max_articles)
        else:
            selected_raw = raw_items[:config.max_articles]
        
        # Load ALL existing articles for global dedup
        all_past_articles = []
        today_existing_articles = []
        
        if os.path.isdir(config.archive_dir):
            for html_file in sorted(os.listdir(config.archive_dir)):
                if not html_file.endswith(".html"):
                    continue
                
                path = os.path.join(config.archive_dir, html_file)
                parsed = parse_existing_articles(path)
                
                if html_file.startswith(date_str):
                    today_existing_articles.extend(parsed)
                else:
                    all_past_articles.extend(parsed)
        
        past_links = {art.get("link") for art in all_past_articles if art.get("link")}
        today_links = {art.get("link") for art in today_existing_articles if art.get("link")}
        today_by_link = {art.get("link"): art for art in today_existing_articles if art.get("link")}
        
        print(f"[{config.key.upper()}] Found {len(past_links)} past, {len(today_links)} today articles for dedup check.")
             
        # Summarize
        summarized_items = []
        skipped_count = 0
        for idx, (ts, title, link, content, entry) in enumerate(selected_raw):
            # 1. Skip if exists on a DIFFERENT day (global dedup)
            if link in past_links:
                continue
            
            # 2. Reuse if exists in an earlier run TODAY
            if link in today_links:
                existing_art = today_by_link.get(link)
                if existing_art and existing_art.get("summary_html"):
                    summarized_items.append({
                        "title": existing_art.get("title", shorten_korean_title(title)),
                        "link": link,
                        "summary_html": existing_art.get("summary_html"),
                        "published_display": existing_art.get("published_display", format_timestamp(ts)),
                        "source_name": existing_art.get("source_name", extract_source_name(entry, link)),
                        "image_url": existing_art.get("image_url", ""),
                        "placeholder_type": "",
                        "original_title": title,
                        "timestamp": ts, # Add timestamp for badge
                        "is_new": False  # 🚀 Reused items are NOT new for notification
                    })
                    skipped_count += 1
                    continue
            
            # New article - call LLM for summarization
            text_with_url = content + f"\n\nURL: {link}"
            try:
                summary = summarize_article(text_with_url, title, config.display_name)
                summary = sanitize_summary(summary)
                summary = trim_summary_lines(summary)
            except Exception as e:
                print(f"[{config.key}] Summarization error for '{title[:50]}...': {e}")
                continue # Skip failed items

            image_url = extract_image_url(entry, link) if config.key in ("ai", "xr") else ""
            placeholder_type = config.key if (config.key in ("ai", "xr") and not image_url) else ""

            summarized_items.append({
                "title": shorten_korean_title(title),
                "link": link,
                "summary_html": summary,
                "published_display": format_timestamp(ts),
                "source_name": extract_source_name(entry, link),
                "image_url": image_url,
                "placeholder_type": placeholder_type,
                "original_title": title,
                "placeholder_type": placeholder_type,
                "original_title": title,
                "timestamp": ts, # Add timestamp for badge
                "is_new": True   # 🚀 Summarized (Fetched) items ARE new
            })
            new_summarized_count += 1 # Count this as NEW
        
        if skipped_count > 0:
            print(f"[{config.key.upper()}] Reused {skipped_count} existing summaries (LLM calls saved).")
            
    # Markdown processing for AI items
    if config.key != "gov":
        for item in summarized_items:
            item["summary_html"] = markdown_bold_to_highlight(item["summary_html"])

    if not summarized_items and config.key != "gov":
        print(f"[{config.key.upper()}] WARNING: No items produced after summarization step.")

    def resolve_daily_file(date_str: str, run_id: str):
        os.makedirs(config.archive_dir, exist_ok=True)
        html_files = [
            f for f in os.listdir(config.archive_dir)
            if f.endswith(".html") and f.startswith(date_str)
        ]

        if html_files:
            html_files.sort()
            return html_files[0], html_files[1:]

        return f"{run_id}.html", []

    # 2. Render Page
    filename, duplicates = resolve_daily_file(date_str, run_id)
    archived_articles = []

    for fname in [filename] + duplicates:
        path = os.path.join(config.archive_dir, fname)
        archived_articles.extend(parse_existing_articles(path))

    # Keep oldest version today (archived_articles first)
    merged_items = merge_articles(archived_articles, summarized_items)
    merged_items = sorted(merged_items, key=parse_article_datetime, reverse=True)

    html = render_daily_page(merged_items, date_str, time_str, config)

    # 3. Save
    with open(os.path.join(config.archive_dir, filename), "w", encoding="utf-8") as f:
        f.write(html)

    # Clean up duplicate runs for the same day now that they are merged
    for dup in duplicates:
        try:
            os.remove(os.path.join(config.archive_dir, dup))
        except Exception:
            pass

    return {
        "filename": filename,
        "date_str": date_str,
        "time_str": time_str,
        "items": merged_items,
        "new_count": new_summarized_count 
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


def parse_preview_articles_from_html(html_path, limit=5):
    if not os.path.exists(html_path):
        return []

    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    previews = []
    for article in soup.select("article.news-item")[:limit]:
        title_el = article.select_one(".news-title a")
        meta_el = article.select_one(".news-meta")

        source_name = ""
        published_display = ""

        if meta_el:
            meta_text = meta_el.get_text(" ", strip=True)
            if "|" in meta_text:
                left, right = meta_text.split("|", 1)
                source_name = left.strip()
                published_display = right.strip()
            else:
                published_display = meta_text

        previews.append({
            "title": title_el.get_text(strip=True) if title_el else "",
            "link": title_el.get("href", "") if title_el else "",
            "published_display": published_display,
            "source_name": source_name
        })

    return previews


def load_latest_articles_from_archive(config, limit=5):
    latest_path = latest_daily_page_path(config)
    if not latest_path:
        return []

    full_path = os.path.join("docs", latest_path)
    return parse_preview_articles_from_html(full_path, limit=limit)


def sort_gov_announcements(announcements):
    def sort_key(item):
        date_str = item.get("date") or item.get("published_display") or ""
        try:
            return datetime.datetime.strptime(date_str, "%Y-%m-%d")
        except Exception:
            return datetime.datetime.min

    announcements.sort(key=sort_key, reverse=True)
    return announcements


def load_existing_members_latest(limit=5):
    from src.config import load_members

    members = load_members()
    storage = MemberStorage()
    collected = []

    for m_key in members.keys():
        history = storage.load_news(m_key)
        if not history:
            continue

        history.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        collected.extend(history[:2])

    collected.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return collected[:limit]

def rebuild_indexes(categories, consolidate_archives=False):
    # Daily Archives Index Generation
    weekday_map = {0:'월', 1:'화', 2:'수', 3:'목', 4:'금', 5:'토', 6:'일'}

    for key, cfg in categories.items():
        if key == "gov":
            storage = GovStorage()
            announcements = sort_gov_announcements(storage.load_announcements())

            index_html = render_gov_archive(announcements)
            with open(cfg.index_path, "w", encoding="utf-8") as f:
                f.write(index_html)
            continue

        if consolidate_archives:
            consolidate_daily_archives(cfg)

        daily_dir = cfg.archive_dir
        if not os.path.exists(daily_dir):
            continue
            
        files = sorted([f for f in os.listdir(daily_dir) if f.endswith(".html")], reverse=True)
        earliest_by_date = {}

        for f in files:
            date_part = f.split("_")[0]
            existing = earliest_by_date.get(date_part)
            if existing is None or f < existing:
                earliest_by_date[date_part] = f

        entries = []
        for f in sorted(earliest_by_date.values(), reverse=True):
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
                    "image_url": extract_image_url(entry, link),
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
        
        # Latest date and title
        latest_str = "-"
        latest_title = ""
        latest_link = ""
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
            latest_title = latest.get("title", "")
            latest_link = latest.get("link", "")

        member_entries.append({
            "filename": f"{safe_name}.html", 
            "name": member.name, 
            "count": count,
            "latest_date": latest_str,
            "latest_title": latest_title,
            "latest_link": latest_link
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
    
    # Filter to only today's news for the "Latest News" tab
    # Accumulated news can be viewed on individual member pages
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    today_start = datetime.datetime.strptime(today_str, "%Y-%m-%d").timestamp()
    
    todays_news = [
        item for item in all_latest_news 
        if item.get("timestamp", 0) >= today_start
    ]
    
    print(f"[Members] Total news: {len(all_latest_news)}, Today's news: {len(todays_news)}")
    
    idx_html = render_member_index(member_entries, all_news=todays_news)
    with open("docs/members/index.html", "w", encoding="utf-8") as f:
        f.write(idx_html)
        
    return todays_news[:5]

def main():
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Limit number of articles per category for testing")
    parser.add_argument(
        "--consolidate-archives",
        action="store_true",
        help="Merge duplicate daily files and rebuild indexes. Enabled by default via environment flag"
    )
    args = parser.parse_args()

    dashboard_data = {
        "ai": [],
        "xr": [],
        "gov": [],
        "members": [],
        "links": {} # To store latest filenames
    }

    run_flags = {
        "ai": str_to_bool(os.getenv("RUN_AI", "true")),
        "xr": str_to_bool(os.getenv("RUN_XR", "true")),
        "gov": str_to_bool(os.getenv("RUN_GOV", "true")),
        "members": str_to_bool(os.getenv("RUN_MEMBERS", "true"))
    }

    # 1. Process Categories
    categories = load_categories()
    total_new_items = 0
    for key, config in categories.items():
        if not run_flags.get(key, True):
            print(f"[{key}] Skipped by configuration.")
            if key == "gov":
                storage = GovStorage()
                announcements = sort_gov_announcements(storage.load_announcements())
                dashboard_data["gov"] = announcements[:5]
                dashboard_data["links"]["gov"] = "gov/index.html"
            else:
                fallback_articles = load_latest_articles_from_archive(config)
                if fallback_articles:
                    dashboard_data[key] = fallback_articles

                fallback_path = latest_daily_page_path(config)
                if fallback_path:
                    dashboard_data["links"][key] = fallback_path
            continue

        if args.limit:
            config.max_articles = args.limit

        try:
            res = process_category(config, now_utc)
            print(f"[{key}] Generated: {res['filename']} (New Items: {res.get('new_count', 0)})")
            dashboard_data[key] = res.get("items", [])
            total_new_items += res.get("new_count", 0)
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
    if run_flags.get("members", True):
        try:
            members_latest = process_members(limit_per_member=1 if args.limit else None)
            dashboard_data["members"] = members_latest
            dashboard_data["links"]["members"] = "members/index.html" # Members always goes to index
        except Exception as e:
            print(f"[Members] Process failed: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("[Members] Skipped by configuration.")
        dashboard_data["members"] = load_existing_members_latest()
        dashboard_data["links"]["members"] = "members/index.html"

    # 3. Rebuild Indexes
    rebuild_indexes(
        categories,
        consolidate_archives=str_to_bool(os.getenv("CONSOLIDATE_ARCHIVES", "true")) or args.consolidate_archives
    )

    # 3.5 Generate Word Cloud
    if str_to_bool(os.getenv("SKIP_WORDCLOUD", "false")):
        print("[WordCloud] Skipped by configuration.")
    else:
        print("[WordCloud] Generating 2-day word cloud...")
        try:
            wc_counts, wc_categories = extract_weekly_keywords(docs_dir="docs", days=2)
            wc_output_path = "static/images/weekly_wordcloud.png"
            os.makedirs(os.path.dirname(wc_output_path), exist_ok=True)
            create_wordcloud_image(wc_counts, wc_categories, wc_output_path)
            
            # Also copy to docs/static for deployment
            docs_output_path = "docs/static/images/weekly_wordcloud.png"
            os.makedirs(os.path.dirname(docs_output_path), exist_ok=True)
            import shutil
            shutil.copy(wc_output_path, docs_output_path)
            print(f"[WordCloud] Saved to {wc_output_path} and {docs_output_path}")
        except Exception as e:
            print(f"[WordCloud] Failed: {e}")

    # 3.8 Generate Board Page
    print("[Board] Generating board page...")
    try:
        os.makedirs("docs/board", exist_ok=True)
        board_html = render_board_page()
        with open("docs/board/index.html", "w", encoding="utf-8") as f:
            f.write(board_html)
        print("[Board] Generated docs/board/index.html")
    except Exception as e:
        print(f"[Board] Failed: {e}")

    # 4. Save actual news update timestamp (only when there are NEW articles)
    if total_new_items > 0:
        news_update_time = datetime.datetime.now().strftime("%Y년 %m월 %d일 %H시 %M분")
        with open("docs/last_update.txt", "w", encoding="utf-8") as f:
            f.write(news_update_time)
        print(f"[Update] New articles found ({total_new_items}). Saved update time: {news_update_time}")
    else:
        # Read existing time if no new articles
        if os.path.exists("docs/last_update.txt"):
            with open("docs/last_update.txt", "r", encoding="utf-8") as f:
                news_update_time = f.read().strip()
        else:
            news_update_time = "정보 없음"
        print(f"[Update] No new articles. Keeping existing time: {news_update_time}")

    # 5. Render Dashboard
    try:
        dash_html = render_dashboard(
            ai_latest=dashboard_data.get("ai", [])[:5],
            xr_latest=dashboard_data.get("xr", [])[:5],
            gov_latest=dashboard_data.get("gov", [])[:5],
            members_latest=dashboard_data.get("members", [])[:5],
            section_links=dashboard_data.get("links", {}),
            last_updated=news_update_time
        )
        
        # Write to temporary file first to preserve existing index.html on failure
        import tempfile
        temp_fd, temp_path = tempfile.mkstemp(suffix=".html", dir="docs", text=True)
        
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                f.write(dash_html)
            
            # Only replace the original file if write succeeded
            import shutil
            shutil.move(temp_path, "docs/index.html")
            print("[Dashboard] Index generated successfully.")
        except Exception as e:
            # Clean up temp file if it still exists
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise e
        
        # 5. Asset Deployment
        src_static = "static"
        dst_static = "docs/static"
        if os.path.exists(src_static):
            if os.path.exists(dst_static):
                shutil.rmtree(dst_static)
            shutil.copytree(src_static, dst_static)
            print(f"[Deployment] Copied {src_static} -> {dst_static}")
            
    except Exception as e:
        print(f"[Dashboard] Failed to render: {e}")
        print("[Dashboard] Keeping existing index.html to preserve service availability.")
        import traceback
        traceback.print_exc()

    # 5.5 Generate Mobile Briefing Page (CONDITIONAL)
    if total_new_items > 0:
        print(f"[Briefing] Found {total_new_items} new items. Generating mobile landing page...")
        try:
            briefing_html = render_mobile_landing(
                ai_items=dashboard_data.get("ai", [])[:10], # Ensure 2x items (10)
                xr_items=dashboard_data.get("xr", [])[:10],
                gov_items=dashboard_data.get("gov", [])[:10],
                links=dashboard_data.get("links", {})
            )
            with open("docs/briefing.html", "w", encoding="utf-8") as f:
                f.write(briefing_html)
            
            # Add briefing URL for notifier
            dashboard_data["briefing_url"] = "https://vaax-maker.github.io/ai-news-daily/briefing.html"
            print("[Briefing] Generated docs/briefing.html")
        except Exception as e:
            print(f"[Briefing] Failed: {e}")
            # Fallback to index if briefing fails
            dashboard_data["briefing_url"] = "https://vaax-maker.github.io/ai-news-daily/index.html"

        # 6. Send Notifications (Only if new items)
        print("[Notifier] Sending daily briefing...")
        try:
            send_daily_briefing(dashboard_data)
        except Exception as e:
            print(f"[Notifier] Failed: {e}")
    else:
        print("[Briefing] No new items found. Skipping briefing generation and notification.")

    # 5.6 Generate Admin Notifier Page (Always generate for admin access)
    print("[Admin] Generating admin notifier page...")
    try:
        from src.generators.html import render_admin_page
        admin_html = render_admin_page()
        with open("docs/admin.html", "w", encoding="utf-8") as f:
            f.write(admin_html)
        print("[Admin] Generated docs/admin.html")
    except Exception as e:
        print(f"[Admin] Failed: {e}")

if __name__ == "__main__":
    main()
