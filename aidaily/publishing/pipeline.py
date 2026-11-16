"""Publish generated content and rebuild the unified public site."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import tempfile
from pathlib import Path

from aidaily import config
from aidaily.publishing import search_index
from aidaily.publishing.repository import publish_generated


def ensure_release_allowed() -> None:
    """An explicit external-approval hold also applies to unattended entrypoints."""
    editorial = config.DATA_ROOT / 'customer_stories' / (datetime.date.today().isoformat() + '.json')
    if editorial.exists() and (json.loads(editorial.read_text()).get('gen')or{}).get('schema_version')==2:
        authorization_path=config.DATA_ROOT/'customer_stories/newsroom/release-authorization.json'
        authorization=json.loads(authorization_path.read_text())if authorization_path.exists()else{}
        digest=__import__('hashlib').sha256(editorial.read_bytes()).hexdigest()
        routine=authorization.get('policy')=='regular_publication_approved'
        edition=authorization.get('policy')=='edition_approved'and authorization.get('edition_sha256')==digest
        if not(routine or edition):raise RuntimeError('Newsroom public release requires explicit payload/destination authorization; internal generation remains available')
    path = config.DATA_ROOT / 'publishing/publication-hold.json'
    if not path.exists():
        return
    hold = json.loads(path.read_text())
    if hold.get('date') == datetime.date.today().isoformat() and hold.get('status') == 'approval_required':
        raise RuntimeError('Public publication is on an explicit approval hold; generated outputs are preserved')


def rebuild_search_index() -> None:
    with tempfile.TemporaryDirectory(prefix="aidaily-search-source-") as temporary:
        source = Path(temporary) / "news"
        subprocess.run(
            ["git", "clone", "-q", "--depth", "1",
             config.PUBLISHING_READ_URL, str(source)],
            check=True, timeout=120,
        )
        search_index.build(
            docs_root=str(config.DOCS_ROOT),
            webroot=str(source),
            output=str(config.DOCS_ROOT / "search-index.json"),
        )


def public_outputs(date: str | None = None) -> list[str]:
    """Only public generated documents; never publish internal docs wholesale."""
    date = date or datetime.date.today().isoformat()
    candidates = ["docs/daily.html", "docs/archive.html", "docs/archive/index.json",
                  "docs/search-index.json", "docs/v2/uservoice.html",
                  "docs/v2/uservoice/index.html", "docs/v2/uservoice/manifest.json",
                  "docs/v2/uservoice/community.html", f"docs/v2/uservoice/{date}.html"]
    edition = config.DATA_ROOT / 'customer_stories' / (date + '.json')
    if edition.exists() and (json.loads(edition.read_text()).get('gen') or {}).get('schema_version') == 2:
        # Newsroom articles live entirely on the main page; preserve existing
        # legacy files remotely without publishing a new detail-page edition.
        candidates = [path for path in candidates if not path.startswith('docs/v2/uservoice')]
    return [path for path in candidates if (config.PROJECT_ROOT / path).is_file()]


def publish_aidaily() -> bool:
    ensure_release_allowed()
    return publish_generated(
        config.PROJECT_ROOT,
        public_outputs(),
        f"publish: AI Daily {datetime.date.today().isoformat()}",
    )


def publish_unified_site() -> None:
    ensure_release_allowed()
    script = config.YOUTUBE_SUMMARIES_REPOSITORY / "deploy" / "publish_unified.sh"
    subprocess.run(
        ["/bin/bash", str(script)],
        check=True,
        env={**os.environ, "PUBLISH_UNIFIED_PUSH": "1"},
        timeout=600,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-unified", action="store_true")
    args = parser.parse_args()
    ensure_release_allowed()
    rebuild_search_index()
    # Daily topics are prepared before rendering and the following notification.
    # A local editorial failure must not discard otherwise publishable articles.
    from aidaily.publishing import editorial
    try:
        editorial.prepare()
    except Exception as error:
        print('[publishing] editorial unavailable; existing renderer fallback:', type(error).__name__)
    publish_aidaily()
    if not args.skip_unified:
        publish_unified_site()
        from aidaily.publishing.customer_verification import verify_customer_publication
        verify_customer_publication(datetime.date.today().isoformat())


if __name__ == "__main__":
    main()
