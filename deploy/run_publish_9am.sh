#!/bin/bash
# AI 데일리 — 9시 통합 발행 오케스트레이터 (매일 09:00 KST).
# 뉴스 → 보이스 를 **순차** 실행한다. 둘 다 같은 리포(vaax-maker/ai-news-daily)의 main 에
# push 하는데 러너들은 push 재시도가 없어(각자 exit 1), 동시 실행 시 non-ff 레이스로 하나가
# 실패한다. 순차로 돌리면 두 번째가 첫 번째의 커밋을 pull 한 뒤 push 하므로 레이스가 없다.
# 각 러너는 자족형(자체 cd·PATH·로그). 유튜브(AI 브리프)는 다른 리포라 별도 스케줄 유지.
# 발행 감사(통지)는 별도 잡 com.aidaily.publish-audit(10:00)가 3개 모두 정본 기준으로 확인.
set -uo pipefail
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
LOG="$HOME/ai-news-daily-beacon/data/publish-9am.log"
mkdir -p "$(dirname "$LOG")"
{
  echo "==================== $(date '+%F %T') 9시 통합 발행 시작 ===================="
  echo "--- [1/2] AI 뉴스 ---"
  /bin/bash "$HOME/ai-news-daily-v3/deploy/run_daily.sh"
  echo "  (AI 뉴스 rc=$?)"
  echo "--- [2/2] AI 보이스 ---"
  /bin/bash "$HOME/ai-news-daily-beacon/deploy/run_uservoice.sh"
  echo "  (AI 보이스 rc=$?)"
  echo "==================== $(date '+%F %T') 9시 통합 발행 종료 ===================="
} >> "$LOG" 2>&1
