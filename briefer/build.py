#!/usr/bin/env python3
"""briefer.build — production orchestrator.

Fetches all daily-news docs (newest first), converts today's stories to 개조식
bullets via OpenRouter, generates (or reuses) the cover infographic, renders the
daily page + archive, and writes them under --docs-root.

Usage:
  python3 -m briefer.build --docs-root docs
  python3 -m briefer.build --docs-root docs --skip-infographic /path/to/existing.png
"""
import argparse
import json
import os
import shutil
import sys

from briefer import article, infographic, notify, outline, render, source


def main():
    ap = argparse.ArgumentParser(description="Build the daily AI briefing site.")
    ap.add_argument("--docs-root", default="docs", help="output directory (default: docs)")
    ap.add_argument("--skip-infographic", metavar="PATH", default=None,
                     help="reuse an existing infographic PNG instead of calling the slow nlm API")
    args = ap.parse_args()

    docs_root = args.docs_root
    os.makedirs(docs_root, exist_ok=True)
    os.makedirs(os.path.join(docs_root, "archive"), exist_ok=True)

    print("[build] fetching all daily-news docs from Firestore...", file=sys.stderr)
    items = source.fetch_all()
    if not items:
        raise SystemExit("[build] daily-news 없음 — fetch_all()이 빈 목록을 반환했습니다")

    # "오늘의 AI 소식" 통합: 해외·전문 소스(MIT·CB Insights·aibase·AI타임스)를 aiofmodu에 합류.
    # 평일 = aiofmodu 오늘분 + 신규 augment. 주말/aiofmodu 공백일 = 신규로 당일 골격 생성.
    # (com.aidaily.publish는 매일 08:30 실행이라 주말도 돈다 — 골격 분기로 주말 커버.)
    from briefer import extra_sources
    import datetime
    try:
        from zoneinfo import ZoneInfo
        _today = datetime.datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")
    except Exception:
        _today = datetime.date.today().strftime("%Y-%m-%d")

    if items[0].get("date") == _today:            # 평일: aiofmodu 오늘분 존재 → 신규 augment
        today = items[0]
        extra_sources.merge_into(today)           # 기본 소스당 2건 + 3층 중복제거
    else:                                          # 주말/공백: aiofmodu 오늘분 없음 → 신규로 골격
        _kd = f"{int(_today[5:7])}월 {int(_today[8:10])}일"
        today = {"date": _today, "newsTime": _kd, "title": "", "summary": "", "stories": []}
        extra_sources.merge_into(today, limit_per_source=4)   # 주말은 더 깊게
        if not today["stories"]:
            raise SystemExit("[build] 오늘 신규 뉴스 없음(주말/공백) — 발행 스킵")
        today["title"] = today["stories"][0]["headline"]
        today["summary"] = "해외·전문 소스 기반 오늘의 AI 뉴스(주말·보강)"
        items = [today] + items                     # 아카이브에 today 편입(기존 이력 보존)
    print(f"[build] {len(items)}건 로드, 오늘={today['date']} 「{today['title']}」 "
          f"(스토리 {len(today['stories'])})", file=sys.stderr)

    print("[build] outline_stories (OpenRouter)...", file=sys.stderr)
    stories = outline.outline_stories(today["stories"])

    infographic_path = os.path.join(docs_root, "infographic.png")
    if args.skip_infographic:
        if os.path.abspath(args.skip_infographic) != os.path.abspath(infographic_path):
            shutil.copyfile(args.skip_infographic, infographic_path)
        print(f"[build] infographic: reused {args.skip_infographic} -> {infographic_path}",
              file=sys.stderr)
    else:
        # 대표기사 top3 원문 fetch → terra 종합(실패 시 None → 뉴스 요약 폴백)
        print("[build] 대표기사 원문 fetch + 종합(article)...", file=sys.stderr)
        rich = article.synthesize_rich(today["stories"], top_n=3)
        infographic.generate(infographic_path, today, rich=rich)

    print("[build] rendering daily page...", file=sys.stderr)
    daily_html = render.render_daily(today, stories, "infographic.png")
    # Phase 3 컷오버(decouple): 데일리 페이지는 daily.html 로 분리 출력한다.
    # index.html 은 통합 페이지(wootom 기술.html)로 가는 영구 리다이렉트 자리로 비워 두어야
    # 하며, 매일 build 가 index.html 을 덮어써서 리다이렉트를 지우는 사고를 막는다.
    # 데이터(archive/index.json)는 아래에서 계속 기록되어 스토어(검색 인덱스)에 공급된다.
    daily_path = os.path.join(docs_root, "daily.html")
    with open(daily_path, "w", encoding="utf-8") as f:
        f.write(daily_html)

    print("[build] rendering archive page...", file=sys.stderr)
    archive_html = render.render_archive(items)
    archive_path = os.path.join(docs_root, "archive.html")
    with open(archive_path, "w", encoding="utf-8") as f:
        f.write(archive_html)

    archive_json_path = os.path.join(docs_root, "archive", "index.json")
    with open(archive_json_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)

    # Hero 표지(가로 16:6) — 그날 주요소식 '도식화'. 통합 '기술 데일리' 커버용. **맨 마지막에 생성**
    # (뉴스 확정 후). 통합 페이지 라이브 전까진 대기 에셋(현 페이지는 세로 infographic.png 사용,
    # 세로 원본은 클릭용으로 유지). 실패해도 뉴스 발행을 막지 않도록 예외를 삼킨다(아직 라이브 미사용).
    hero_path = os.path.join(docs_root, "hero.png")
    if not args.skip_infographic:
        try:
            infographic.generate_hero(hero_path, today)
        except Exception as e:
            print(f"[build] hero 생성 실패(무시, 뉴스 발행엔 영향 없음): {e}", file=sys.stderr)
    else:
        print("[build] hero: --skip-infographic → 스킵", file=sys.stderr)

    # ---- summary ----
    def sz(p):
        return f"{os.path.getsize(p) / 1024:.1f}KB" if os.path.exists(p) else "MISSING"

    n_bullets = sum(1 for s in stories if s.get("body_bullets"))
    print("", file=sys.stderr)
    print("=== build summary ===", file=sys.stderr)
    print(f"  {daily_path}          {sz(daily_path)}", file=sys.stderr)
    print(f"  {archive_path}        {sz(archive_path)}", file=sys.stderr)
    print(f"  {archive_json_path}   {sz(archive_json_path)}", file=sys.stderr)
    print(f"  {infographic_path}    {sz(infographic_path)}", file=sys.stderr)
    print(f"  오늘 제목: {today['title']}", file=sys.stderr)
    print(f"  스토리 수: {len(stories)}  (bullets 생성={n_bullets})", file=sys.stderr)
    print(f"  아카이브 총 뉴스 수: {len(items)}", file=sys.stderr)
    print(f"  아카이브 총 스토리 수: {sum(len(b['stories']) for b in items)}", file=sys.stderr)


if __name__ == "__main__":
    main()
