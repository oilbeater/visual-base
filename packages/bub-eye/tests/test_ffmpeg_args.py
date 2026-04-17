"""Unit tests for build_command — pure string construction, no subprocess."""

from __future__ import annotations

from pathlib import Path

from bub_eye.ffmpeg import build_command
from bub_eye.settings import EyeSettings


def _settings(**overrides: object) -> EyeSettings:
    base: dict[str, object] = {
        "enabled": True,
        "ffmpeg": None,
        "framerate": 1.0,
        "segment_seconds": 60,
        "codec": "hevc_videotoolbox",
        "bitrate": "1200k",
        "crf": 28,
        "scale_height": 720,
        "segments_dir": Path("/tmp/bub-eye-segments"),
        "tape_dir": Path("/tmp/bub-eye-tapes"),
        "display_index": None,
    }
    base.update(overrides)
    return EyeSettings(**base)  # type: ignore[arg-type]


def test_includes_avfoundation_input() -> None:
    cmd = build_command(
        _settings(), "/usr/bin/ffmpeg", screen_index=1, run_id="r1", run_start_iso="2026-04-17T00:00:00+00:00"
    )
    assert "-f" in cmd and "avfoundation" in cmd
    i_pos = cmd.index("-i")
    assert cmd[i_pos + 1] == "1:none"


def test_fps_filter_drives_framerate() -> None:
    """We use `-vf fps=N` instead of `-framerate N` for reliable decimation."""
    cmd = build_command(_settings(framerate=0.5), "ffmpeg", 0, "r", "t")
    vf = cmd[cmd.index("-vf") + 1]
    assert "fps=0.5" in vf
    # We do NOT set the input -framerate, to avoid avfoundation quirks.
    assert "-framerate" not in cmd


def test_segment_time_independent_of_fps() -> None:
    cmd = build_command(_settings(framerate=2.0, segment_seconds=30), "ffmpeg", 0, "r", "t")
    assert cmd[cmd.index("-segment_time") + 1] == "30"


def test_progress_pipe_flag_present() -> None:
    cmd = build_command(_settings(), "ffmpeg", 0, "r", "t")
    assert "-progress" in cmd
    assert cmd[cmd.index("-progress") + 1] == "pipe:1"


def test_gop_rounds_fps_times_segment() -> None:
    cmd = build_command(_settings(framerate=0.5, segment_seconds=60), "ffmpeg", 0, "r", "t")
    # 0.5 fps * 60 s = 30 frames per segment.
    assert cmd[cmd.index("-g") + 1] == "30"


def test_vf_combines_fps_and_scale() -> None:
    cmd = build_command(_settings(framerate=1.0, scale_height=540), "ffmpeg", 0, "r", "t")
    vf = cmd[cmd.index("-vf") + 1]
    assert vf == "fps=1.0,scale=-2:540"


def test_vf_drops_scale_when_disabled() -> None:
    cmd = build_command(_settings(scale_height=-1), "ffmpeg", 0, "r", "t")
    vf = cmd[cmd.index("-vf") + 1]
    assert vf.startswith("fps=")
    assert "scale" not in vf


def test_segment_path_uses_strftime_and_configured_dir() -> None:
    cmd = build_command(_settings(segments_dir=Path("/out")), "ffmpeg", 0, "r", "t")
    assert cmd[-1] == "/out/eye_%Y%m%d_%H%M%S.mp4"
    assert cmd[cmd.index("-strftime") + 1] == "1"


def test_metadata_carries_run_identifiers() -> None:
    cmd = build_command(_settings(), "ffmpeg", 0, "abc123", "2026-04-17T12:00:00+00:00")
    assert "run_id=abc123" in cmd
    assert "run_start=2026-04-17T12:00:00+00:00" in cmd
    assert "title=bub-eye" in cmd


def test_audio_disabled_explicitly() -> None:
    cmd = build_command(_settings(), "ffmpeg", 0, "r", "t")
    assert "-an" in cmd


def test_default_codec_is_hevc_videotoolbox_with_bitrate_cap() -> None:
    cmd = build_command(_settings(), "ffmpeg", 0, "r", "t")
    c_v_pos = cmd.index("-c:v")
    assert cmd[c_v_pos + 1] == "hevc_videotoolbox"
    assert cmd[cmd.index("-b:v") + 1] == "1200k"
    # HEVC needs the hvc1 tag for QuickTime/Finder to play/preview it.
    assert cmd[cmd.index("-tag:v") + 1] == "hvc1"
    # Hardware codec should NOT get software-only tuning flags.
    assert "-tune" not in cmd
    assert "-crf" not in cmd
    assert "-preset" not in cmd


def test_h264_videotoolbox_omits_hvc1_tag() -> None:
    cmd = build_command(_settings(codec="h264_videotoolbox", bitrate="2000k"), "ffmpeg", 0, "r", "t")
    assert cmd[cmd.index("-c:v") + 1] == "h264_videotoolbox"
    assert cmd[cmd.index("-b:v") + 1] == "2000k"
    assert "-tag:v" not in cmd


def test_libx264_fallback_uses_crf_and_stillimage_tuning() -> None:
    cmd = build_command(_settings(codec="libx264", crf=30), "ffmpeg", 0, "r", "t")
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert cmd[cmd.index("-tune") + 1] == "stillimage"
    assert cmd[cmd.index("-preset") + 1] == "veryfast"
    assert cmd[cmd.index("-crf") + 1] == "30"
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    # Software encoding ignores the bitrate knob.
    assert "-b:v" not in cmd
