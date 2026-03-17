import json
import os
import re
import hashlib
from difflib import SequenceMatcher
from typing import List, Dict


class MemberStorage:
    def __init__(self, data_dir="data/members"):
        self.use_firestore = os.getenv("FIRESTORE_ENABLED", "false").lower() == "true"
        self.data_dir = data_dir
        self._db = None
        if not self.use_firestore:
            os.makedirs(self.data_dir, exist_ok=True)

    @property
    def db(self):
        """지연 초기화 — 첫 Firestore 호출 시에만 연결."""
        if self._db is None:
            from src.generators.quickview import get_firestore_client
            self._db = get_firestore_client()
        return self._db

    def _get_path(self, member_id: str) -> str:
        return os.path.join(self.data_dir, f"{member_id}.json")

    def load_news(self, member_id: str) -> List[Dict]:
        if self.use_firestore:
            return self._load_from_firestore(member_id)
        return self._load_from_json(member_id)

    def save_news(self, member_id: str, new_items: List[Dict]):
        if self.use_firestore:
            return self._save_to_firestore(member_id, new_items)
        return self._save_to_json(member_id, new_items)

    # --- JSON backend (기존 로직 그대로) ---

    def _load_from_json(self, member_id: str) -> List[Dict]:
        path = self._get_path(member_id)
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Storage] Failed to load {member_id}: {e}")
            return []

    def _save_to_json(self, member_id: str, new_items: List[Dict]):
        """
        Merge new items with existing items for a member.

        Rules:
        1. Keep only articles between 2025-01-01 and now.
        2. Deduplicate by link *or* similar normalized titles.
        3. Always accumulate unique items onto previous results.
        4. Allow at most two articles per member for the same calendar date.
        """
        import datetime

        existing = self._load_from_json(member_id)

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
            for item in sorted(items, key=lambda x: x.get("timestamp", 0)):
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
            """Check if '살린' in title is used as a proper noun (company name), not a verb."""
            if not title or "살린" not in title:
                return False

            if re.search(r"\bSALIN\b", title, flags=re.IGNORECASE):
                return True

            if title.strip().startswith("살린"):
                return True

            verb_like_patterns = [
                r"[가-힣A-Za-z0-9\)\]\"\''\"]\s*살린\s+[가-힣]",
                r"[을를이가도은는]\s*살린",
                r"살린\s*(뒤|후|채|적|줄|상황|점|것|이|건|덕|힘|게|데|곳)",
                r"살린\s*['\"\'']",
                r"(불씨|기회|우위|특성|장점|개성|맛|멋|전통|가치|정신|분위기)\s*살린",
                r"[가-힣]+[를을]\s*살린",
                r"못\s*살린",
                r"(회사|사람|생명|청년|아이|환자|목숨|팀|기업|농어촌|경제|마을|동네)\s*살린",
                r"망해가던.*살린",
                r"벼랑.*살린",
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

        os.makedirs(self.data_dir, exist_ok=True)
        try:
            with open(self._get_path(member_id), "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Storage] Failed to save {member_id}: {e}")

        return merged

    # --- Firestore backend (신규) ---

    def _doc_id(self, link: str) -> str:
        return hashlib.md5(link.encode()).hexdigest()[:16]

    def _load_from_firestore(self, member_id: str) -> List[Dict]:
        """Firestore members/{member_id}/news 컬렉션에서 로드."""
        try:
            docs = self.db.collection("members").document(member_id).collection("news").stream()
            return [doc.to_dict() for doc in docs]
        except Exception as e:
            print(f"[Storage/Firestore] Failed to load {member_id}: {e}")
            return []

    def _save_to_firestore(self, member_id: str, new_items: List[Dict]) -> List[Dict]:
        """기존 dedup 로직 유지, Firestore에 저장."""
        # 기존 JSON 경로로 dedup 처리 후 Firestore에 저장
        # 임시로 JSON 경로를 통해 dedup 수행
        existing = self._load_from_firestore(member_id)
        import datetime
        cutoff_date = datetime.datetime(2025, 1, 1).timestamp()
        now_ts = datetime.datetime.now().timestamp()

        def normalize(s):
            cleaned = re.sub(r"[^0-9A-Za-z가-힣]", "", s)
            return cleaned.lower()

        def is_similar(norm_title: str, seen_titles: List[str], threshold: float = 0.9) -> bool:
            return any(SequenceMatcher(None, norm_title, seen).ratio() >= threshold for seen in seen_titles)

        seen_links = {item.get("link") for item in existing if item.get("link")}
        seen_titles = [normalize(item.get("title", "")) for item in existing if item.get("title")]

        col_ref = self.db.collection("members").document(member_id).collection("news")
        added = 0
        for item in new_items:
            ts = item.get("timestamp", 0)
            if not (cutoff_date <= ts <= now_ts):
                continue
            link = item.get("link", "")
            if link in seen_links:
                continue
            norm_title = normalize(item.get("title", ""))
            if norm_title and is_similar(norm_title, seen_titles):
                continue
            doc_id = self._doc_id(link) if link else None
            if doc_id:
                col_ref.document(doc_id).set(item)
            else:
                col_ref.add(item)
            seen_links.add(link)
            if norm_title:
                seen_titles.append(norm_title)
            added += 1

        if added:
            print(f"[Storage/Firestore] Saved {added} new items for {member_id}")
        return existing + [i for i in new_items if i.get("link") in seen_links]


class GovStorage:
    def __init__(self, data_path: str = "data/gov/announcements.json"):
        self.use_firestore = os.getenv("FIRESTORE_ENABLED", "false").lower() == "true"
        self.data_path = data_path
        self._db = None
        # JSON 백업 디렉토리는 항상 생성 (Firestore 사용 시에도 백업용)
        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)

    @property
    def db(self):
        if self._db is None:
            from src.generators.quickview import get_firestore_client
            self._db = get_firestore_client()
        return self._db

    def _doc_id(self, link: str) -> str:
        return hashlib.md5(link.encode()).hexdigest()[:16]

    def load_announcements(self) -> List[Dict]:
        if self.use_firestore:
            data = self._load_from_firestore()
            if data:
                return data
            # Firestore 실패 또는 빈 데이터 → 로컬 JSON 자동 폴백
            print("[GovStorage] Firestore 데이터 없음/실패 → 로컬 JSON 폴백")
            return self._load_from_json()
        return self._load_from_json()

    def save_announcements(self, new_items: List[Dict]) -> List[Dict]:
        if self.use_firestore:
            merged = self._save_to_firestore(new_items)
            # Firestore 저장 후 로컬 JSON에도 항상 백업 (폴백 안전망)
            self._backup_to_json(merged)
            return merged
        return self._save_to_json(new_items)

    # --- JSON backend (기존 로직 그대로) ---

    def _load_from_json(self) -> List[Dict]:
        if not os.path.exists(self.data_path):
            return []
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Storage] Failed to load gov announcements: {e}")
            return []

    def _save_to_json(self, new_items: List[Dict]) -> List[Dict]:
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

            def add_item(item: Dict, is_new: bool):
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

                item["is_new"] = is_new
                merged.append(item)

            for item in existing:
                add_item(item, is_new=False)
            for item in incoming:
                add_item(item, is_new=True)

            return merged

        existing_items = self._load_from_json()
        merged = merge_items(existing_items, new_items)
        merged.sort(key=lambda x: x.get('date', '') or x.get('published_display', ''), reverse=True)

        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
        try:
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Storage] Failed to save gov announcements: {e}")

        return merged

    def _backup_to_json(self, merged: List[Dict]) -> None:
        """Firestore 데이터를 로컬 JSON에 백업 저장 (폴백 안전망)."""
        try:
            os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)
            print(f"[GovStorage] 로컬 JSON 백업 완료: {len(merged)}건 → {self.data_path}")
        except Exception as e:
            print(f"[GovStorage] 로컬 JSON 백업 실패: {e}")

    # --- Firestore backend ---

    def _load_from_firestore(self) -> List[Dict]:
        try:
            docs = self.db.collection("gov").document("announcements").collection("items").stream()
            return [doc.to_dict() for doc in docs]
        except Exception as e:
            print(f"[Storage/Firestore] Failed to load gov announcements: {e}")
            return []

    def _save_to_firestore(self, new_items: List[Dict]) -> List[Dict]:
        existing = self._load_from_firestore()

        def normalize(text: str) -> str:
            cleaned = re.sub(r"[^0-9A-Za-z가-힣]", "", text or "")
            return cleaned.lower()

        def is_similar(norm_title: str, seen_titles: List[str], threshold: float = 0.9) -> bool:
            return any(SequenceMatcher(None, norm_title, seen).ratio() >= threshold for seen in seen_titles)

        seen_links = {item.get("link") for item in existing if item.get("link")}
        seen_titles = [normalize(item.get("title", "")) for item in existing if item.get("title")]

        col_ref = self.db.collection("gov").document("announcements").collection("items")
        added = 0
        added_items = []
        for item in new_items:
            link = item.get("link", "")
            if link in seen_links:
                continue
            norm_title = normalize(item.get("title", ""))
            if norm_title and is_similar(norm_title, seen_titles):
                continue
            item["is_new"] = True
            doc_id = self._doc_id(link) if link else None
            if doc_id:
                col_ref.document(doc_id).set(item)
            else:
                col_ref.add(item)
            seen_links.add(link)
            if norm_title:
                seen_titles.append(norm_title)
            added_items.append(item)
            added += 1

        if added:
            print(f"[Storage/Firestore] Saved {added} new gov announcements")

        # 기존 항목은 is_new=False로 설정하여 기존과제와 신규과제를 구분
        for item in existing:
            item["is_new"] = False

        # 기존(existing) + 신규(added_items) 합산 후 날짜순 정렬
        merged = existing + added_items
        merged.sort(key=lambda x: x.get('date', '') or x.get('published_display', ''), reverse=True)
        return merged
