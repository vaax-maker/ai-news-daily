import json
import os
import re
from typing import List, Dict

class MemberStorage:
    def __init__(self, data_dir="data/members"):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        
    def _get_path(self, member_id: str) -> str:
        return os.path.join(self.data_dir, f"{member_id}.json")
        
    def load_news(self, member_id: str) -> List[Dict]:
        path = self._get_path(member_id)
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Storage] Failed to load {member_id}: {e}")
            return []
            
    def save_news(self, member_id: str, new_items: List[Dict]):
        """
        Merge new items with existing items.
        Rules:
        1. Filter out items older than 2025-01-01.
        2. Deduplicate by link AND normalized title.
        3. Only accumulate items newer than the latest stored article.
        """
        import datetime

        existing = self.load_news(member_id)

        # 1. Date Filter Limit
        cutoff_date = datetime.datetime(2025, 1, 1).timestamp()

        def normalize(s):
            cleaned = re.sub(r"[^0-9A-Za-z가-힣]", "", s)
            return cleaned.lower()

        def dedup_items(items):
            seen_links = set()
            seen_titles = set()
            cleaned = []
            for item in sorted(items, key=lambda x: x.get("timestamp", 0), reverse=True):
                link = item.get("link")
                title = item.get("title", "")
                norm_title = normalize(title)

                if link in seen_links or norm_title in seen_titles:
                    continue

                seen_links.add(link)
                seen_titles.add(norm_title)
                cleaned.append(item)
            return cleaned

        # Clean existing articles up-front (date + duplicates)
        existing = [item for item in existing if item.get('timestamp', 0) >= cutoff_date]
        existing = dedup_items(existing)

        latest_existing_ts = max([item.get('timestamp', 0) for item in existing], default=0)

        unique_new = []
        for item in new_items:
            # Date Check
            ts = item.get('timestamp', 0)
            if ts < cutoff_date:
                continue

            # Skip anything older than the latest stored article
            if latest_existing_ts and ts <= latest_existing_ts:
                continue

            # Dedup Check against cleaned existing + new batch
            norm_title = normalize(item.get('title', ''))
            existing_links = {i.get('link') for i in existing}
            existing_titles = {normalize(i.get('title', '')) for i in existing}
            new_links = {n.get('link') for n in unique_new}
            new_titles = {normalize(n.get('title', '')) for n in unique_new}

            if item.get('link') in existing_links or item.get('link') in new_links:
                continue
            if norm_title in existing_titles or norm_title in new_titles:
                continue

            unique_new.append(item)

        # Combine and save if needed
        merged = dedup_items(unique_new + existing)

        # Sort by timestamp desc just in case
        merged.sort(key=lambda x: x.get("timestamp", 0), reverse=True)

        try:
            with open(self._get_path(member_id), "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Storage] Failed to save {member_id}: {e}")
            
        return merged
