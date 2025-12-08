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
        Merge new items with existing items, deduplicate by link.
        Prepend new items.
        """
        existing = self.load_news(member_id)
        
        # Dedup logic: Use set of links
        seen_links = {item['link'] for item in existing}
        
        unique_new = []
        for item in new_items:
            if item['link'] not in seen_links:
                unique_new.append(item)
                seen_links.add(item['link'])
                
        if not unique_new:
            return existing # No change
            
        # Prepend new items
        merged = unique_new + existing
        
        # Limit total history? (Optional, say 100 items)
        merged = merged[:100]
        
        try:
            with open(self._get_path(member_id), "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Storage] Failed to save {member_id}: {e}")
            
        return merged
