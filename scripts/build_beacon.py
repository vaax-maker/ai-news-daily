#!/usr/bin/env python3
"""오늘, 세상이 — beacon 빌드 오케스트레이터 (맥미니 로컬).

  python scripts/build_beacon.py --all           # 생성(xbot LLM) + 렌더
  python scripts/build_beacon.py --generate       # 생성만 (data/beacon/*.json)
  python scripts/build_beacon.py                  # 렌더만 (latest.json → docs/v2/beacon.html)

옵션:
  --docs-root PATH   후보 뉴스 소스 docs 루트 (기본: 이 저장소 docs/)
  --date YYYY.MM.DD  발행일 라벨 (기본: 오늘)

주의: --generate/--all 은 hermes-xbot 컨테이너(맥미니)가 필요.
렌더 단독은 의존성 없음(CI 가능하나 data/ 는 gitignore라 로컬 잡이 커밋 권장).
"""
import os
import sys
import json
import argparse
import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from src.v2 import beacon  # noqa: E402

DATA_DIR = os.path.join(ROOT, "data", "beacon")
OUT_HTML = os.path.join(ROOT, "docs", "v2", "beacon.html")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--generate", action="store_true", help="LLM 생성만")
    ap.add_argument("--all", action="store_true", help="생성 + 렌더")
    ap.add_argument("--docs-root", default=os.path.join(ROOT, "docs"))
    ap.add_argument("--date", default=datetime.date.today().strftime("%Y.%m.%d"))
    args = ap.parse_args()

    do_generate = args.generate or args.all
    do_render = args.all or not args.generate  # 기본 렌더; --generate 단독이면 렌더 안 함

    os.makedirs(DATA_DIR, exist_ok=True)
    latest = os.path.join(DATA_DIR, "latest.json")

    if do_generate:
        cands = beacon.load_candidates(args.docs_root)
        if len(cands) < 3:
            print(f"[error] 후보 부족: {len(cands)}건 (docs-root 확인)", file=sys.stderr)
            sys.exit(2)
        gen = beacon.generate_beacon(cands)
        payload = {"date": args.date, "cands": cands, "gen": gen}
        dated = os.path.join(DATA_DIR, f"{args.date.replace('.', '-')}.json")
        for path in (dated, latest):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"[generate] 대표='{gen['impact_headline']}' 모델={gen.get('_model')} "
              f"conf={gen.get('confidence')} → {os.path.relpath(dated, ROOT)}")

    if do_render:
        if not os.path.exists(latest):
            print("[error] data/beacon/latest.json 없음 — 먼저 --generate 하세요.", file=sys.stderr)
            sys.exit(2)
        with open(latest, encoding="utf-8") as f:
            p = json.load(f)
        html = beacon.render_html(p["cands"], p["gen"], p.get("date", args.date))
        os.makedirs(os.path.dirname(OUT_HTML), exist_ok=True)
        with open(OUT_HTML, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[render] {os.path.relpath(OUT_HTML, ROOT)} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
