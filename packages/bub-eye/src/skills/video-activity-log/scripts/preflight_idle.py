#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Quick-scan a screen-recording segment and short-circuit the LLM call if it's idle.

Counts ffmpeg scene-change events with `select='gt(scene,<sensitivity>)'`. Divides by video
duration to get a rate (events / second). If the rate is below `--idle-scene-rate` AND the
video is at least `--idle-min-seconds` long, writes a one-line "idle" activity log directly
and exits 0 so the caller can skip the LLM phase. Otherwise exits 1.

Exit codes:
  0  — idle: a finalized markdown log has been written.
  1  — active: proceed to Phase 1 (LLM writes a draft).
  2  — error: ffmpeg / ffprobe missing, video unreadable, etc.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from _common import fmt_abs, get_video_duration, parse_video_start


def count_scene_changes(video: Path, sensitivity: float) -> int:
    """Run ffmpeg scene-change filter, return number of detected scene transitions."""
    if not shutil.which("ffmpeg"):
        print("error: ffmpeg not found on PATH", file=sys.stderr)
        raise SystemExit(2)
    cmd = [
        "ffmpeg",
        "-nostats",
        "-i", str(video),
        "-vf", f"select='gt(scene,{sensitivity})',showinfo",
        "-an",
        "-f", "null",
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"error: ffmpeg failed on {video}:\n{result.stderr.strip()[-500:]}", file=sys.stderr)
        raise SystemExit(2)
    # Every detected scene change prints one `showinfo` line with `pts_time:`.
    return sum(1 for line in result.stderr.splitlines() if "pts_time:" in line)


def write_idle_log(
    output: Path,
    video: Path,
    base: datetime,
    duration_seconds: float,
    scene_changes: int,
) -> None:
    end_dt = base + timedelta(seconds=duration_seconds)
    date = base.date().isoformat()
    content = (
        "---\n"
        f"video: {video}\n"
        f"date: {date}\n"
        f"start: {fmt_abs(base)}\n"
        f"end: {fmt_abs(end_dt)}\n"
        "idle: true\n"
        f"scene_changes: {scene_changes}\n"
        "---\n"
        "\n"
        f"# [[{date}]] 活动日志\n"
        "\n"
        f"- `{fmt_abs(base)} - {fmt_abs(end_dt)}` #idle 屏幕静止或锁屏，无活动\n"
        "\n"
        "## 关键实体\n"
        "\n"
        "_(空)_\n"
    )
    output.write_text(content, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--video", type=Path, required=True, help="source video path")
    ap.add_argument("--output", type=Path, help="output markdown path (default: sibling of video, .md)")
    ap.add_argument("--base-time", help="override wall-clock start (ISO-8601)")
    ap.add_argument("--idle-scene-rate", type=float, default=0.01,
                    help="max scene-changes per second to count as idle (default: 0.01)")
    ap.add_argument("--idle-min-seconds", type=float, default=60.0,
                    help="minimum video length to bother classifying (default: 60)")
    ap.add_argument("--scene-sensitivity", type=float, default=0.01,
                    help="ffmpeg scene filter threshold (default: 0.01)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print verdict and rate, don't write the idle log")
    args = ap.parse_args()

    duration = get_video_duration(args.video)
    if duration is None:
        print("error: could not determine video duration via ffprobe", file=sys.stderr)
        raise SystemExit(2)

    if duration < args.idle_min_seconds:
        print(f"video too short for idle classification ({duration:.1f}s < {args.idle_min_seconds}s); proceed to LLM",
              file=sys.stderr)
        raise SystemExit(1)

    scene_changes = count_scene_changes(args.video, args.scene_sensitivity)
    rate = scene_changes / duration if duration else 0.0
    is_idle = rate < args.idle_scene_rate

    print(f"duration={duration:.1f}s scene_changes={scene_changes} rate={rate:.4f}/s "
          f"threshold={args.idle_scene_rate}/s -> {'IDLE' if is_idle else 'ACTIVE'}",
          file=sys.stderr)

    if not is_idle:
        raise SystemExit(1)

    if args.dry_run:
        print("dry-run: would have written idle log and exited 0", file=sys.stderr)
        raise SystemExit(0)

    base = datetime.fromisoformat(args.base_time) if args.base_time else parse_video_start(args.video)
    out = args.output or args.video.with_suffix(".md")
    write_idle_log(out, args.video.resolve(), base, duration, scene_changes)
    print(f"wrote idle log: {out}", file=sys.stderr)
    raise SystemExit(0)


if __name__ == "__main__":
    main()
