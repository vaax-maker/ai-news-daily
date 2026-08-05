#!/usr/bin/env python3
"""월간 총집 빌드 (맥미니 로컬, xbot LLM 필요).

  python scripts/build_monthly.py --month 2026-08

옵션: --docs-root(기본 저장소 docs), --month(기본 이번 달).
산출: docs/v2/monthly/{month}.html
"""
import os
import sys
import argparse
import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from src.v2 import monthly  # noqa: E402

OUT_DIR = os.path.join(ROOT, "docs", "v2", "monthly")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default=datetime.date.today().strftime("%Y-%m"))
    ap.add_argument("--docs-root", default=os.path.join(ROOT, "docs"))
    args = ap.parse_args()

    items = monthly.gather_month(args.month, args.docs_root)
    if len(items) < 3:
        print(f"[error] {args.month} 헤드라인 부족: {len(items)}건", file=sys.stderr)
        sys.exit(2)
    data = monthly.generate_monthly(items, args.month)
    html = monthly.render_monthly(data, args.month, len(items))
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, f"{args.month}.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[monthly] {args.month} headline='{data.get('headline')}' "
          f"shifts={len(data.get('shifts', []))} model={data.get('_model')} "
          f"→ {os.path.relpath(out, ROOT)}")


if __name__ == "__main__":
    main()
