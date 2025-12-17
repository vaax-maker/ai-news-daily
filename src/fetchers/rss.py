"""RSS Feed Fetcher with User-Agent support for bot-blocking sites."""

import time
import random
import logging
import requests
import feedparser
from typing import List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

# User-Agent to bypass bot blocking on some RSS feeds
USER_AGENT = "Mozilla/5.0 (compatible; AINewsDailyBot/1.0; +https://vaax.github.io)"
REQUEST_TIMEOUT = 30


def fetch_rss_items(
    feeds: List[str],
    selection_mode: str = "time",
    keyword_filters: Optional[List[str]] = None
) -> List[Tuple[float, str, str, str, Any]]:
    """
    Fetch items from multiple RSS feeds.
    
    Args:
        feeds: List of RSS feed URLs
        selection_mode: 'time', 'random', or 'keyword'
        keyword_filters: Optional list of keywords to filter by
        
    Returns:
        List of tuples: (timestamp, title, link, content, entry)
    """
    raw_items: List[Tuple[float, str, str, str, Any]] = []
    headers = {"User-Agent": USER_AGENT}
    
    for feed_url in feeds:
        try:
            # Use requests with User-Agent to fetch the feed content
            response = requests.get(feed_url, headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            
            # Parse the fetched content with feedparser
            d = feedparser.parse(response.content)
            
            entries_count = len(d.entries)
            if entries_count == 0:
                logger.warning(f"[RSS] No entries from {feed_url}")
            else:
                logger.info(f"[RSS] Fetched {entries_count} entries from {feed_url}")
            
            for entry in d.entries:
                title = getattr(entry, "title", "")
                link = getattr(entry, "link", "")
                content = getattr(entry, "summary", "") or getattr(entry, "description", "")
                
                published = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
                ts = time.mktime(published) if published else 0
                
                raw_items.append((ts, title, link, content, entry))
                
        except requests.RequestException as e:
            logger.error(f"[RSS] Request error for {feed_url}: {e}")
        except Exception as e:
            logger.error(f"[RSS] Parse error for {feed_url}: {e}")

    # Keyword Filtering
    if keyword_filters:
        low_kws = [k.lower() for k in keyword_filters]
        raw_items = [
            item for item in raw_items
            if any(kw in ((item[1] or "") + " " + (item[3] or "")).lower() for kw in low_kws)
        ]
        logger.info(f"[RSS] After keyword filter: {len(raw_items)} items")

    # Time Filtering (Last 48 hours for robustness)
    two_days_ago = time.time() - 48 * 60 * 60
    filtered_items = [item for item in raw_items if item[0] >= two_days_ago]
    
    # Use filtered if we have enough items, else fallback to raw
    target_items = filtered_items if len(filtered_items) >= 5 else raw_items

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
