"""Publish staged YouTube Summaries without coupling publication to generation."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from aidaily import config
from aidaily.publishing.repository import commit_and_push


def _merge_queue(path: Path, messages: dict, date: str) -> tuple[dict, list[str]]:
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        current = {"date": date, "messages": {}, "sent": []}
    existing = dict(current.get("messages") or {})
    new_slugs = [slug for slug in messages if slug not in existing]
    existing.update(messages)
    current.update(date=date, messages=existing, sent=current.get("sent") or [])
    return current, new_slugs


def _update_processed_log(video_ids: list[str], *, publication_date=None, slugs=()):
    from aidaily.youtube_summaries.processed_state import record_published
    return record_published(video_ids, publication_date or datetime.now().date().isoformat(), slugs)


def publish(staging_dir: str, date: str, messages: dict, video_ids: list[str],
            dry_run: bool = False) -> dict:
    """Clone the public repository, merge reports/queue, push, then record IDs."""
    source_repository = config.PUBLISHING_REPOSITORY
    remote = subprocess.run(
        ["git", "-C", str(source_repository), "remote", "get-url", "origin"],
        check=True, capture_output=True, text=True, timeout=30,
    ).stdout.strip()
    temporary_root = Path(tempfile.mkdtemp(prefix="youtube-summaries-publish-"))
    deployment = temporary_root / "news"
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", remote, str(deployment)],
            check=True, capture_output=True, text=True, timeout=120,
        )
        for slug in messages:
            if Path(slug).name != slug or slug in (".", ".."):
                raise ValueError("Invalid report slug")
            report = Path(staging_dir) / f"{slug}.html"
            if not report.is_file():
                raise FileNotFoundError(f"Missing validated report: {slug}")
            shutil.copy2(report, deployment / report.name)
            # Revision/recovery publication can carry completed images in the
            # same transaction as reports. The earlier text-only stage remains
            # compatible when generation has not produced an image yet.
            image = Path(staging_dir) / 'assets' / 'ig' / (slug + '.jpg')
            if image.is_file():
                destination = deployment / 'assets' / 'ig' / image.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(image, destination)
        queue_path = deployment / config.LEGACY_YOUTUBE_QUEUE
        queue, new_slugs = _merge_queue(queue_path, messages, date)
        queue_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")

        # Commit prefix is retained because an external verification script consumes it.
        changed = commit_and_push(
            deployment,
            ["."],
            f"update: morning-digest {date} — {len(messages)} videos",
            dry_run=dry_run,
        )
        if not dry_run:
            _update_processed_log(video_ids, publication_date=date, slugs=list(messages))
        return {"changed": changed, "new_slugs": new_slugs, "dry_run": dry_run}
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)
