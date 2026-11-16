#!/bin/bash
# Daily production flow: generate -> publish -> notify.
set -uo pipefail

REPO="${AIDAILY_REPOSITORY:-$HOME/aidaily}"
PY="${AIDAILY_PYTHON:-/opt/homebrew/bin/python3}"
LOG="$REPO/data/publishing/run.log"
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
mkdir -p "$REPO/data/publishing"

{
  echo "==== $(date '+%F %T') AI Daily pipeline ===="
  cd "$REPO" || exit 1

  # Runtime code and generated files stay local. Publication uses a fresh clone.
  "$PY" -m aidaily.publishing.daily "$@" || exit $?
  echo "==== complete ===="
} >> "$LOG" 2>&1
