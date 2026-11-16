"""Detect a newly created or subsequently edited aiofmodu weekday edition.

The morning pipeline may run before aiofmodu creates its daily Firestore document.
This module compares the current source stories with the locally published archive
while ignoring generated bullet metadata.  A refresh is therefore requested only
when source facts changed, not every time the scheduler polls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from aidaily.ai_news import source


def _projection(stories: list[dict]) -> list[dict]:
    fields = ("headline", "body", "takeaway", "url")
    rows = [{field: str(story.get(field) or "").strip() for field in fields}
            for story in stories]
    return sorted(rows, key=lambda row: (row["url"], row["headline"]))


def _source_stories(items: list[dict], publication_date: str) -> list[dict]:
    stories = []
    seen = set()
    for edition in items:
        if str(edition.get("date") or "") != publication_date:
            continue
        for story in edition.get("stories") or []:
            key = (str(story.get("url") or "").strip(),
                   str(story.get("headline") or "").strip())
            if key in seen:
                continue
            seen.add(key)
            stories.append(story)
    return stories


def _published_stories(path: str | Path, publication_date: str) -> list[dict]:
    try:
        editions = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    for edition in editions if isinstance(editions, list) else []:
        if str(edition.get("date") or "") != publication_date:
            continue
        return [story for story in edition.get("stories") or []
                if str(story.get("source") or "").casefold() == source.AIOFMODU_SOURCE]
    return []


def _fingerprint(stories: list[dict]) -> str:
    raw = json.dumps(_projection(stories), ensure_ascii=False,
                     sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def evaluate(publication_date: str, archive_path: str | Path,
             source_items: list[dict] | None = None) -> dict:
    current = _source_stories(source_items if source_items is not None else source.fetch_all(),
                              publication_date)
    published = _published_stories(archive_path, publication_date)
    if not current:
        state = "waiting"
    elif _projection(current) == _projection(published):
        state = "current"
    else:
        state = "refresh"
    return {
        "state": state,
        "date": publication_date,
        "source_count": len(current),
        "published_count": len(published),
        "source_fingerprint": _fingerprint(current),
        "published_fingerprint": _fingerprint(published),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    parser.add_argument("--archive", default="docs/archive/index.json")
    args = parser.parse_args()
    print(json.dumps(evaluate(args.date, args.archive), ensure_ascii=False))


if __name__ == "__main__":
    main()
