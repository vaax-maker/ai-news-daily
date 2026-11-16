#!/bin/bash
# Prepared only; source config must be approved before launchd installation.
set -euo pipefail
TASK_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$TASK_ROOT"
TASK_PYTHON="${AIDAILY_PYTHON:-/opt/homebrew/bin/python3}"
exec "$TASK_PYTHON" -m aidaily.customer_stories.community_tap --since 24h
