#!/bin/bash
# 오늘, 세상이 — beacon 로컬 스케줄 러너 (맥미니, 평일 10:00).
# xbot LLM(docker exec) 필요 → 로컬 전용. 생성+렌더 후 docs/v2/beacon.html 커밋·푸시.
set -uo pipefail
REPO="$HOME/ai-news-daily"
PY="/opt/homebrew/bin/python3"          # bs4 포함 인터프리터
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
LOG="$REPO/data/beacon/run.log"
mkdir -p "$REPO/data/beacon"

{
  echo "==== $(date '+%F %T') beacon run ===="
  cd "$REPO" || exit 1

  # 1) hermes-xbot 컨테이너 up 보장
  if ! docker ps --filter name=hermes-xbot --format '{{.Names}}' | grep -q hermes-xbot; then
    echo "hermes-xbot down → Docker 기동 시도"
    open -a Docker || true
    for i in $(seq 1 40); do
      docker ps --filter name=hermes-xbot --format '{{.Names}}' | grep -q hermes-xbot && break
      sleep 5
    done
  fi

  # 2) 생성(xbot LLM) + 렌더
  if ! "$PY" scripts/build_beacon.py --all; then
    echo "build_beacon 실패 — 발행 중단"; exit 1
  fi

  # 3) 산출물만 커밋·푸시 (data/ 는 gitignore)
  git add docs/v2/beacon.html
  if git diff --cached --quiet; then
    echo "변경 없음 → 커밋 스킵"
  else
    git commit -m "beacon: 오늘의 경종 $(date +%F)"
    # ⚠ 공개(GitHub Pages)하려면 이 브랜치가 main 이어야 함. 아래는 현재 브랜치 push.
    git push origin HEAD 2>&1 || echo "push 실패 — git 인증(토큰/credential helper) 확인 필요"
  fi
  echo "==== done ===="
} >> "$LOG" 2>&1
