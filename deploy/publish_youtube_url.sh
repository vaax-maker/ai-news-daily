#!/bin/bash
# AI Daily single-URL publication entrypoint used by the authenticated xbot admin.
set -uo pipefail

URL="${1:-}"
JOB="${2:-$(date +%s)}"
[ -n "$URL" ] || { echo "YouTube URL required"; exit 2; }

REPO="${AIDAILY_REPOSITORY:-$HOME/aidaily}"
EXTERNAL="${YOUTUBE_SUMMARIES_REPOSITORY:-$HOME/nlm-infographic}"
WEBROOT="${AIDAILY_PUBLISHING_REPOSITORY:-$HOME/Sites/ai-infographic}"
PY="${AIDAILY_PYTHON:-/opt/homebrew/bin/python3}"
TODAY="$(date +%F)"
JOB_DIR="$REPO/data/youtube_summaries/jobs"
LOG="$REPO/data/youtube_summaries/publish-url.log"
STATUS="$JOB_DIR/$JOB.status"
mkdir -p "$JOB_DIR"

log() { echo "[$(date '+%F %T')] [$JOB] $*" | tee -a "$LOG"; }
set_status() { echo "$1" > "$STATUS"; }
fail() { set_status error; log "FAILED: $*"; exit 1; }

STAGING="$(mktemp -d /tmp/aidaily-youtube-url.XXXXXX)" || exit 1
SYNC_ROOT="$(mktemp -d /tmp/aidaily-youtube-sync.XXXXXX)" || exit 1
trap 'rm -rf "$STAGING" "$SYNC_ROOT"' EXIT

set_status running
log "═════ 단일 발행 시작 URL=$URL ═════"
cd "$REPO" || fail "repository missing"
"$PY" -m aidaily.youtube_summaries.pipeline --url "$URL" --staging-dir "$STAGING" --publish \
  >>"$LOG" 2>&1 || fail "analysis or staged publication failed"

QUEUE="$STAGING/daybreak-telegram-queue.json"
SLUGS="$("$PY" -c 'import json,sys; print(" ".join(json.load(open(sys.argv[1],encoding="utf-8")).get("messages",{})))' "$QUEUE" 2>>"$LOG")"
if [ -z "$SLUGS" ]; then
  set_status done
  log "DONE: no new item (already published or filtered)"
  exit 0
fi

AUTH_URL="$(git -C "$WEBROOT" remote get-url origin 2>>"$LOG")" || fail "publishing origin missing"
git clone -q --depth 1 "$AUTH_URL" "$SYNC_ROOT/news" >>"$LOG" 2>&1 || fail "published state sync failed"
for slug in $SLUGS; do
  cp "$SYNC_ROOT/news/$slug.html" "$WEBROOT/" || fail "report mirror failed: $slug"
done
[ -f "$SYNC_ROOT/news/daybreak-telegram-queue.json" ] && \
  cp "$SYNC_ROOT/news/daybreak-telegram-queue.json" "$WEBROOT/"

GEN_IG_METHOD=1 NLM_METHOD_PRIORITY=1,2 \
  "$PY" "$EXTERNAL/deploy/gen_infographics.py" "$TODAY" --webroot "$WEBROOT" \
  >>"$LOG" 2>&1 || fail "image generation failed"
for slug in $SLUGS; do
  [ -s "$WEBROOT/assets/ig/$slug.jpg" ] || fail "quality gate: image missing for $slug"
done

"$PY" "$EXTERNAL/deploy/render_briefs_lean.py" "$TODAY" --push >>"$LOG" 2>&1 || \
  fail "daily YouTube page publication failed"

"$PY" -m aidaily.publishing.youtube_listing_check --webroot "$WEBROOT" --date "$TODAY" $SLUGS >>"$LOG" 2>&1 || \
  fail "publication verification: report missing from daily list"

# Read-only polling accommodates static-host deployment propagation; never resubmit publication.
verified=0
for check in 1 2 3 4 5 6; do
  if "$PY" -m aidaily.publishing.youtube_listing_check --webroot "$WEBROOT" --date "$TODAY" --public-base "${AIDAILY_PUBLIC_BASE_URL:-https://wootom.github.io/news/}" $SLUGS >>"$LOG" 2>&1; then
    verified=1
    break
  fi
  sleep 10
done
[ "$verified" -eq 1 ] || fail "public publication verification incomplete"

i=0
total="$(printf '%s\n' $SLUGS | wc -l | tr -d ' ')"
for slug in $SLUGS; do
  i=$((i + 1))
  log "[$i/$total] OK $slug method=aidaily"
done
set_status done
log "DONE: web publication complete"
