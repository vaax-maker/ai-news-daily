"""YouTube RSS, metadata, and transcript adapters."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

from aidaily import config
from aidaily.integrations.http import request_bytes
from aidaily.integrations.youtube_transcript import transcribe, YTDLP, _yt_hardening

RSS_URL = config.YOUTUBE_RSS_URL
_NS = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}


def fetch_channel(channel_id: str, timeout: int = 15) -> list[dict]:
    raw, _ = request_bytes(
        RSS_URL.format(channel_id=channel_id),
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=timeout,
    )
    root = ET.fromstring(raw)
    videos = []
    for entry in root.findall("atom:entry", _NS):
        video_id = entry.find("yt:videoId", _NS)
        title = entry.find("atom:title", _NS)
        published = entry.find("atom:published", _NS)
        if video_id is None or title is None or published is None:
            continue
        videos.append({
            "video_id": video_id.text.strip(),
            "title": (title.text or "").strip(),
            "published": datetime.fromisoformat(published.text.strip()),
        })
    return videos


def duration_seconds(video_id: str, timeout: int = 45) -> float | None:
    result = subprocess.run(
        [YTDLP, *_yt_hardening(), "--no-update", "--print", "duration",
         f"https://youtu.be/{video_id}"],
        capture_output=True, text=True, timeout=timeout,
    )
    lines = (result.stdout or "").strip().splitlines()
    value = lines[-1].strip() if lines else ""
    try:
        return float(value) if value and value not in ("NA", "None") else None
    except ValueError:
        return None


def video_metadata(url: str, timeout: int = 60) -> dict:
    """Resolve public title/channel/upload metadata for a single URL."""
    result = subprocess.run(
        [YTDLP, *_yt_hardening(), "--no-update", "--skip-download", "--dump-single-json", url],
        capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "YouTube metadata lookup failed")[:300])
    data = json.loads(result.stdout)
    upload_date = str(data.get("upload_date") or "")
    date = (f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
            if len(upload_date) == 8 else "")
    return {
        "video_id": str(data.get("id") or ""),
        "title": str(data.get("title") or ""),
        "channel": str(data.get("channel") or data.get("uploader") or ""),
        "channel_id": str(data.get("channel_id") or ""),
        "upload_date": date,
        "duration": data.get("duration"),
        "url": str(data.get("webpage_url") or url),
    }


def fetch_transcript(url: str, timeout: int = 180, *, normalize: bool = False, title: str = "", channel: str = "") -> str:
    """Transcribe on the executing mini1 with local Whisper; no Pro ASR API.

    Only the resulting text proceeds to the shared local-first LLM adapter.
    """
    del timeout  # adapter owns download/backend timeouts
    context = {}
    if title:
        context["title"] = title
    if channel:
        context["channel"] = channel
    data = transcribe(url, lang="ko", **context)
    if isinstance(data, dict):
        if data.get("error"):
            stages = ", ".join(f"{x['stage']}={x['status']}" for x in data.get("stages", []))
            raise RuntimeError(f"자막·음성 전사 확보 실패 ({stages})")
        text = str(data.get("text") or data.get("transcript") or "")
    else:
        text = str(data or "")
    # The default preserves raw checkpoints; callers may request a display copy.
    if normalize:
        from aidaily.integrations.terminology import normalize_text, load_glossary, with_title_reference
        text, _ = normalize_text(text, context=f"{title}\n{channel}\n{text}",
                                 glossary=with_title_reference(load_glossary(), title))
    return text


def fetch_channel_video_page(channel_id: str, timeout: int = 120) -> list[dict]:
    """Bounded public /videos lookup for a failed XR-channel RSS feed.

    Full metadata supplies upload dates; flat playlists omit them. At most five
    uploads are read, with the same existing yt-dlp transport and no downloads.
    """
    result = subprocess.run(
        [YTDLP, *_yt_hardening(), "--no-update", "--skip-download",
         "--playlist-end", "5", "--dump-single-json",
         f"https://www.youtube.com/channel/{channel_id}/videos"],
        capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError("XR channel video-page lookup failed")
    payload = json.loads(result.stdout)
    videos = []
    for entry in payload.get("entries", [])[:5]:
        stamp = entry.get("release_timestamp") or entry.get("timestamp")
        date = str(entry.get("upload_date") or "")
        if stamp:
            published = datetime.fromtimestamp(float(stamp), timezone.utc)
        elif len(date) == 8 and date.isdigit():
            published = datetime.strptime(date, "%Y%m%d").replace(tzinfo=timezone.utc)
        else:
            continue
        if not entry.get("id") or not entry.get("title"):
            continue
        videos.append({"video_id":entry["id"], "title":entry["title"],
                       "published":published, "duration":entry.get("duration"),
                       "collection_source":"youtube_video_page"})
    return videos
