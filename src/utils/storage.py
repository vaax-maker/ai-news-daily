import json
import os
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
        3. Prepend new items (incremental).
        """
        import datetime
        
        existing = self.load_news(member_id)
        
        # 1. Date Filter Limit
        cutoff_date = datetime.datetime(2025, 1, 1).timestamp()
        
        # Helper to normalize title for dedup
        def normalize(s):
            return "".join(s.split()).lower()

        # Build set of existing signatures
        seen_links = {item['link'] for item in existing}
        seen_titles = {normalize(item['title']) for item in existing if 'title' in item}
        
        unique_new = []
        for item in new_items:
            # Date Check
            ts = item.get('timestamp', 0)
            if ts < cutoff_date:
                continue
                
            # Dedup Check
            norm_title = normalize(item['title'])
            if item['link'] in seen_links:
                continue
            if norm_title in seen_titles:
                continue
                
            unique_new.append(item)
            seen_links.add(item['link'])
            seen_titles.add(norm_title)
                
        if not unique_new:
            return existing # No change
            
        # Prepend new items
        merged = unique_new + existing
        
        # Sort by timestamp desc just in case
        merged.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        
        try:
            with open(self._get_path(member_id), "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Storage] Failed to save {member_id}: {e}")
            
        return merged
