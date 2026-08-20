#!/bin/bash
# 사용자 피드백 — 로컬 스케줄 러너 (맥미니, 매일 09:30).
# 소스: Reddit(.rss)·Hacker News(Algolia)·긱뉴스(RSS)·오픈채팅 GPTers(에어 SSH) — 최근 24시간.
# 날짜 간 중복 제거(seen.json). OpenRouter(공통 briefer.llm) 요약 → docs/v2/uservoice.html 커밋·푸시.
set -uo pipefail
REPO="$HOME/ai-news-daily-beacon"        # v3 main 추적 git worktree
PY="/opt/homebrew/bin/python3"
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
LOG="$REPO/data/uservoice/run.log"
mkdir -p "$REPO/data/uservoice"

{
  echo "==== $(date '+%F %T') uservoice(피드백) run ===="
  cd "$REPO" || exit 1

  # 1) LLM = OpenRouter(공통 briefer.llm) — Docker/xbot 의존 없음(2026-08-18 전환).
  #    키는 env OPENROUTER_API_KEY 또는 ~/xbot/.env 에서 로드.

  # 2) 최신 main 반영(uservoice는 docs/v2/uservoice.html 만 건드려 daily 잡과 무충돌)
  git fetch origin main 2>&1
  git pull --rebase --autostash origin main 2>&1 || echo "pull-rebase 경고(계속)"

  # 3) 소스 수집(24h·중복제거) + 생성(OpenRouter) + 렌더
  if ! "$PY" -m briefer.uservoice --docs-root docs --since 1d; then
    echo "uservoice 실패/신규 소스 부족 — 발행 스킵"; exit 0
  fi

  # 4) 산출물 커밋·푸시 (data/ 는 gitignore). 날짜별 아카이브 포함.
  COMMITTED=0
  git add docs/v2/uservoice.html docs/v2/uservoice_message.txt docs/v2/uservoice/
  if git diff --cached --quiet; then
    echo "변경 없음 → 커밋 스킵(발송도 스킵)"
  else
    git commit -m "uservoice: 사용자 피드백 $(date +%F)"
    git push origin HEAD:main 2>&1 && COMMITTED=1 || echo "push 실패 — git 인증 확인 필요"
  fi

  # 5) vaax-notifier 발송(텔레그램, AI뉴스와 동일 채널) — 새 내용일 때만.
  if [ "$COMMITTED" = "1" ]; then
    CREDS="/Users/woojanghoon/nlm-infographic/deploy/.tg-creds.json"
    if [ -z "${TELEGRAM_BOT_TOKEN:-}" ] || [ -z "${TELEGRAM_CHAT_ID:-}" ]; then
      if [ -f "$CREDS" ]; then
        export TELEGRAM_BOT_TOKEN="$("$PY" -c "import json;print(json.load(open('$CREDS'))['default']['bot_token'])" 2>/dev/null)"
        export TELEGRAM_CHAT_ID="$("$PY" -c "import json;print(json.load(open('$CREDS'))['default']['chat_id'])" 2>/dev/null)"
      fi
    fi
    if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
      "$PY" -c "
import os
from briefer import notify
cap = open('docs/v2/uservoice_message.txt', encoding='utf-8').read()
# PNG 없음 → notify.send_photo 가 sendMessage(텍스트)로 자동 폴백
notify.send_photo('docs/v2/__nopng__.png', cap,
                  os.environ['TELEGRAM_BOT_TOKEN'], os.environ['TELEGRAM_CHAT_ID'])
" && echo "발송 OK" || echo "발송 실패"
    else
      echo "경고: TELEGRAM 자격증명 없음 — 발송 스킵"
    fi
  fi
  echo "==== done ===="
} >> "$LOG" 2>&1
