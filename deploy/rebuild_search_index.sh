#!/bin/bash
# 검색 인덱스 재생성 — 개별 영상 리포트는 origin(wootom/news)의 발행본을 진실원천으로 삼는다.
# 로컬 webroot(~/Sites/ai-infographic)는 dirty·미발행 파일이 섞여 죽은 링크를 낳으므로 쓰지 않는다.
# 뉴스/보이스는 build_search_index가 beacon docs에서 읽는다. 8096(http.server)이 docs/를 직접 서빙 → 즉시 반영.
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
DOCS="$HOME/ai-news-daily-beacon/docs"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
if git clone -q --depth 1 https://github.com/wootom/news.git "$TMP/news"; then
  /opt/homebrew/bin/python3 "$DOCS/build_search_index.py" --webroot "$TMP/news" --out "$DOCS/search-index.json"
else
  echo "clone 실패 — 검색 인덱스 재생성 스킵(기존 유지)"; exit 1
fi
