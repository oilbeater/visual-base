"""ffmpeg binary resolution, avfoundation device probing, and command construction."""

from __future__ import annotations

import re
import socket
import subprocess
import sys

from bub_eye.settings import EyeSettings

_SCREEN_RE = re.compile(r"\[(\d+)\]\s+Capture screen \d+", re.IGNORECASE)
IMAGEIO_FFMPEG_SPEC = "imageio-ffmpeg>=0.5.1"

_imageio_ffmpeg_install_checked = False


def _ensure_imageio_ffmpeg_installed() -> None:
    """Install `imageio-ffmpeg` into the current venv if missing.

    We ship `visual-base` without this heavy dep (≈70 MB ffmpeg binary) so
    Linux / Apple Silicon users don't download it for nothing. On Intel Mac
    the screen-recording supervisor is the only caller that reaches here,
    and we install lazily via uv the first time it's needed.
    """
    global _imageio_ffmpeg_install_checked
    if _imageio_ffmpeg_install_checked:
        return
    try:
        import imageio_ffmpeg  # noqa: F401
    except ImportError:
        pass
    else:
        _imageio_ffmpeg_install_checked = True
        return

    print(
        f"bub-eye: imageio-ffmpeg not installed; adding `{IMAGEIO_FFMPEG_SPEC}` "
        "via `uv pip install` (one-time setup)…",
        file=sys.stderr,
        flush=True,
    )
    try:
        subprocess.run(
            ["uv", "pip", "install", "--python", sys.executable, IMAGEIO_FFMPEG_SPEC],
            check=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "bub-eye: cannot auto-install imageio-ffmpeg because `uv` is not on PATH. "
            "Install uv (https://docs.astral.sh/uv/) or pre-install imageio-ffmpeg manually."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"bub-eye: `uv pip install {IMAGEIO_FFMPEG_SPEC}` failed with exit code "
            f"{exc.returncode}. Run it manually to see the underlying error."
        ) from exc

    try:
        import imageio_ffmpeg  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "bub-eye: imageio-ffmpeg was installed but still cannot be imported. "
            "Check the active venv with `uv pip list --python "
            f"{sys.executable}`."
        ) from exc
    _imageio_ffmpeg_install_checked = True


def resolve_ffmpeg(settings: EyeSettings) -> str:
    if settings.ffmpeg:
        return settings.ffmpeg
    _ensure_imageio_ffmpeg_installed()
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
