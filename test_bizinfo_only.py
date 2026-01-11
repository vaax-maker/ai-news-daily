
import logging
from src.fetchers.gov import fetch_bizinfo_announcements

logging.basicConfig(level=logging.INFO)

print("Fetching Bizinfo items...")
items = fetch_bizinfo_announcements(limit=20)
print(f"Fetched {len(items)} items from Bizinfo.")
for item in items:
    print(f"- {item['title']}")
