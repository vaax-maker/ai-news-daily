#!/bin/bash
# Compatibility entrypoint for rebuilding the local unified search index.
set -uo pipefail
REPO="${AIDAILY_REPOSITORY:-$HOME/aidaily}"
PY="${AIDAILY_PYTHON:-/opt/homebrew/bin/python3}"
cd "$REPO" || exit 1
exec "$PY" -m aidaily.publishing.search_index "$@"
