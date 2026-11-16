"""YouTube LLM calls that resume accepted fleet work instead of aborting a run."""

from __future__ import annotations

import os
import time

from aidaily.integrations import openrouter


def complete_json(*args, resume_timeout: int | None = None,
                  poll_interval: int | None = None, **kwargs):
    """Resume the same stable request until it finishes.

    ``openrouter.complete`` already falls back after a *confirmed* local
    inability when ``allow_external`` is true.  An accepted/busy job is not a
    failure: keep querying its identical request ID so it cannot be duplicated.
    """
    if resume_timeout is None:
        resume_timeout = int(os.environ.get("YOUTUBE_LLM_RESUME_TIMEOUT", "1800"))
    if poll_interval is None:
        poll_interval = int(os.environ.get("YOUTUBE_LLM_POLL_INTERVAL", "15"))
    deadline = time.monotonic() + max(0, resume_timeout)
    kwargs.setdefault("allow_external", True)
    while True:
        try:
            return openrouter.complete_json(*args, **kwargs)
        except openrouter.CompletionPending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(max(1, poll_interval), remaining))
