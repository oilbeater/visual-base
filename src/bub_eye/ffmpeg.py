"""ffmpeg binary resolution, avfoundation device probing, and command construction."""

from __future__ import annotations

import re
import socket
import subprocess

from imageio_ffmpeg import get_ffmpeg_exe

from bub_eye.settings import EyeSettings

_SCREEN_RE = re.compile(r"\[(\d+)\]\s+Capture screen \d+", re.IGNORECASE)


def resolve_ffmpeg(settings: EyeSettings) -> str:
    if settings.ffmpeg:
        return settings.ffmpeg
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

    Capture strategy: the `fps` filter is the source of truth for the output
    rate — it always works, whereas `-framerate` on avfoundation screen devices
    is unreliable across macOS versions. We still pass `-framerate 1` as a hint
    so avfoundation backs off its default 60 Hz target and shrinks the internal
    ring buffer; combined with `-pixel_format nv12` (which matches the native
    input format of `hevc_videotoolbox` and skips a BGRA→YUV swscale pass),
    this cut RSS from ~267 MB to ~96 MB in local testing. Either flag alone
    regresses — they must be added together. The hardcoded `1` is deliberate:
    any low target triggers the buffer downshift, and avfoundation may reject
    fractional values when `sample_interval_seconds` > 1.

    The `-strftime 1` segment pattern writes filenames in the subprocess's
    local time; the supervisor passes `TZ=UTC` in the environment so filenames
    are UTC-stamped regardless of host timezone.
    """
    fps = 1.0 / settings.sample_interval_seconds
    seg = settings.segment_seconds
    kf = settings.keyframe_interval_seconds

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
        "-framerate",
        "1",
        "-pixel_format",
        "nv12",
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
        # `-g` is respected by libx264 but largely ignored by hevc_videotoolbox
        # (Apple's hardware encoder uses its own internal keyframe strategy,
        # often a very long default GOP). We add `-force_key_frames` as the
        # hard guarantee so the segment muxer — which can only cut on keyframes —
        # actually rotates. keyframe_interval_seconds is decoupled from
        # segment_seconds so long segments still have interior seek points.
        "-g",
        str(max(1, int(round(fps * kf)))),
        "-force_key_frames",
        f"expr:gte(t,n_forced*{kf})",
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
