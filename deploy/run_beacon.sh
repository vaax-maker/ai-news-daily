#!/bin/bash
# 오늘, 세상이 — beacon 로컬 스케줄 러너 (맥미니, 평일 10:00).
# xbot LLM(docker exec) 필요 → 로컬 전용. main 추적 체크아웃에서 생성+렌더 후
# docs/v2/beacon.html 을 main 에 커밋·푸시(→ GitHub Pages 공개).
set -uo pipefail
REPO="$HOME/ai-news-daily-beacon"        # main 추적 데몬 전용 체크아웃(git worktree)
PY="/opt/homebrew/bin/python3"           # bs4 포함 인터프리터
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

  # 2) 최신 main 반영(daily CI가 docs 갱신) — 충돌 방지
  git fetch origin main 2>&1
  git pull --rebase --autostash origin main 2>&1 || echo "pull-rebase 경고(계속)"

  # 3) 생성(xbot LLM) + 렌더
  if ! "$PY" scripts/build_beacon.py --all; then
    echo "build_beacon 실패 — 발행 중단"; exit 1
  fi

  # 4) 산출물만 커밋·푸시 (data/ 는 gitignore). worktree HEAD=main.
  git add docs/v2/beacon.html
  if git diff --cached --quiet; then
    echo "변경 없음 → 커밋 스킵"
  else
    git commit -m "beacon: 오늘의 경종 $(date +%F)"
    git push origin HEAD:main 2>&1 || echo "push 실패 — git 인증 확인 필요"
  fi
  echo "==== done ===="
} >> "$LOG" 2>&1
