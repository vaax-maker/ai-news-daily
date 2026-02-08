#!/usr/bin/env python3
"""
Manually trigger Government Projects update and regenerate Dashboard.
"""

import sys
import os
import datetime
import logging

# Adjust path to find src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.fetchers.gov import fetch_gov_announcements
from src.utils.storage import GovStorage
from src.generators.html import render_gov_archive, render_dashboard
from src.config import load_categories

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("🚀 Starting manual Government Projects update...")

    # 1. Fetch latest data
    try:
        logger.info("Fetching government announcements...")
        items = fetch_gov_announcements(limit=50)
        logger.info(f"Fetched {len(items)} items.")
    except Exception as e:
        logger.error(f"Failed to fetch gov items: {e}")
        return

    # 2. Save to storage
    try:
        storage = GovStorage()
        saved_items = storage.save_announcements(items)
        logger.info(f"Saved {len(saved_items)} items to storage.")
    except Exception as e:
        logger.error(f"Failed to save to storage: {e}")
        return

    # 3. Regenerate Gov Index
    try:
        # Sort by date
        def sort_key(item):
            date_str = item.get("date") or item.get("published_display") or ""
            try:
                return datetime.datetime.strptime(date_str, "%Y-%m-%d")
            except:
                return datetime.datetime.min
        
        saved_items.sort(key=sort_key, reverse=True)
        
        logger.info("Regenerating docs/gov/index.html...")
        html = render_gov_archive(saved_items)
        
        os.makedirs("docs/gov", exist_ok=True)
        with open("docs/gov/index.html", "w", encoding="utf-8") as f:
            f.write(html)
        logger.info("✅ Gov index regenerated.")
    except Exception as e:
        logger.error(f"Failed to regenerate gov index: {e}")

    # 4. Regenerate Dashboard (docs/index.html)
    try:
        logger.info("Regenerating Dashboard (docs/index.html)...")
        from src.config import load_categories
        from main import load_latest_articles_from_archive, sort_gov_announcements, load_existing_members_latest
        
        # Load existing data for other sections to preserve them
        categories = load_categories()
        dashboard_data = {
            "ai": [],
            "xr": [],
            "gov": saved_items[:5], # Use the newly fetched items
            "members": [],
            "links": {}
        }

        # Load latest AI/XR from archive
        for key in ["ai", "xr"]:
            if key in categories:
                dashboard_data[key] = load_latest_articles_from_archive(categories[key])
                # Resolve link
                from main import latest_daily_page_path
                fallback_path = latest_daily_page_path(categories[key])
                if fallback_path:
                    dashboard_data["links"][key] = fallback_path

        # Load members
        dashboard_data["members"] = load_existing_members_latest()
        dashboard_data["links"]["members"] = "members/index.html"
        dashboard_data["links"]["gov"] = "gov/index.html"

        # Quickview
        quickview_latest = []
        try:
            from generate_quickview import get_latest_quickviews
            quickview_latest = get_latest_quickviews(limit=5)
            dashboard_data["links"]["quickview"] = "quickview/index.html"
        except:
            pass

        # Time
        last_updated = "정보 없음"
        if os.path.exists("docs/last_update.txt"):
            with open("docs/last_update.txt", "r", encoding="utf-8") as f:
                last_updated = f.read().strip()

        # Render
        dash_html = render_dashboard(
            ai_latest=dashboard_data["ai"],
            xr_latest=dashboard_data["xr"],
            gov_latest=dashboard_data["gov"],
            quickview_latest=quickview_latest,
            members_latest=dashboard_data["members"],
            section_links=dashboard_data["links"],
            last_updated=last_updated
        )

        with open("docs/index.html", "w", encoding="utf-8") as f:
            f.write(dash_html)
        
        logger.info("✅ Dashboard regenerated successfully.")

    except Exception as e:
        logger.error(f"Failed to regenerate dashboard: {e}")
        import traceback
        traceback.print_exc()

    logger.info("🎉 Gov Update Complete.")

if __name__ == "__main__":
    main()
