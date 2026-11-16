"""Date/source/hash gate for daily hero publication; stale files are preserved."""
import hashlib
import json
import os
from pathlib import Path

ROLES = ("customer_story", "today_youtube", "ai_news")

def manifest_path(image):
    return Path(image).with_suffix(".manifest.json")

def validate_sources(stories, date):
    if not date or len(stories) != 3:
        raise ValueError("Hero requires all three daily sources")
    for story in stories:
        if not isinstance(story, dict) or not str(story.get("headline") or "").strip() or not str(story.get("body") or story.get("summary") or "").strip():
            raise ValueError("Hero source missing")
        dates = [story[k] for k in ("date", "report_date") if story.get(k)]
        if not dates or any(value != date for value in dates):
            raise ValueError("Hero source is not from the publication date")

def source_manifest(stories, date):
    validate_sources(stories, date)
    return [{"role": role, "date": date, "sha256": hashlib.sha256(
        json.dumps({k: v for k, v in story.items() if k not in ("n", "visual_brief")},
                   sort_keys=True, ensure_ascii=False).encode()).hexdigest()}
        for role, story in zip(ROLES, stories)]

def _write(image, value):
    path = manifest_path(image)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".new")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    os.replace(temporary, path)

def invalidate_hero(image, date, reason):
    _write(image, {"version": 1, "active": False, "date": date, "reason": reason})

def write_manifest(image, date, stories):
    _write(image, {"version": 1, "active": True, "date": date,
                   "image_sha256": hashlib.sha256(Path(image).read_bytes()).hexdigest(),
                   "sources": source_manifest(stories, date)})

def validate_hero(image, brief):
    from .visuals import _selected_stories
    try:
        metadata = json.loads(manifest_path(image).read_text())
        date = brief["date"]
        return (metadata.get("version") == 1 and metadata.get("active") is True
                and metadata.get("date") == date
                and metadata.get("image_sha256") == hashlib.sha256(Path(image).read_bytes()).hexdigest()
                and metadata.get("sources") == source_manifest(_selected_stories(brief), date))
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        return False

def validate_published_hero(image_path, date, *, manifest_path_override=None):
    """Validate stored publication evidence without loading project source data."""
    try:
        image = Path(image_path)
        metadata = json.loads(Path(manifest_path_override or manifest_path(image)).read_text())
        sources = metadata.get("sources")
        return (metadata.get("version") == 1 and metadata.get("active") is True
                and metadata.get("date") == date
                and metadata.get("image_sha256") == hashlib.sha256(image.read_bytes()).hexdigest()
                and isinstance(sources, list) and len(sources) == 3
                and [row.get("role") for row in sources] == list(ROLES)
                and all(row.get("date") == date and isinstance(row.get("sha256"), str)
                        and len(row["sha256"]) == 64
                        and all(c in "0123456789abcdef" for c in row["sha256"])
                        for row in sources))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False
