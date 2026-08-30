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
  echo "--- [1/4] AI 뉴스 ---"
  /bin/bash "$HOME/ai-news-daily-beacon/deploy/run_daily.sh"
  echo "  (AI 뉴스 rc=$?)"
  echo "--- [2/4] AI 보이스 ---"
  /bin/bash "$HOME/ai-news-daily-beacon/deploy/run_uservoice.sh"
  echo "  (AI 보이스 rc=$?)"
  # 검색 인덱스 재생성 — 뉴스·보이스(09:00) + 개별 영상 리포트(digest 07:30)를 모두 반영.
  # 개별 리포트는 origin(wootom/news) 발행본 기준(로컬 드리프트·죽은링크 회피). 8096이 docs/ 직접 서빙 → 즉시 반영.
  echo "--- [3/4] 검색 인덱스 재생성 (origin 기준) ---"
  /bin/bash "$HOME/ai-news-daily-beacon/deploy/rebuild_search_index.sh"
  echo "  (검색 인덱스 rc=$?)"
  # 통합 페이지(오늘의 AI 소식) — 갱신된 스토어로 기술/경제/경제뉴스/검색 4페이지 렌더 + wootom/news
  # 발행(공식 사이트). 반드시 [3/4] 뒤(스토어 신선 후). hero.png는 [1/4] build.py가 그날 생성.
  echo "--- [4/4] 통합 페이지 렌더 + wootom 발행 ---"
  PUBLISH_UNIFIED_PUSH=1 /bin/bash "$HOME/nlm-infographic/deploy/publish_unified.sh"
  echo "  (통합 페이지 rc=$?)"
  echo "==================== $(date '+%F %T') 9시 통합 발행 종료 ===================="
} >> "$LOG" 2>&1
