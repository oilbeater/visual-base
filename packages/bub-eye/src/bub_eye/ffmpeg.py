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


def _encoder_args(settings: EyeSettings) -> list[str]:
    """Codec-specific flags. Dispatches on codec family.

    - *_videotoolbox (Apple hardware): bitrate-controlled, near-zero CPU. Default.
    - libx264 (software fallback): CRF + still-image tuning.
    - any other codec name: treated as a bitrate-controlled encoder.
    """
    codec = settings.codec
    if codec.endswith("_videotoolbox"):
        args = ["-c:v", codec, "-b:v", settings.bitrate]
        # `-tag:v hvc1` makes HEVC files playable in QuickTime / Finder preview.
        if codec.startswith("hevc"):
            args += ["-tag:v", "hvc1"]
        return args
    if codec == "libx264":
        return [
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
        ]
    # Generic: codec + bitrate, no assumptions about tuning flags.
    return ["-c:v", codec, "-b:v", settings.bitrate]


def build_command(
    settings: EyeSettings,
    ffmpeg: str,
    screen_index: int,
    run_id: str,
    run_start_iso: str,
) -> list[str]:
    """Build the long-running ffmpeg command line.

    Capture strategy: let avfoundation run at its native rate and decimate with
    the `fps` filter. Passing `-framerate` to avfoundation is unreliable across
    macOS versions; `-vf fps=N` always works.

    The `-strftime 1` segment pattern writes filenames in the subprocess's
    local time; the supervisor passes `TZ=UTC` in the environment so filenames
    are UTC-stamped regardless of host timezone.
    """
    fps = settings.framerate
    seg = settings.segment_seconds

    vf_parts: list[str] = [f"fps={fps}"]
    if settings.scale_height != -1:
        vf_parts.append(f"scale=-2:{settings.scale_height}")

    cmd: list[str] = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "warning",
        "-f",
        "avfoundation",
        "-capture_cursor",
        "1",
        "-i",
        f"{screen_index}:none",
        "-an",
        "-vf",
        ",".join(vf_parts),
    ]

    cmd += _encoder_args(settings)

    cmd += [
        "-g",
        str(max(1, int(round(fps * seg)))),
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
