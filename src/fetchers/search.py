import time
import urllib.parse
import feedparser
from typing import List

def fetch_search_news(keywords: List[str], limit: int = 10) -> List[tuple]:
    if not keywords:
        return []
    
    # Construct query: "Keyword1" OR "Keyword2" ...
    # Quoting keywords to ensure exact match and reduce noise
    query_str = " OR ".join([f'"{k}"' for k in keywords])
    encoded_query = urllib.parse.quote(query_str)
    
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"
    
    raw_items = []
    try:
        d = feedparser.parse(rss_url)
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
        print(f"[Search Fetch Error] Query={keywords}: {e}")
        return []

    # Sort by time desc
    raw_items.sort(key=lambda x: x[0], reverse=True)
    
    return raw_items[:limit]
