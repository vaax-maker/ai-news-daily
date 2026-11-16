"""Serialize late-source generation/publication with the scheduled daily release."""
from __future__ import annotations
import fcntl
import subprocess
import sys
from aidaily import config


def main():
    directory = config.DATA_ROOT / 'publishing/daily_runs'
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'pipeline.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for module, extra in (
            ('aidaily.ai_news.pipeline', ['--docs-root', 'docs']),
            ('aidaily.publishing.pipeline', []),
        ):
            code = subprocess.run([sys.executable, '-m', module, *extra],
                                  cwd=config.PROJECT_ROOT).returncode
            if code:
                return code
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
