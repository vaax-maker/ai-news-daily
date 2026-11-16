"""Operator-managed content source and visual policies.

The JSON file is the single source of truth shared by collection pipelines and the
xbot admin compatibility boundary.  Secrets never belong in this document; API
credentials remain environment variables handled by the integration adapters.
"""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from aidaily import config


SETTINGS_PATH = Path(os.environ.get(
    "AIDAILY_CONTENT_SETTINGS",
    config.DATA_ROOT / "content-settings.json",
)).expanduser()

CONTENT_TYPES = ("ai_news", "customer_stories", "youtube_summaries", "economy_news")
CONNECTORS = ("firestore", "rss", "html", "reddit", "hacker_news", "youtube")
LIMIT_MODES = ("default", "fixed", "all_today")


DEFAULT_SETTINGS = {
    "version": 1,
    "collection": {
        "ai_news": {"enabled": True, "since_days": 3, "default_per_source": 2},
        "customer_stories": {"enabled": True, "since_hours": 24},
        "youtube_summaries": {"enabled": True, "hours": 48, "min_duration": 240},
        "economy_news": {"enabled": True, "since_days": 1, "default_per_source": 2},
    },
    "sources": [
        {"id": "aiofmodu", "name": "aiofmodu", "content_type": "ai_news",
         "connector": "firestore", "url": "https://aiofmodu.com/daily-news",
         "enabled": True, "limit_mode": "all_today", "limit": 0,
         "infographic_candidate": True, "priority": 1, "include_keywords": [],
         "exclude_keywords": []},
        {"id": "mit-tech-review", "name": "MIT Tech Review", "content_type": "ai_news",
         "connector": "rss", "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed/",
         "enabled": True, "limit_mode": "fixed", "limit": 2,
         "infographic_candidate": False, "priority": 20, "include_keywords": [],
         "exclude_keywords": []},
        {"id": "cb-insights", "name": "CB Insights", "content_type": "ai_news",
         "connector": "rss", "url": "https://www.cbinsights.com/research/feed/",
         "enabled": True, "limit_mode": "fixed", "limit": 2,
         "infographic_candidate": False, "priority": 30, "include_keywords": [],
         "exclude_keywords": []},
        {"id": "aibase", "name": "aibase", "content_type": "ai_news",
         "connector": "html", "url": "https://www.aibase.com/news",
         "enabled": True, "limit_mode": "fixed", "limit": 2,
         "infographic_candidate": False, "priority": 40, "include_keywords": [],
         "exclude_keywords": []},
        {"id": "ai-times", "name": "AI타임스", "content_type": "ai_news",
         "connector": "rss", "url": "https://www.aitimes.com/rss/allArticle.xml",
         "enabled": True, "limit_mode": "fixed", "limit": 2,
         "infographic_candidate": False, "priority": 50, "include_keywords": [],
         "exclude_keywords": []},
        {"id": "reddit", "name": "Reddit", "content_type": "customer_stories",
         "connector": "reddit", "url": "https://www.reddit.com/",
         "enabled": True, "limit_mode": "default", "limit": 0,
         "infographic_candidate": False, "priority": 10, "include_keywords": [],
         "exclude_keywords": []},
        {"id": "hacker-news", "name": "Hacker News", "content_type": "customer_stories",
         "connector": "hacker_news", "url": "https://news.ycombinator.com/",
         "enabled": True, "limit_mode": "default", "limit": 0,
         "infographic_candidate": False, "priority": 20, "include_keywords": [],
         "exclude_keywords": []},
        {"id": "geeknews", "name": "긱뉴스", "content_type": "customer_stories",
         "connector": "rss", "url": "https://news.hada.io/rss/news",
         "enabled": True, "limit_mode": "default", "limit": 0,
         "infographic_candidate": False, "priority": 30, "include_keywords": [],
         "exclude_keywords": []},
    ],
    "infographics": {
        "ai_news": {
            "enabled": True, "article_count": 3, "source_ids": ["aiofmodu"],
            "story_mix": ["customer_story", "today_youtube", "ai_news"],
            "orientation": "landscape", "background": "white",
            "layout": "lead_50_support_25_25",
            "equal_panels": False, "number_order": True,
            "read_original_articles": True, "max_article_chars": 6000,
        },
        "market_summary": {
            "enabled": True, "renderer": "template", "format": "png",
            "orientation": "landscape", "background": "white",
        },
    },
    "market_summary": {
        "enabled": True, "publish_time": "07:30", "timezone": "Asia/Seoul",
        "holiday_policy": "previous_trading_day",
        "indicators": ["KOSPI", "KOSDAQ", "S&P 500", "NASDAQ", "USD/KRW",
                       "US 10Y", "GOLD", "BITCOIN"],
    },
}


def _deep_merge(default, value):
    if not isinstance(default, dict) or not isinstance(value, dict):
        return copy.deepcopy(value)
    result = copy.deepcopy(default)
    for key, item in value.items():
        result[key] = _deep_merge(result[key], item) if key in result else copy.deepcopy(item)
    return result


def load(path: str | Path | None = None) -> dict:
    target = Path(path or SETTINGS_PATH).expanduser()
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        value = {}
    settings = _deep_merge(DEFAULT_SETTINGS, value if isinstance(value, dict) else {})
    settings["sources"] = [normalize_source(source) for source in settings.get("sources", [])
                           if isinstance(source, dict)]
    return settings


def save(settings: dict, path: str | Path | None = None) -> Path:
    target = Path(path or SETTINGS_PATH).expanduser()
    normalized = _deep_merge(DEFAULT_SETTINGS, settings if isinstance(settings, dict) else {})
    normalized["sources"] = [normalize_source(source) for source in normalized.get("sources", [])]
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(normalized, output, ensure_ascii=False, indent=2)
            output.write("\n")
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").casefold()).strip("-")
    return slug or "source"


def normalize_source(source: dict) -> dict:
    name = str(source.get("name") or "").strip()
    url = str(source.get("url") or "").strip()
    content_type = str(source.get("content_type") or "ai_news")
    connector = str(source.get("connector") or "rss")
    limit_mode = str(source.get("limit_mode") or "default")
    if content_type not in CONTENT_TYPES:
        raise ValueError(f"unsupported content_type: {content_type}")
    if connector not in CONNECTORS:
        raise ValueError(f"unsupported connector: {connector}")
    if limit_mode not in LIMIT_MODES:
        raise ValueError(f"unsupported limit_mode: {limit_mode}")
    if not name:
        raise ValueError("source name is required")
    if url and urlparse(url).scheme not in ("http", "https"):
        raise ValueError("source URL must be http(s)")
    generated_id = slugify(name)
    if generated_id == "source" and url:
        generated_id = slugify((urlparse(url).hostname or "").removeprefix("www."))
    return {
        "id": str(source.get("id") or generated_id),
        "name": name,
        "content_type": content_type,
        "connector": connector,
        "url": url,
        "enabled": bool(source.get("enabled", True)),
        "limit_mode": limit_mode,
        "limit": max(0, int(source.get("limit") or 0)),
        "infographic_candidate": bool(source.get("infographic_candidate", False)),
        "priority": max(1, int(source.get("priority") or 100)),
        "include_keywords": _keywords(source.get("include_keywords")),
        "exclude_keywords": _keywords(source.get("exclude_keywords")),
    }


def _keywords(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def sources(content_type: str | None = None, enabled_only: bool = False,
            settings: dict | None = None) -> list[dict]:
    rows = (settings or load()).get("sources", [])
    if content_type:
        rows = [row for row in rows if row.get("content_type") == content_type]
    if enabled_only:
        rows = [row for row in rows if row.get("enabled", True)]
    return sorted(rows, key=lambda row: (int(row.get("priority") or 100), row.get("name", "")))


def source_by_id(source_id: str, settings: dict | None = None) -> dict | None:
    return next((row for row in (settings or load()).get("sources", [])
                 if row.get("id") == source_id), None)


def upsert_source(source: dict, path: str | Path | None = None) -> dict:
    settings = load(path)
    row = normalize_source(source)
    existing = {item["id"]: item for item in settings["sources"]}
    existing[row["id"]] = row
    settings["sources"] = list(existing.values())
    save(settings, path)
    return row


def archive_source(source_id: str, path: str | Path | None = None) -> bool:
    settings = load(path)
    row = source_by_id(source_id, settings)
    if not row:
        return False
    row["enabled"] = False
    save(settings, path)
    return True
