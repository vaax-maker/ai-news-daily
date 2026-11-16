"""Shared paths and service endpoints for the AI Daily applications."""

from __future__ import annotations

import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = PROJECT_ROOT / "docs"
DATA_ROOT = Path(os.environ.get("AIDAILY_DATA_ROOT", PROJECT_ROOT / "data")).expanduser()

PUBLISHING_REPOSITORY = Path(
    os.environ.get("AIDAILY_PUBLISHING_REPOSITORY", "~/Sites/ai-infographic")
).expanduser()
YOUTUBE_SUMMARIES_REPOSITORY = Path(
    os.environ.get("YOUTUBE_SUMMARIES_REPOSITORY", "~/nlm-infographic")
).expanduser()

SERVICE_REGISTRY = Path(os.environ.get(
    "ABOT_SERVICES_FILE",
    "~/Library/CloudStorage/GoogleDrive-woojanghoon@gmail.com/내 드라이브/_abot/services.json",
)).expanduser()


def service_endpoint(service: str, endpoint: str = "api_local", default: str = "") -> str:
    """Resolve an internal endpoint from the fleet registry."""
    try:
        registry = json.loads(SERVICE_REGISTRY.read_text(encoding="utf-8"))
        return str(registry["services"][service]["endpoints"][endpoint])
    except (OSError, ValueError, KeyError, TypeError):
        return default


INFOGRAPHIC_API_URL = os.environ.get("INFOGRAPHIC_API_URL") or service_endpoint(
    "aidaily-infographic-api", default="http://127.0.0.1:8791/generate"
)
SEARCH_SERVICE_URL = os.environ.get("SEARCH_SERVICE_URL") or service_endpoint(
    "aidaily-search", default="http://127.0.0.1:8096"
)
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_APP_TITLE = "AI-Daily"
OPENROUTER_APP_REFERER = "https://ai-daily.local"
TELEGRAM_API_URL = "https://api.telegram.org"
YOUTUBE_RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
FIRESTORE_API_URL = (
    "https://firestore.googleapis.com/v1/projects/{project}/"
    "databases/(default)/documents:runQuery"
)
PUBLISHING_READ_URL = "https://github.com/wootom/news.git"
PUBLIC_SITE_URL = "https://vaax-maker.github.io/ai-news-daily/"
TECH_DAILY_URL = os.environ.get(
    "AIDAILY_TECH_DAILY_URL",
    "https://wootom.github.io/news/%EA%B8%B0%EC%88%A0.html",
)

# These filenames are external storage/public contracts. Code-facing names stay canonical.
LEGACY_YOUTUBE_CONFIG = PUBLISHING_REPOSITORY / "daybreak-config.json"
LEGACY_YOUTUBE_QUEUE = "daybreak-telegram-queue.json"
# Read-only legacy migration sources; runtime history lives under data/youtube_summaries.
LEGACY_YOUTUBE_STATE = YOUTUBE_SUMMARIES_REPOSITORY / "deploy" / "morning-digest-log.mirror.json"
LEGACY_YOUTUBE_PROCESSED_LOG = Path(
    "~/Library/CloudStorage/GoogleDrive-woojanghoon@gmail.com/내 드라이브/"
    "obsidian_vault_2026/99-System/morning-digest-log.json"
).expanduser()
LEGACY_CUSTOMER_STORIES_PUBLIC_DIR = "uservoice"
LEGACY_CUSTOMER_STORIES_TAP = Path("~/.xbot/uservoice-rooms.jsonl").expanduser()
