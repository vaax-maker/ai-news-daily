#!/usr/bin/env python3
"""Shared caption formatter for AI News, Customer Stories, and YouTube Summaries.

골격:
    [<섹션>] M월D일(요일)[ · <suffix>]

    "<headline>"                (headline 있을 때만)

    ■ <불릿1>

    ■ <불릿2>

    ■ <불릿3>

    ▸ <url>
    ※ <note>                    (note 있을 때만)
"""
import datetime
import re

_WK = ["월", "화", "수", "목", "금", "토", "일"]


def fmt_date(date: str) -> str:
    try:
        d = datetime.date.fromisoformat(date)
        return f"{d.month}월{d.day}일({_WK[d.weekday()]})"
    except Exception:
        return date or ""


def daily_header(date: str, *, republished: bool = False) -> str:
    """Canonical header accepted by the existing Telegram→Kakao relay."""
    datetime.date.fromisoformat(date)  # Never fall back to an ISO/invalid header.
    header = f"오늘의 AI소식 · {fmt_date(date)}"
    return header + ('\n재발행 안내' if republished else '')


def validate_daily_header(caption: str) -> None:
    """Check only the transport header; do not inspect article content."""
    head = (caption or '').lstrip().split('\n', 1)[0]
    if head.startswith('오늘의 AI소식') and not re.fullmatch(
            r'오늘의 AI소식\s*·\s*\d{1,2}월\d{1,2}일\([월화수목금토일]\)', head):
        raise ValueError('Daily announcement must use captions.daily_header()')


def build(section: str, date: str, bullets, url: str,
          headline: str = "", suffix: str = "", note: str = "") -> str:
    """통일 캡션 텍스트. bullets=문자열 리스트(■ 자동 부착, 빈 값 제외)."""
    head = f"[{section}] {fmt_date(date)}" + (f" · {suffix}" if suffix else "")
    parts = [head, ""]
    if headline:
        parts += [f'"{headline.strip()}"', ""]
    parts.append("\n\n".join(f"■ {b}" for b in bullets if b))
    parts += ["", f"▸ {url}"]
    if note:
        parts.append(f"※ {note}")
    return "\n".join(parts)
