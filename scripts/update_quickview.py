#!/usr/bin/env python3
"""
Update quickview pages and regenerate dashboard.
This script is called by the admin-notifications workflow every 5 minutes.
"""

import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.generators.quickview import process_quickview_pages, get_latest_quickviews
from src.generators.html import render_dashboard
from src.utils.storage import GovStorage
from main import load_latest_articles_from_archive, load_categories


def main():
    print("[Quickview Update] Starting...")
    
    # 1. Generate quickview HTML pages from Firestore
    try:
        pages = process_quickview_pages()
        print(f"[Quickview Update] Generated {len(pages)} quickview pages")
    except Exception as e:
        print(f"[Quickview Update] Failed to generate pages: {e}")
        return
    
    # 2. Update dashboard with latest quickviews
    try:
        quickview_latest = get_latest_quickviews(limit=5)
        print(f"[Quickview Update] Got {len(quickview_latest)} latest quickviews for dashboard")
        
        # Load last update time
        update_time_file = "docs/last_update.txt"
        if os.path.exists(update_time_file):
            with open(update_time_file, 'r') as f:
                news_update_time = f.read().strip()
        else:
            from src.utils.common import get_kst_now
            news_update_time = get_kst_now().strftime("%Y년 %m월 %d일 %H시 %M분")
        
        # Load other dashboard data
        categories = load_categories()
        ai_latest = load_latest_articles_from_archive(categories['ai'], limit=5)
        xr_latest = load_latest_articles_from_archive(categories['xr'], limit=5)
        
        storage = GovStorage()
        gov_latest = storage.load_announcements()[:5]
        
        links = {
            'ai': 'ai/index.html',
            'xr': 'xr/index.html',
            'gov': 'gov/index.html',
            'quickview': 'quickview/index.html'
        }
        
        # Load Key Message
        key_message = None
        key_message_file = "data/latest_key_message.json"
        if os.path.exists(key_message_file):
            try:
                import json
                with open(key_message_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    key_message = data.get("key_message")
            except Exception as e:
                print(f"[Quickview Update] Error loading key message: {e}")

        # Render dashboard
        dash_html = render_dashboard(
            ai_latest=ai_latest,
            xr_latest=xr_latest,
            gov_latest=gov_latest,
            quickview_latest=quickview_latest,
            section_links=links,
            last_updated=news_update_time,
            key_message=key_message
        )
        
        with open('docs/index.html', 'w', encoding='utf-8') as f:
            f.write(dash_html)
        
        print("[Quickview Update] Dashboard updated successfully!")
        
    except Exception as e:
        print(f"[Quickview Update] Failed to update dashboard: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
