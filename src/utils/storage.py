import json
import os
import re
from difflib import SequenceMatcher
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
        Merge new items with existing items for a member.

        Rules:
        1. Keep only articles between 2025-01-01 and now.
        2. Deduplicate by link *or* similar normalized titles.
        3. Always accumulate unique items onto previous results.
        4. Allow at most two articles per member for the same calendar date.
        """
        import datetime

        existing = self.load_news(member_id)

        cutoff_date = datetime.datetime(2025, 1, 1).timestamp()
        now_ts = datetime.datetime.now().timestamp()

        def normalize(s):
            cleaned = re.sub(r"[^0-9A-Za-z가-힣]", "", s)
            return cleaned.lower()

        def is_similar_title(norm_title: str, seen_titles: List[str], threshold: float = 0.9) -> bool:
            return any(SequenceMatcher(None, norm_title, seen).ratio() >= threshold for seen in seen_titles)

        def dedup_items(items):
            seen_links = set()
            seen_titles: List[str] = []
            cleaned = []
            for item in sorted(items, key=lambda x: x.get("timestamp", 0), reverse=True):
                link = item.get("link")
                title = item.get("title", "")
                norm_title = normalize(title)

                if link in seen_links:
                    continue
                if norm_title and is_similar_title(norm_title, seen_titles):
                    continue

                seen_links.add(link)
                if norm_title:
                    seen_titles.append(norm_title)
                cleaned.append(item)
            return cleaned

        def is_salrin_noun(title: str) -> bool:
            if not title or "살린" not in title:
                return False

            # Accept explicit romanization mentions as a proper noun.
            if re.search(r"\bSALIN\b", title, flags=re.IGNORECASE):
                return True

            verb_like_patterns = [
                # Object + 살린 + noun (e.g., "김수용 살린 김숙", "생명 살린 의용소방대원")
                r"[가-힣A-Za-z0-9][\)\]\"'’”]?\s*살린\s+[가-힣0-9]",
                # Past-tense clause tails such as "살린 뒤", "살린 후", "살린 적"
                r"살린\s+(뒤|후|채|적|줄|상황|점|것)",
            ]

            for pat in verb_like_patterns:
                if re.search(pat, title):
                    return False

            return True

        def apply_member_specific_filters(items: List[Dict]) -> List[Dict]:
            if member_id == "살린":
                filtered = []
                for item in items:
                    if is_salrin_noun(item.get("title", "")) or is_salrin_noun(item.get("original_title", "")):
                        filtered.append(item)
                return filtered
            return items

        def within_range(item):
            ts = item.get("timestamp", 0)
            return cutoff_date <= ts <= now_ts

        def enforce_daily_limit(items, limit_per_date: int = 2):
            counts = {}
            limited = []
            for item in items:
                ts = item.get("timestamp", 0)
                date_key = datetime.datetime.fromtimestamp(ts).date()
                counts.setdefault(date_key, 0)
                if counts[date_key] >= limit_per_date:
                    continue
                counts[date_key] += 1
                limited.append(item)
            return limited

        cleaned_existing = dedup_items(apply_member_specific_filters([item for item in existing if within_range(item)]))
        cleaned_new = apply_member_specific_filters([item for item in new_items if within_range(item)])

        merged = dedup_items(cleaned_existing + cleaned_new)
        merged.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        merged = enforce_daily_limit(merged)

        try:
            with open(self._get_path(member_id), "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Storage] Failed to save {member_id}: {e}")

        return merged


class GovStorage:
    def __init__(self, data_path: str = "data/gov/announcements.json"):
        self.data_path = data_path
        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)

    def load_announcements(self) -> List[Dict]:
        if not os.path.exists(self.data_path):
            return []
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Storage] Failed to load gov announcements: {e}")
            return []

    def save_announcements(self, new_items: List[Dict]) -> List[Dict]:
        """
        Accumulate government announcements onto the first captured list while
        removing duplicates by link or similar normalized titles. Newly fetched
        items are placed before existing ones so the latest entries appear first.
        """

        def normalize(text: str) -> str:
            cleaned = re.sub(r"[^0-9A-Za-z가-힣]", "", text or "")
            return cleaned.lower()

        def is_similar_title(norm_title: str, seen_titles: List[str], threshold: float = 0.9) -> bool:
            return any(SequenceMatcher(None, norm_title, seen).ratio() >= threshold for seen in seen_titles)

        def merge_items(existing: List[Dict], incoming: List[Dict]) -> List[Dict]:
            seen_links = set()
            seen_titles: List[str] = []
            merged: List[Dict] = []

            def add_item(item: Dict):
                link = item.get("link")
                norm_title = normalize(item.get("title", ""))

                if link and link in seen_links:
                    return
                if norm_title and is_similar_title(norm_title, seen_titles):
                    return

                if link:
                    seen_links.add(link)
                if norm_title:
                    seen_titles.append(norm_title)
                merged.append(item)

            for item in incoming:
                add_item(item)
            for item in existing:
                add_item(item)

            return merged

        existing_items = self.load_announcements()
        merged = merge_items(existing_items, new_items)

        try:
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Storage] Failed to save gov announcements: {e}")

        return merged
