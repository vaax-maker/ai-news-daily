#!/usr/bin/env python3
"""
Rebuild all HTML pages across the site using existing data and updated templates.
No API calls are made.
"""

import os
import re
import datetime
import json
from bs4 import BeautifulSoup

from src.generators.html import (
    render_member_page,
    render_member_index,
    render_archive_index,
    render_dashboard,
    render_board_page,
    render_gov_archive,
    render_admin_page,
    render_guide_page,
    render_quickview_index
)
from src.config import CategoryConfig, load_members, load_categories
from src.utils.storage import MemberStorage, GovStorage

def parse_preview_from_html(html_path, limit=5):
    """HTML 파일에서 제목과 메타 정보를 추출하여 요약 목록 생성"""
    if not os.path.exists(html_path):
        return []

    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    previews = []
    # 최신 템플릿은 .news-item 클래스를 사용함
    for article in soup.select(".news-item")[:limit]:
        title_el = article.select_one(".news-title a")
        meta_el = article.select_one(".news-meta")

        source_name = ""
        published_display = ""

        if meta_el:
            # "출처 | 날짜" 형식을 파싱
            text = meta_el.get_text(" ", strip=True)
            if "·" in text:
                parts = text.split("·")
                source_name = parts[0].strip()
                published_display = parts[1].strip()
            elif "|" in text:
                parts = text.split("|")
                source_name = parts[0].strip()
                published_display = parts[1].strip()
            else:
                published_display = text

        # "NEW" 뱃지 확인 (process_manual_articles.py 등에서 생성된 마크업)
        is_new = False
        if article.select_one(".new-badge"):
            is_new = True

        previews.append({
            "title": title_el.get_text(strip=True) if title_el else "제목 없음",
            "link": title_el.get("href") if title_el else "#",
            "source_name": source_name,
            "published_display": published_display,
            "is_new": is_new
        })
    return previews

def rebuild_members():
    print("--- [Members] Rebuilding... ---")
    members = load_members()
    storage = MemberStorage()
    member_page_dir = "docs/members"
    os.makedirs(member_page_dir, exist_ok=True)
    
    member_entries = []
    all_latest_news = []
    
    for m_key, member in members.items():
        try:
            history = storage.load_news(m_key)
            history.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            
            now_str = datetime.datetime.now().strftime("%Y-%m-%d")
            html = render_member_page(member, history, now_str)
            
            safe_name = re.sub(r'[<>:"/\\|?*]', '_', m_key).strip()
            page_filename = f"{safe_name}.html"
            
            with open(os.path.join(member_page_dir, page_filename), "w", encoding="utf-8") as f:
                f.write(html)
            
            # Index data
            latest_str = "-"
            latest_title = ""
            latest_link = ""
            if history:
                latest = history[0]
                latest_str = latest.get("published_display", "-")
                latest_title = latest.get("title", "")
                latest_link = latest.get("link", "")
            
            member_entries.append({
                "filename": page_filename,
                "name": member.name,
                "count": len(history),
                "latest_date": latest_str,
                "latest_title": latest_title,
                "latest_link": latest_link
            })
            all_latest_news.extend(history[:2])
        except Exception as e:
            print(f"  Error {member.name}: {e}")

    # Index
    member_entries.sort(key=lambda x: (-x["count"], x["name"]))
    all_latest_news.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    
    # Filter today's news for index grid
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    today_start = datetime.datetime.strptime(today_str, "%Y-%m-%d").timestamp()
    todays_news = [n for n in all_latest_news if n.get("timestamp", 0) >= today_start]
    
    idx_html = render_member_index(member_entries, all_news=todays_news)
    with open("docs/members/index.html", "w", encoding="utf-8") as f:
        f.write(idx_html)
    
    print(f"✓ Member Index & {len(member_entries)} pages done.")
    return all_latest_news[:5]

def rebuild_archives():
    print("\n--- [Archives] Rebuilding... ---")
    categories = load_categories()
    dashboard_previews = {}
    dashboard_links = {}

    for key in ["ai", "xr"]:
        config = categories.get(key)
        if not config: continue
        
        daily_dir = os.path.join("docs", key, "daily")
        if not os.path.exists(daily_dir): continue
        
        files = sorted([f for f in os.listdir(daily_dir) if f.endswith(".html")], reverse=True)
        run_entries = []
        for f in files:
            parts = f.replace(".html", "").split("_")
            if len(parts) == 2:
                # Calculate day of week
                try:
                    dt = datetime.datetime.strptime(parts[0], "%Y-%m-%d")
                    weekday_map = {0:'월', 1:'화', 2:'수', 3:'목', 4:'금', 5:'토', 6:'일'}
                    day_of_week = weekday_map[dt.weekday()]
                except:
                    day_of_week = ""
                
                run_entries.append({
                    "date_str": parts[0], 
                    "time_str": parts[1], 
                    "filename": f,
                    "day_of_week": day_of_week
                })
        
        # Index
        idx_html = render_archive_index(run_entries, config)
        with open(os.path.join("docs", key, "index.html"), "w", encoding="utf-8") as f:
            f.write(idx_html)
        
        # Dashboard previews
        if files:
            latest_path = os.path.join(daily_dir, files[0])
            dashboard_previews[key] = parse_preview_from_html(latest_path)
            dashboard_links[key] = f"{key}/daily/{files[0]}"
        
        print(f"✓ {key.upper()} Index done.")
    
    return dashboard_previews, dashboard_links

def rebuild_gov():
    print("\n--- [Gov] Rebuilding... ---")
    storage = GovStorage()
    announcements = storage.load_announcements()
    # Sort by date desc
    announcements.sort(key=lambda x: x.get("date", ""), reverse=True)
    
    html = render_gov_archive(announcements)
    with open("docs/gov/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"✓ Gov Index done.")
    return announcements[:5]

def rebuild_board():
    print("\n--- [Board] Rebuilding... ---")
    os.makedirs("docs/board", exist_ok=True)
    html = render_board_page()
    with open("docs/board/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✓ Board done.")

def rebuild_admin():
    print("\n--- [Admin] Rebuilding... ---")
    html = render_admin_page()
    with open("docs/admin.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✓ Admin done.")

def rebuild_guide():
    print("\n--- [Guide] Rebuilding... ---")
    html = render_guide_page()
    with open("docs/guide.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("✓ Guide Page done.")

def rebuild_quickview():
    print("\n--- [Quickview] Rebuilding... ---")
    qv_dir = "docs/quickview"
    if not os.path.exists(qv_dir):
        print("No quickview directory found.")
        return []
    
    files = [f for f in os.listdir(qv_dir) if f.endswith(".html") and f != "index.html"]
    pages = []
    
    for f in files:
        path = os.path.join(qv_dir, f)
        try:
            with open(path, "r", encoding="utf-8") as file:
                soup = BeautifulSoup(file, "html.parser")
                
            title_el = soup.select_one(".quickview-title")
            meta_el = soup.select_one(".quickview-meta")
            
            title = title_el.get_text(strip=True) if title_el else "제목 없음"
            date_str = meta_el.get_text(strip=True).replace("📅", "").strip() if meta_el else ""
            
            # Parse date for sorting
            # Parse date for sorting
            created_at = 0
            
            # 1. Try to read from meta tag first (most reliable)
            meta_ts = soup.select_one("meta[name='created-at']")
            if meta_ts and meta_ts.get("content"):
                try:
                    created_at = float(meta_ts.get("content"))
                except ValueError:
                    pass

            # 2. Fallback to text parsing if meta tag missing
            if created_at == 0 and date_str:
                try:
                    # Remove " AM" or " PM" if present
                    clean_date = date_str.replace(" PM", "").replace(" AM", "")
                    # Try various formats
                    dt = datetime.datetime.strptime(clean_date, "%Y년 %m월 %d일 %H:%M")
                    created_at = dt.timestamp()
                except:
                    # Fallback for other formats
                    pass
            
            # 3. Last resort: file mtime
            if created_at == 0:
                created_at = os.path.getmtime(path)

            pages.append({
                "id": f.replace(".html", ""),
                "url": f"quickview/{f}", # Dashboard link relative to docs root
                "title": title,
                "created_at": created_at,
                "created_display": date_str,
                "is_new": False # Logic for new could be added if needed
            })
        except Exception as e:
            print(f"Error parsing {f}: {e}")
            
    # Sort by date desc
    pages.sort(key=lambda x: x["created_at"], reverse=True)
    
    # Render Index
    idx_html = render_quickview_index(pages)
    with open(os.path.join("docs/quickview/index.html"), "w", encoding="utf-8") as f:
        f.write(idx_html)
    print(f"✓ Quickview Index done. ({len(pages)} pages)")
    
    return pages

def rebuild_dashboard(ai_previews, xr_previews, gov_previews, member_previews, quickview_previews, links):
    print("\n--- [Dashboard] Rebuilding... ---")
    # Clean up previews for dashboard format
    # The template expects specific fields
    
    # Gov previews formatting
    gov_formatted = []
    for item in gov_previews:
        gov_formatted.append({
            "title": item.get("title"),
            "link": item.get("link"),
            "published_display": item.get("date"),
            "dept": item.get("dept")
        })

    # Members previews formatting
    member_formatted = []
    for item in member_previews:
        member_formatted.append({
            "title": item.get("title"),
            "link": item.get("link"),
            "published_display": item.get("published_display"),
            "member_name": item.get("member_name")
        })

    # Read saved news update time (from main.py's last run)
    last_update_file = "docs/last_update.txt"
    if os.path.exists(last_update_file):
        with open(last_update_file, "r", encoding="utf-8") as f:
            saved_update_time = f.read().strip()
    else:
        saved_update_time = "정보 없음"

    html = render_dashboard(
        ai_latest=ai_previews,
        xr_latest=xr_previews,
        gov_latest=gov_formatted,
        quickview_latest=quickview_previews,
        members_latest=member_formatted,
        section_links=links,
        last_updated=saved_update_time
    )
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✓ Dashboard done.")

if __name__ == "__main__":
    m_latest = rebuild_members()
    a_previews, links = rebuild_archives()
    g_latest = rebuild_gov()
    rebuild_board()
    rebuild_admin()
    rebuild_guide()
    qv_latest = rebuild_quickview()
    
    # Additional links
    links["members"] = "members/index.html"
    links["gov"] = "gov/index.html"
    links["quickview"] = "quickview/index.html"
    
    rebuild_dashboard(
        ai_previews=a_previews.get("ai", []),
        xr_previews=a_previews.get("xr", []),
        gov_previews=g_latest,
        member_previews=m_latest,
        quickview_previews=qv_latest[:5],
        links=links
    )
    
    # 5. Asset Deployment (Sync static folders)
    import shutil
    src_static = "static"
    dst_static = "docs/static"
    if os.path.exists(src_static):
        if os.path.exists(dst_static):
            shutil.rmtree(dst_static)
        shutil.copytree(src_static, dst_static)
        print(f"[Deployment] Copied {src_static} -> {dst_static}")
    
    print("\n✨ All HTML pages have been rebuild with new templates and assets synced!")
