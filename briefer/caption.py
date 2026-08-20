#!/usr/bin/env python3
"""공통 텔레그램 캡션 — 3개 발행물(AI 뉴스·AI 보이스·AI 브리프) 룩앤필 통일.

2026-08-18 신설(재구성: 텔레그램 요약본문 룩앤필 통일). 어느 파이프라인이든 이 build()로
같은 골격을 강제한다. nlm-infographic/deploy/caption.py 와 **동일 사본**(교차 리포).

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

_WK = ["월", "화", "수", "목", "금", "토", "일"]


def fmt_date(date: str) -> str:
    try:
        d = datetime.date.fromisoformat(date)
        return f"{d.month}월{d.day}일({_WK[d.weekday()]})"
    except Exception:
        return date or ""


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
