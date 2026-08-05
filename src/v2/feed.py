"""Data extraction for VAAX v2.

Reads from the already-rendered files produced by the existing pipeline:
  - docs/ai/daily/*.html, docs/xr/daily/*.html  → news feed items
  - data/gov/announcements.json                 → government calls
  - data/latest_key_message.json                → editor's note
  - docs/quickview/...                          → quickview reports

Pure read-only. Nothing here writes to the existing tree.
"""

from __future__ import annotations

import glob
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

KST = timezone(timedelta(hours=9))


@dataclass
class FeedItem:
    title: str
    url: str
    domain: str
    published: Optional[datetime]
    summary: str = ""
    category: str = ""  # "ai" | "xr" | "quickview"
    points: int = 0
    comments: int = 0

    @property
    def relative_time(self) -> str:
        if not self.published:
            return ""
        now = datetime.now(KST)
        # Coerce naive datetimes to KST so subtraction works
        pub = self.published if self.published.tzinfo else self.published.replace(tzinfo=KST)
        diff = now - pub
        secs = int(diff.total_seconds())
        if secs < 60:
            return "방금"
        if secs < 3600:
            return f"{secs // 60}m"
        if secs < 86400:
            return f"{secs // 3600}h"
        days = secs // 86400
        return f"{days}d"


@dataclass
class GovItem:
    title: str
    agency: str
    region: str
    url: str
    deadline: Optional[datetime] = None
    raw: dict = field(default_factory=dict)

    @property
    def days_remaining(self) -> Optional[int]:
        if not self.deadline:
            return None
        today = datetime.now(KST).date()
        d = self.deadline.date() if isinstance(self.deadline, datetime) else self.deadline
        return (d - today).days

    @property
    def dday_label(self) -> str:
        d = self.days_remaining
        if d is None:
            return "—"
        if d < 0:
            return "마감"
        if d == 0:
            return "D-DAY"
        return f"D-{d}"

    @property
    def warn(self) -> bool:
        d = self.days_remaining
        return d is not None and 0 <= d <= 7

    @property
    def deadline_short(self) -> str:
        if not self.deadline:
            return ""
        return self.deadline.strftime("%m.%d")


@dataclass
class QuickviewItem:
    title: str
    url: str
    date: datetime
    tag: str = "심층 리포트"
    read: str = ""
    views: str = ""
    comments: int = 0

    @property
    def date_md(self) -> str:
        return self.date.strftime("%m/%d")

    @property
    def date_y(self) -> str:
        return self.date.strftime("%Y")

    @property
    def date_short(self) -> str:
        return self.date.strftime("%m.%d")

    @property
    def recent(self) -> bool:
        return (datetime.now(KST).date() - self.date.date()).days <= 14


# --------------------- News extraction ---------------------

def _domain_of(url: str) -> str:
    try:
        net = urlparse(url).netloc.lower()
        return net[4:] if net.startswith("www.") else net
    except Exception:
        return ""


def _parse_pub(text: str) -> Optional[datetime]:
    text = (text or "").strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y.%m.%d %H:%M", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=KST)
        except ValueError:
            continue
    return None


def _latest_daily(pattern: str) -> Optional[str]:
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None


def extract_news(category: str, docs_root: str) -> list[FeedItem]:
    """Parse the latest daily HTML for AI or XR into FeedItem list."""
    path = _latest_daily(os.path.join(docs_root, category, "daily", "*.html"))
    if not path or not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")
    items: list[FeedItem] = []
    for art in soup.select("article.news-item"):
        a = art.select_one("h2.news-title a")
        if not a:
            continue
        url = a.get("href", "").strip()
        title = a.get_text(strip=True)
        # Strip trailing NEW badge text if it bled into title
        title = re.sub(r"\s*NEW\s*$", "", title)
        meta = art.select_one(".news-meta")
        domain = ""
        pub_text = ""
        if meta:
            src_a = meta.select_one(".source-link")
            if src_a:
                domain = src_a.get_text(strip=True)
            pd = meta.select_one(".published-date")
            if pd:
                pub_text = pd.get_text(strip=True)
        if not domain:
            domain = _domain_of(url)
        # Try to capture a short summary from body
        body = art.select_one(".news-summary, .news-body")
        summary = body.get_text(" ", strip=True)[:200] if body else ""
        items.append(FeedItem(
            title=title,
            url=url,
            domain=domain,
            published=_parse_pub(pub_text),
            summary=summary,
            category=category,
        ))
    return items


def merged_today_feed(docs_root: str, limit: int = 12) -> list[FeedItem]:
    """Combine AI + XR + a few QV references, sorted by recency, truncated."""
    items = extract_news("ai", docs_root) + extract_news("xr", docs_root)
    items.sort(key=lambda x: x.published or datetime.min.replace(tzinfo=KST), reverse=True)
    return items[:limit]


# --------------------- Gov extraction ---------------------

def _parse_gov_deadline(s: str) -> Optional[datetime]:
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y%m%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:len(fmt) + 8], fmt).replace(tzinfo=KST)
        except ValueError:
            continue
    return None


def extract_gov(data_root: str) -> list[GovItem]:
    path = os.path.join(data_root, "gov", "announcements.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    rows = raw if isinstance(raw, list) else list(raw.values()) if isinstance(raw, dict) else []
    out: list[GovItem] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        deadline = None
        # Real-data field names (bid_close_dt, openg_dt) come first; common
        # public-data-API names are fallbacks.
        for key in (
            "bid_close_dt", "openg_dt",
            "deadline", "endDate", "reqstEndDe", "pblancEndDe", "end_date", "마감일",
        ):
            if r.get(key):
                deadline = _parse_gov_deadline(str(r[key]))
                if deadline:
                    break
        title = (
            r.get("title")
            or r.get("name")
            or r.get("pblancNm")
            or r.get("공고명")
            or "정부과제"
        )
        agency = (
            r.get("dept")
            or r.get("agency")
            or r.get("source_name")
            or r.get("organization")
            or r.get("excInsttNm")
            or r.get("기관")
            or ""
        )
        # Region is often embedded in title as [서울], [대구], etc. Try to lift it.
        region = r.get("region") or r.get("area") or r.get("지역") or ""
        if not region:
            m = re.match(r"\s*\[([^\]]+)\]", title)
            if m:
                region = m.group(1)
        if not region:
            region = "전국"
        url = (
            r.get("link")
            or r.get("url")
            or r.get("pblancUrl")
            or "https://www.bizinfo.go.kr/"
        )
        out.append(GovItem(
            title=title,
            agency=agency,
            region=region,
            url=url,
            deadline=deadline,
            raw=r,
        ))
    # Sort: open soonest first, then no-deadline at the bottom.
    out.sort(key=lambda x: (x.days_remaining is None, x.days_remaining if x.days_remaining is not None else 9999))
    return out


# --------------------- Quickview extraction ---------------------

def extract_quickview(docs_root: str) -> list[QuickviewItem]:
    """Look at docs/quickview/*.html and produce a feed.

    The existing pipeline writes quickview pages with various naming conventions.
    We grab files matching YYYY-MM-DD in their filename, falling back to mtime.
    """
    qv_dir = os.path.join(docs_root, "quickview")
    if not os.path.isdir(qv_dir):
        return []
    out: list[QuickviewItem] = []
    seen_urls: set[str] = set()
    for path in sorted(glob.glob(os.path.join(qv_dir, "*.html")), reverse=True):
        name = os.path.basename(path)
        if name in ("index.html", "archive.html"):
            continue
        m = re.search(r"(\d{4})[-_.](\d{2})[-_.](\d{2})", name)
        if m:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=KST)
        else:
            dt = datetime.fromtimestamp(os.path.getmtime(path), tz=KST)
        # Get title from the page <title> or <h1>
        title = name.rsplit(".", 1)[0]
        try:
            with open(path, encoding="utf-8") as f:
                soup = BeautifulSoup(f.read(2000), "html.parser")
            h = soup.find(["h1", "title"])
            if h:
                title = h.get_text(strip=True) or title
        except Exception:
            pass
        url = f"./quickview/{name}"
        if url in seen_urls:
            continue
        seen_urls.add(url)
        out.append(QuickviewItem(title=title, url=url, date=dt))
    out.sort(key=lambda x: x.date, reverse=True)
    return out


def load_editor_note(data_root: str) -> str:
    path = os.path.join(data_root, "latest_key_message.json")
    if not os.path.exists(path):
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d.get("key_message", "") or ""
    except Exception:
        return ""
