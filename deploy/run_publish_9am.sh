#!/bin/bash
# Compatibility entrypoint for the installed com.aidaily.publish launchd job.
exec /bin/bash "${AIDAILY_REPOSITORY:-$HOME/aidaily}/deploy/run_pipeline.sh" --wait-for-lock "$@"
