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
    today = items[0]
    print(f"[build] {len(items)}건 로드, 오늘={today['date']} 「{today['title']}」", file=sys.stderr)

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
    index_path = os.path.join(docs_root, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(daily_html)

    print("[build] rendering archive page...", file=sys.stderr)
    archive_html = render.render_archive(items)
    archive_path = os.path.join(docs_root, "archive.html")
    with open(archive_path, "w", encoding="utf-8") as f:
        f.write(archive_html)

    archive_json_path = os.path.join(docs_root, "archive", "index.json")
    with open(archive_json_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)

    # ---- summary ----
    def sz(p):
        return f"{os.path.getsize(p) / 1024:.1f}KB" if os.path.exists(p) else "MISSING"

    n_bullets = sum(1 for s in stories if s.get("body_bullets"))
    print("", file=sys.stderr)
    print("=== build summary ===", file=sys.stderr)
    print(f"  {index_path}          {sz(index_path)}", file=sys.stderr)
    print(f"  {archive_path}        {sz(archive_path)}", file=sys.stderr)
    print(f"  {archive_json_path}   {sz(archive_json_path)}", file=sys.stderr)
    print(f"  {infographic_path}    {sz(infographic_path)}", file=sys.stderr)
    print(f"  오늘 제목: {today['title']}", file=sys.stderr)
    print(f"  스토리 수: {len(stories)}  (bullets 생성={n_bullets})", file=sys.stderr)
    print(f"  아카이브 총 뉴스 수: {len(items)}", file=sys.stderr)
    print(f"  아카이브 총 스토리 수: {sum(len(b['stories']) for b in items)}", file=sys.stderr)


if __name__ == "__main__":
    main()
