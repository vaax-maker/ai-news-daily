"""
src/utils/archive.py — Daily archive file resolution utilities.
"""

import os


def resolve_daily_file(archive_dir: str, date_str: str, run_id: str) -> tuple:
    """Return (primary_filename, duplicate_filenames) for the given date.

    Finds existing HTML files for date_str in archive_dir.
    Returns the oldest file as primary (to preserve continuity),
    and any additional files as duplicates to be merged then removed.
    """
    os.makedirs(archive_dir, exist_ok=True)
    html_files = [
        f for f in os.listdir(archive_dir)
        if f.endswith(".html") and f.startswith(date_str)
    ]

    if html_files:
        html_files.sort()
        return html_files[0], html_files[1:]

    return f"{run_id}.html", []
