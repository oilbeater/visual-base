"""ffmpeg binary resolution, avfoundation device probing, and command construction."""

from __future__ import annotations

import re
import socket
import subprocess

from bub_eye.settings import EyeSettings

_SCREEN_RE = re.compile(r"\[(\d+)\]\s+Capture screen \d+", re.IGNORECASE)


def resolve_ffmpeg(settings: EyeSettings) -> str:
    if settings.ffmpeg:
        return settings.ffmpeg
    from imageio_ffmpeg import get_ffmpeg_exe

    return get_ffmpeg_exe()


def detect_screen_index(ffmpeg: str) -> int:
    """Return the first avfoundation `Capture screen N` index.

    `ffmpeg -f avfoundation -list_devices true -i ""` exits non-zero and writes
    the device list to stderr; that's the expected behavior, not a failure.
    """
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
        capture_output=True,
        text=True,
        timeout=15,
    )
    output = proc.stderr
    for line in output.splitlines():
        if "Capture screen" not in line:
            continue
        match = _SCREEN_RE.search(line)
        if match:
            return int(match.group(1))
    raise RuntimeError(
        "bub-eye: no avfoundation 'Capture screen' device found. "
        "Set BUB_EYE_DISPLAY_INDEX explicitly or install an ffmpeg with avfoundation support. "
        f"Raw output:\n{output}"
    )


def build_command(
    settings: EyeSettings,
    ffmpeg: str,
    screen_index: int,
    run_id: str,
    run_start_iso: str,
) -> list[str]:
    """Build the long-running ffmpeg command line.

    The `-strftime 1` segment pattern writes filenames in the subprocess's
    local time; the supervisor passes `TZ=UTC` in the environment so filenames
    are UTC-stamped regardless of host timezone.
    """
    fps = settings.framerate
    seg = settings.segment_seconds

    cmd: list[str] = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "warning",
        "-f",
        "avfoundation",
        "-framerate",
        str(fps),
        "-capture_cursor",
        "1",
        "-i",
        f"{screen_index}:none",
    ]

    if settings.scale_height != -1:
        cmd += ["-vf", f"scale=-2:{settings.scale_height}"]

    cmd += [
        "-c:v",
        "libx264",
        "-tune",
        "stillimage",
        "-preset",
        "veryfast",
        "-crf",
        str(settings.crf),
        "-pix_fmt",
        "yuv420p",
        "-g",
        str(max(1, fps * seg)),
        "-metadata",
        "title=bub-eye",
        "-metadata",
        f"host={socket.gethostname()}",
        "-metadata",
        f"run_id={run_id}",
        "-metadata",
        f"run_start={run_start_iso}",
        "-progress",
        "pipe:1",
        "-nostats",
        "-f",
        "segment",
        "-segment_time",
        str(seg),
        "-reset_timestamps",
        "1",
        "-strftime",
        "1",
        str(settings.segments_dir / "eye_%Y%m%d_%H%M%S.mp4"),
    ]
    return cmd
