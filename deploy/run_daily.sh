#!/bin/bash
# Compatibility entrypoint. AI News is now part of the unified daily pipeline.
exec /bin/bash "${AIDAILY_REPOSITORY:-$HOME/aidaily}/deploy/run_pipeline.sh" "$@"
