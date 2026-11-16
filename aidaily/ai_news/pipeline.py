#!/usr/bin/env python3
"""AI News generation pipeline.

Fetches all daily-news docs (newest first), converts today's stories to 개조식
bullets via OpenRouter, generates (or reuses) one horizontal hero image, renders
the daily page + archive, and writes them under --docs-root.

Usage:
  python3 -m aidaily.ai_news.pipeline --docs-root docs
  python3 -m aidaily.ai_news.pipeline --docs-root docs --reuse-hero /path/to/existing.png
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from aidaily.ai_news import extra_sources, renderer, source, summarizer, visuals
from aidaily.integrations import content_settings


def _story_key(story: dict) -> tuple[str, str]:
    return (str(story.get("url") or "").strip(),
            str(story.get("headline") or "").strip())


def _restore_published_archive(items: list[dict], archive_path: str) -> list[dict]:
    """Keep previously published extras and bullet metadata on source refresh.

    Firestore is the aiofmodu SSOT, but it does not contain the external-media
    augmentation or generated bullet fields.  Re-fetching Firestore must not
    erase those already-published additions from today or historical dates.
    """
    path = Path(archive_path)
    try:
        published = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return items
    if not isinstance(published, list):
        return items

    by_date: dict[str, dict] = {}
    for item in items:
        date = str(item.get("date") or "")
        if date:
            by_date.setdefault(date, item)

    for old_day in published:
        date = str(old_day.get("date") or "")
        if not date:
            continue
        target = by_date.get(date)
        if target is None:
            # Preserve an external-only historical edition that Firestore does
            # not know about, such as a weekend augmentation.
            clone = dict(old_day)
            clone["stories"] = [dict(s) for s in (old_day.get("stories") or [])]
            items.append(clone)
            by_date[date] = clone
            continue

        target_stories = target.setdefault("stories", [])
        current = {_story_key(story): story for story in target_stories}
        for old_story in old_day.get("stories") or []:
            key = _story_key(old_story)
            matched = current.get(key)
            if matched is not None:
                for field in ("body_bullets", "why_bullets"):
                    if old_story.get(field) and not matched.get(field):
                        matched[field] = list(old_story[field])
                continue
            if str(old_story.get("source") or "").casefold() == source.AIOFMODU_SOURCE:
                continue
            clone = dict(old_story)
            target_stories.append(clone)
            current[key] = clone
    items.sort(key=lambda item: str(item.get("date") or ""), reverse=True)
    return items


def _ensure_bullets_without_api(stories: list[dict], refresh_sources=None) -> list[dict]:
    """Fill or selectively refresh web bullets without an LLM call."""
    refresh = {str(name).casefold() for name in (refresh_sources or set())}
    for story in stories:
        force = str(story.get("source") or "").casefold() in refresh
        if story.get("body_bullets") and not force:
            continue
        fallback = summarizer._fallback([story])[0]
        story["body_bullets"] = fallback["body"]
        story["why_bullets"] = fallback["why"]
    return stories


def _combine_editions_for_date(items: list[dict], publication_date: str) -> tuple[dict | None, list[dict]]:
    """Combine every aiofmodu edition for a publication date without losing stories."""
    editions = [item for item in items if item.get("date") == publication_date]
    if not editions:
        return None, items

    today = {**editions[0], "stories": []}
    seen: set[tuple[str, str]] = set()
    for edition in editions:
        for story in edition.get("stories") or []:
            key = (str(story.get("url") or "").strip(),
                   str(story.get("headline") or "").strip())
            if key in seen:
                continue
            seen.add(key)
            today["stories"].append(dict(story))
    for number, story in enumerate(today["stories"], start=1):
        story["n"] = f"{number:02d}"

    archive = [today] + [item for item in items if item.get("date") != publication_date]
    return today, archive


def main():
    ap = argparse.ArgumentParser(description="Build the daily AI briefing site.")
    ap.add_argument("--docs-root", default="docs", help="output directory (default: docs)")
    ap.add_argument("--reuse-hero", metavar="PATH", default=None,
                     help="reuse an existing horizontal hero PNG instead of generating one")
    ap.add_argument("--web-only", action="store_true",
                    help="refresh local HTML/JSON only; no LLM or image generation")
    args = ap.parse_args()

    docs_root = args.docs_root
    os.makedirs(docs_root, exist_ok=True)
    os.makedirs(os.path.join(docs_root, "archive"), exist_ok=True)

    print("[build] fetching all daily-news docs from Firestore...", file=sys.stderr)
    items = source.fetch_all()
    if not items:
        raise SystemExit("[build] daily-news 없음 — fetch_all()이 빈 목록을 반환했습니다")

    # Firestore 재조회만으로 과거 외부매체·생성 bullet이 사라지지 않도록 기존 공개
    # 아카이브의 부가 데이터를 먼저 복원한다.
    archive_json_path = os.path.join(docs_root, "archive", "index.json")
    items = _restore_published_archive(items, archive_json_path)

    # "오늘의 AI 소식" 통합: 해외·전문 소스(MIT·CB Insights·aibase·AI타임스)를 aiofmodu에 합류.
    # 평일 = aiofmodu 오늘분 + 신규 augment. 주말/aiofmodu 공백일 = 신규로 당일 골격 생성.
    # (com.aidaily.publish는 06:00 사전 생성·07:30 게시이라 주말도 돈다 — 골격 분기로 주말 커버.)
    import datetime
    try:
        from zoneinfo import ZoneInfo
        _today = datetime.datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")
    except Exception:
        _today = datetime.date.today().strftime("%Y-%m-%d")

    today, items = _combine_editions_for_date(items, _today)
    source_policy = content_settings.source_by_id("aiofmodu") or {}
    if today is not None and not source_policy.get("enabled", True):
        items = [item for item in items if item is not today]
        today = None
    elif today is not None and source_policy.get("limit_mode") == "fixed":
        today["stories"] = today.get("stories", [])[:max(0, int(source_policy.get("limit") or 0))]
    if today is not None:                          # aiofmodu 발행일 뉴스 전체 + 외부 매체 보강
        if not args.web_only:
            extra_sources.merge_into(today)        # 소스별 설정 기사 수 + 3층 중복제거
    else:                                          # 주말/공백: aiofmodu 오늘분 없음 → 신규로 골격
        _kd = f"{int(_today[5:7])}월 {int(_today[8:10])}일"
        today = {"date": _today, "newsTime": _kd, "title": "", "summary": "", "stories": []}
        if not args.web_only:
            extra_sources.merge_into(today)         # 공백일에도 소스별 설정 기사 수 적용
        if not today["stories"]:
            raise SystemExit("[build] 오늘 신규 뉴스 없음(주말/공백) — 발행 스킵")
        today["title"] = today["stories"][0]["headline"]
        today["summary"] = "해외·전문 소스 기반 오늘의 AI 뉴스(주말·보강)"
        items = [today] + items                     # 아카이브에 today 편입(기존 이력 보존)
    print(f"[build] {len(items)}건 로드, 오늘={today['date']} 「{today['title']}」 "
          f"(스토리 {len(today['stories'])})", file=sys.stderr)

    visual_policy = content_settings.load().get("infographics", {}).get("ai_news", {})
    if args.web_only:
        print("[ai_news] web-only: LLM 없이 기존/문장분할 bullet 사용", file=sys.stderr)
        stories = _ensure_bullets_without_api(
            today["stories"], refresh_sources={source.AIOFMODU_SOURCE}
        )
    else:
        print("[ai_news] summarize_stories (OpenRouter)...", file=sys.stderr)
        stories = summarizer.summarize_stories(today["stories"])

    # 웹 커버와 Telegram 알림은 같은 가로형 hero.png를 사용한다. 예전 세로형
    # infographic.png는 중복 산출물이므로 더 이상 생성하지 않는다.
    hero_path = os.path.join(docs_root, "hero.png")
    hero_src = None
    from aidaily.ai_news.hero_validation import validate_hero, invalidate_hero, manifest_path
    if visual_policy.get("presentation", "matrix") == "matrix":
        # The unified hero is now rendered from daily article data. Do not
        # generate an unused synthetic cover; per-video images are independent.
        invalidate_hero(hero_path, today["date"], "matrix_presentation")
        print("[build] hero: 주제·출처 표 사용, 이미지 생성 안 함", file=sys.stderr)
    elif not visual_policy.get("enabled", True):
        invalidate_hero(hero_path, today["date"], "disabled")
    elif args.web_only or args.reuse_hero:
        candidate = args.reuse_hero or hero_path
        if validate_hero(candidate, today):
            if os.path.abspath(candidate) != os.path.abspath(hero_path):
                shutil.copyfile(candidate, hero_path)
                shutil.copyfile(manifest_path(candidate), manifest_path(hero_path))
            hero_src = "hero.png"
        else:
            invalidate_hero(hero_path, today["date"], "reuse_validation_failed")
            print("[build] hero: 당일 소스·날짜·해시 검증 미달, 사용 안 함", file=sys.stderr)
    else:
        try:
            visuals.generate_hero(hero_path, today)
            if validate_hero(hero_path, today):
                hero_src = "hero.png"
            else:
                invalidate_hero(hero_path, today["date"], "generation_validation_failed")
        except Exception as e:
            invalidate_hero(hero_path, today["date"], "generation_failed")
            print(f"[build] hero 생성 실패(이미지 비활성·원본 보존): {type(e).__name__}", file=sys.stderr)

    print("[build] rendering daily page...", file=sys.stderr)
    daily_html = renderer.render_daily(today, stories, hero_src)
    # Phase 3 컷오버(decouple): 데일리 페이지는 daily.html 로 분리 출력한다.
    # index.html 은 통합 페이지(wootom 기술.html)로 가는 영구 리다이렉트 자리로 비워 두어야
    # 하며, 매일 build 가 index.html 을 덮어써서 리다이렉트를 지우는 사고를 막는다.
    # 데이터(archive/index.json)는 아래에서 계속 기록되어 스토어(검색 인덱스)에 공급된다.
    daily_path = os.path.join(docs_root, "daily.html")
    with open(daily_path, "w", encoding="utf-8") as f:
        f.write(daily_html)

    print("[build] rendering archive page...", file=sys.stderr)
    archive_html = renderer.render_archive(items)
    archive_path = os.path.join(docs_root, "archive.html")
    with open(archive_path, "w", encoding="utf-8") as f:
        f.write(archive_html)

    with open(archive_json_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)

    # ---- summary ----
    def sz(p):
        return f"{os.path.getsize(p) / 1024:.1f}KB" if os.path.exists(p) else "MISSING"

    n_bullets = sum(1 for s in stories if s.get("body_bullets"))
    print("", file=sys.stderr)
    print("=== build summary ===", file=sys.stderr)
    print(f"  {daily_path}          {sz(daily_path)}", file=sys.stderr)
    print(f"  {archive_path}        {sz(archive_path)}", file=sys.stderr)
    print(f"  {archive_json_path}   {sz(archive_json_path)}", file=sys.stderr)
    print(f"  {hero_path}           {sz(hero_path)}", file=sys.stderr)
    print(f"  오늘 제목: {today['title']}", file=sys.stderr)
    print(f"  스토리 수: {len(stories)}  (bullets 생성={n_bullets})", file=sys.stderr)
    print(f"  아카이브 총 뉴스 수: {len(items)}", file=sys.stderr)
    print(f"  아카이브 총 스토리 수: {sum(len(b['stories']) for b in items)}", file=sys.stderr)


if __name__ == "__main__":
    main()
