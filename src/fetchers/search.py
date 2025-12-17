"""Google News Search Fetcher with User-Agent support."""

import time
import logging
import urllib.parse
import requests
import feedparser
from typing import List, Tuple, Any, Optional

logger = logging.getLogger(__name__)

# User-Agent to bypass potential bot blocking
USER_AGENT = "Mozilla/5.0 (compatible; AINewsDailyBot/1.0; +https://vaax.github.io)"
REQUEST_TIMEOUT = 30


def fetch_search_news(
    keywords: List[str],
    limit: int = 10
) -> List[Tuple[float, str, str, str, Any]]:
    """
    Fetch news from Google News RSS for given keywords.
    
    Args:
        keywords: List of search keywords
        limit: Maximum number of results to return
        
    Returns:
        List of tuples: (timestamp, title, link, content, entry)
    """
    if not keywords:
        return []
    
    # Construct query: "Keyword1" OR "Keyword2" ...
    query_str = " OR ".join([f'"{k}"' for k in keywords])
    encoded_query = urllib.parse.quote(query_str)
    
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"
    headers = {"User-Agent": USER_AGENT}
    
    raw_items: List[Tuple[float, str, str, str, Any]] = []
    
    try:
        # Use requests with User-Agent
        response = requests.get(rss_url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        
        d = feedparser.parse(response.content)
        
        logger.info(f"[Search] Fetched {len(d.entries)} entries for keywords: {keywords}")
        
        for entry in d.entries:
            title = getattr(entry, "title", "")
            link = getattr(entry, "link", "")
            content = getattr(entry, "summary", "") or getattr(entry, "description", "")
            
            published = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
            ts = time.mktime(published) if published else 0
            
            raw_items.append((ts, title, link, content, entry))
            
    except requests.RequestException as e:
        logger.error(f"[Search] Request error for {keywords}: {e}")
        return []
    except Exception as e:
        logger.error(f"[Search] Parse error for {keywords}: {e}")
        return []

    # Sort by time desc
    raw_items.sort(key=lambda x: x[0], reverse=True)
    
    return raw_items[:limit]
