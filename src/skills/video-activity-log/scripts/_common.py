"""Shared helpers for video-activity-log scripts.

Kept private (leading underscore) because the skill exposes `finalize_log.py` and
`preflight_idle.py` as the user-facing entry points — this module is only imported
by those two.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

FILENAME_RE = re.compile(r"eye_(\d{8})_(\d{6})\.")


def parse_video_start(video_path: Path) -> datetime:
    """Parse wall-clock start from a bub-eye filename (`eye_YYYYMMDD_HHMMSS.<ext>`)."""
    m = FILENAME_RE.search(video_path.name)
    if not m:
        raise SystemExit(
            f"cannot parse wall-clock start from filename: {video_path.name} "
            "(expected eye_YYYYMMDD_HHMMSS.<ext>); pass --base-time explicitly"
        )
    date_str, time_str = m.groups()
    return datetime.strptime(date_str + time_str, "%Y%m%d%H%M%S")


def get_video_duration(video_path: Path) -> float | None:
    """Return video duration in seconds via ffprobe, or None if ffprobe is unavailable.

    Exits with code 2 on a clear error (ffprobe present but failed on a reachable file)
    so callers can propagate a distinct "environment problem" status.
    """
    if not shutil.which("ffprobe"):
        print("warning: ffprobe not found on PATH — skipping duration-based checks", file=sys.stderr)
        return None
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=nw=1:nk=1",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"error: ffprobe failed on {video_path}: {e.stderr.strip()}", file=sys.stderr)
        raise SystemExit(2) from e
    out = result.stdout.strip()
    if not out:
        return None
    try:
        return float(out)
    except ValueError:
        return None


def fmt_abs(dt: datetime) -> str:
    return dt.strftime("%H:%M:%S")
