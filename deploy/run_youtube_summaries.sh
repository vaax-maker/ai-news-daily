#!/bin/bash
# YouTube Summaries production flow. Called by the legacy launchd-compatible wrapper.
set -uo pipefail

REPO="${AIDAILY_REPOSITORY:-$HOME/aidaily}"
EXTERNAL="${YOUTUBE_SUMMARIES_REPOSITORY:-$HOME/nlm-infographic}"
WEBROOT="${AIDAILY_PUBLISHING_REPOSITORY:-$HOME/Sites/ai-infographic}"
PY="${AIDAILY_PYTHON:-/opt/homebrew/bin/python3}"
TODAY="$(date +%F)"
LOG="$REPO/data/youtube_summaries/run.log"
# mini1 performs caption/audio collection and local MLX Whisper transcription.
# Pro receives text only through the shared LLM adapter; no remote ASR calls.
export PATH="$REPO/.venv-youtube/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
export YOUTUBE_MIN_TRANSCRIPT_CHARS="${YOUTUBE_MIN_TRANSCRIPT_CHARS:-1000}"
mkdir -p "$REPO/data/youtube_summaries"

{
  echo "==== $(date '+%F %T') YouTube Summaries ===="
  cd "$REPO" || exit 1
  # 자막이 확보된 유효 리포트가 30% 이상이면 발행한다. 통합 인포그래픽은 그중
  # 한 편만 필요하므로 종전 60% 게이트가 유효한 1~5편까지 모두 폐기하지 않게 한다.
  "$PY" -m aidaily.youtube_summaries.pipeline \
    --limit "${YOUTUBE_SUMMARIES_LIMIT:-15}" \
    --min-success-ratio "${YOUTUBE_SUMMARIES_MIN_SUCCESS_RATIO:-0.3}" \
    --publish || exit 1

  # The working mirror intentionally contains local-only historical artifacts, so a pull can
  # fail when a newly tracked remote file collides with an untracked local file. Clone the
  # published state separately and copy only today's reports/queue needed by post-processing.
  SYNC_ROOT="$(mktemp -d)" || exit 1
  trap 'rm -rf "$SYNC_ROOT"' EXIT
  AUTH_URL="$(git -C "$WEBROOT" remote get-url origin 2>/dev/null)"
  [ -n "$AUTH_URL" ] || { echo "[youtube_summaries] webroot origin missing"; exit 1; }
  git clone -q --depth 1 "$AUTH_URL" "$SYNC_ROOT/news" || exit 1
  copied=0
  for report in "$SYNC_ROOT/news/$TODAY"-*.html; do
    [ -f "$report" ] || continue
    grep -Eq 'YOUTUBE SUMMARIES|MORNING DIGEST' "$report" || continue
    cp "$report" "$WEBROOT/" || exit 1
    copied=$((copied + 1))
  done
  [ -f "$SYNC_ROOT/news/daybreak-telegram-queue.json" ] && \
    cp "$SYNC_ROOT/news/daybreak-telegram-queue.json" "$WEBROOT/"
  echo "[youtube_summaries] published mirror sync: $copied reports"
  # 사용자 정책: ChatGPT 웹(method 1) → OpenRouter GPT Image 2.5(method 2)만 사용한다.
  # Gemini·NotebookLM·Grok 폴백은 사용하지 않는다.
  image_failed=0
  PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}" \
    GEN_IG_METHOD="${GEN_IG_METHOD:-1}" NLM_METHOD_PRIORITY="${NLM_METHOD_PRIORITY:-1,2}" \
    "$PY" "$EXTERNAL/deploy/gen_infographics.py" "$TODAY" --webroot "$WEBROOT" || {
      image_failed=1
      echo "[youtube_summaries] infographic post-processing failed; reports remain published"
    }

  publish_failed=0
  for offset in 0 1 2; do
    summary_date="$(date -j -v-"${offset}"d -f "%Y-%m-%d" "$TODAY" +%Y-%m-%d 2>/dev/null || echo "$TODAY")"
    if ! "$PY" "$EXTERNAL/deploy/render_briefs_lean.py" "$summary_date" --push; then
      echo "[youtube_summaries] daily page failed for $summary_date"
      publish_failed=1
    fi
  done
  if [ "$publish_failed" -ne 0 ]; then
    echo "==== incomplete: publication failed; generated assets retained ===="
    exit 1
  fi
  if [ "$image_failed" -ne 0 ]; then
    echo "==== incomplete: infographic generation failed; published reports retained ===="
    exit 1
  fi
  echo "==== complete ===="
} >> "$LOG" 2>&1
