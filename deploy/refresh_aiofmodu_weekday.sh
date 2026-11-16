#!/bin/bash
# Weekday late-source watcher: update the web when aiofmodu appears or changes.
set -uo pipefail

REPO="${AIDAILY_REPOSITORY:-$HOME/aidaily}"
PY="${AIDAILY_PYTHON:-/opt/homebrew/bin/python3}"
INTERVAL_SEC="${AIOFMODU_REFRESH_INTERVAL_SEC:-600}"
END_TIME="${AIOFMODU_REFRESH_END_TIME:-10:30}"
LOG="$REPO/data/publishing/aiofmodu-refresh.log"
LOCK="$REPO/data/publishing/aiofmodu-refresh.lock"
TODAY="$(date +%F)"
WEEKDAY="$(date +%u)"
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
mkdir -p "$REPO/data/publishing"

log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }

# aiofmodu has no regular weekend edition. Weekend polling would only waste calls.
if [ "$WEEKDAY" -gt 5 ]; then
  log "weekend: polling skipped"
  exit 0
fi

# launchd catch-up or a manual retry must not create two simultaneous publishers.
if ! mkdir "$LOCK" 2>/dev/null; then
  log "another watcher is already running; skipped"
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT

DEADLINE="$($PY -c 'import datetime,sys; d=datetime.datetime.strptime(sys.argv[1]+" "+sys.argv[2], "%Y-%m-%d %H:%M"); print(int(d.timestamp()))' "$TODAY" "$END_TIME")" || exit 1
cd "$REPO" || exit 1
log "weekday watcher started (interval=${INTERVAL_SEC}s, end=$END_TIME)"

while true; do
  probe="$($PY -m aidaily.ai_news.late_refresh --date "$TODAY" --archive docs/archive/index.json 2>>"$LOG")"
  probe_status=$?
  if [ "$probe_status" -ne 0 ]; then
    log "source probe failed; will retry"
  else
    state="$($PY -c 'import json,sys; print(json.loads(sys.argv[1])["state"])' "$probe" 2>>"$LOG")"
    counts="$($PY -c 'import json,sys; x=json.loads(sys.argv[1]); print("source=%s, published=%s" % (x["source_count"], x["published_count"]))' "$probe" 2>>"$LOG")"
    if [ "$state" = "refresh" ]; then
      log "change detected ($counts); regenerating AI News"
      if "$PY" -m aidaily.publishing.source_refresh >>"$LOG" 2>&1; then
        log "web refresh complete ($counts); notifications intentionally skipped"
      else
        log "web refresh failed; will retry"
      fi
    else
      log "$state ($counts)"
    fi
  fi

  now="$(date +%s)"
  if [ "$now" -ge "$DEADLINE" ]; then
    log "watch window closed"
    exit 0
  fi
  remaining=$((DEADLINE - now))
  delay="$INTERVAL_SEC"
  [ "$remaining" -lt "$delay" ] && delay="$remaining"
  sleep "$delay"
done
