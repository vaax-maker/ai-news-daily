import time
import feedparser
import random
from typing import List, Dict, Any

def fetch_rss_items(feeds: List[str], selection_mode: str = "time", keyword_filters: List[str] = None) -> List[tuple]:
    raw_items = []
    
    for feed_url in feeds:
        try:
            d = feedparser.parse(feed_url)
            for entry in d.entries:
                title = getattr(entry, "title", "")
                link = getattr(entry, "link", "")
                content = getattr(entry, "summary", "") or getattr(entry, "description", "")
                
                published = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
                if published:
                    ts = time.mktime(published)
                else:
                    ts = 0
                
                raw_items.append((ts, title, link, content, entry))
        except Exception as e:
            print(f"[RSS Fetch Error] {feed_url}: {e}")

    # Keyword Filtering
    if keyword_filters:
        low_kws = [k.lower() for k in keyword_filters]
        if selection_mode == "keyword" or low_kws:
             raw_items = [
                item for item in raw_items
                if any(kw in ((item[1] or "") + " " + (item[3] or "")).lower() for kw in low_kws)
            ]

    # Time Filtering (Last 48 hours for robustness)
    two_days_ago = time.time() - 48 * 60 * 60
    filtered_items = [item for item in raw_items if item[0] >= two_days_ago]
    
    # Use filtered if we have enough items, else fallback to raw
    if len(filtered_items) >= 5:
        target_items = filtered_items
    else:
        target_items = raw_items

    # Sorting logic
    three_days_ago = time.time() - 3 * 24 * 60 * 60
    
    if selection_mode == "random":
        recent = [item for item in target_items if item[0] >= three_days_ago]
        candidates = recent if recent else target_items
        random.shuffle(candidates)
        return candidates
    else:
        # Default: time desc
        target_items.sort(key=lambda x: x[0], reverse=True)
        return target_items
