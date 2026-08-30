#!/bin/bash
# VAAX AI 뉴스 — 일일 발행 러너 (평일 09:00 KST).
# main 추적 체크아웃에서 fetch→outline→render 후 docs/ 를 main 에 커밋·푸시
# (→ GitHub Pages 공개), 이어서 텔레그램으로 인포그래픽+캡션 발송.
set -uo pipefail
REPO="$HOME/ai-news-daily-beacon"             # main 추적 체크아웃(git worktree)
PY="/opt/homebrew/bin/python3"
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
LOG="$REPO/data/brief/run.log"
mkdir -p "$REPO/data/brief"

{
  echo "==== $(date '+%F %T') daily brief run ===="
  cd "$REPO" || exit 1

  # 1) 최신 main 반영 — 충돌 방지
  if ! git pull --rebase --autostash origin main 2>&1; then
    echo "git pull --rebase 실패 — 발행 중단"; exit 1
  fi

  # 2) OPENROUTER_API_KEY 확보 (hermes-xbot 컨테이너 env)
  if ! docker ps --filter name=hermes-xbot --format '{{.Names}}' | grep -q hermes-xbot; then
    echo "hermes-xbot down → Docker 기동 시도"
    open -a Docker || true
    for i in $(seq 1 40); do
      docker ps --filter name=hermes-xbot --format '{{.Names}}' | grep -q hermes-xbot && break
      sleep 5
    done
  fi
  export OPENROUTER_API_KEY="$(docker exec hermes-xbot printenv OPENROUTER_API_KEY 2>/dev/null)"
  if [ -z "$OPENROUTER_API_KEY" ]; then
    echo "경고: OPENROUTER_API_KEY 획득 실패 — outline은 문장분할 폴백으로 진행"
  fi

  # 3) 빌드 (fetch_all → outline → infographic → render)
  if ! "$PY" -m briefer.build --docs-root docs; then
    echo "briefer.build 실패 — 발행 중단"; exit 1
  fi

  # 4) 산출물 커밋·푸시
  git add docs
  if git diff --cached --quiet; then
    echo "변경 없음 → 커밋 스킵"
  else
    git commit -m "brief: $(date +%F)"
    if ! git push origin HEAD:main 2>&1; then
      echo "push 실패 — git 인증 확인 필요"; exit 1
    fi
  fi

  # 5) 텔레그램 발송 (자격증명: env 우선, 없으면 nlm-infographic의 기본 creds 파일)
  CREDS="/Users/woojanghoon/nlm-infographic/deploy/.tg-creds.json"
  if [ -z "${TELEGRAM_BOT_TOKEN:-}" ] || [ -z "${TELEGRAM_CHAT_ID:-}" ]; then
    if [ -f "$CREDS" ]; then
      export TELEGRAM_BOT_TOKEN="$("$PY" -c "import json;print(json.load(open('$CREDS'))['default']['bot_token'])" 2>/dev/null)"
      export TELEGRAM_CHAT_ID="$("$PY" -c "import json;print(json.load(open('$CREDS'))['default']['chat_id'])" 2>/dev/null)"
    fi
  fi
  if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
    "$PY" -c "
import json
from briefer import notify
brief = json.load(open('docs/archive/index.json'))[0]
notify.send_photo('docs/infographic.png', notify.build_caption(brief),
                   '$TELEGRAM_BOT_TOKEN', '$TELEGRAM_CHAT_ID')
" || echo "텔레그램 발송 실패(계속)"
  else
    echo "경고: TELEGRAM 자격증명 없음 — 발송 스킵"
  fi

  echo "==== done ===="
} >> "$LOG" 2>&1
