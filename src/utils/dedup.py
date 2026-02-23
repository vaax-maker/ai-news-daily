"""
src/utils/dedup.py — Article deduplication utilities.
"""

import re
from difflib import SequenceMatcher


def normalize_title(title: str) -> str:
    """Normalize title for similarity comparison."""
    if not title:
        return ""
    cleaned = re.sub(r"[^0-9A-Za-z가-힣\s]", "", title)
    return cleaned.lower().strip()


def is_similar_title(new_title: str, existing_titles: list, threshold: float = 0.80) -> bool:
    """Check if new_title is similar to any existing title."""
    norm_new = normalize_title(new_title)
    if not norm_new:
        return False
    for existing in existing_titles:
        norm_existing = normalize_title(existing)
        if norm_existing:
            ratio = SequenceMatcher(None, norm_new, norm_existing).ratio()
            if ratio >= threshold:
                return True
    return False
