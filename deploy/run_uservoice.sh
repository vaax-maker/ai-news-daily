#!/bin/bash
# Compatibility entrypoint for Customer Stories generation only (no publish/notify).
set -uo pipefail
REPO="${AIDAILY_REPOSITORY:-$HOME/aidaily}"
PY="${AIDAILY_PYTHON:-/opt/homebrew/bin/python3}"
cd "$REPO" || exit 1
exec "$PY" -m aidaily.customer_stories.pipeline --docs-root docs --since 1d "$@"
