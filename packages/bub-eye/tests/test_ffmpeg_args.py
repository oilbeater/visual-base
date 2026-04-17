"""Unit tests for build_command — pure string construction, no subprocess."""

from __future__ import annotations

from pathlib import Path

from bub_eye.ffmpeg import build_command
from bub_eye.settings import EyeSettings


def _settings(**overrides: object) -> EyeSettings:
    base: dict[str, object] = {
        "enabled": True,
        "ffmpeg": None,
        "framerate": 1,
        "segment_seconds": 60,
        "crf": 28,
        "scale_height": 720,
        "segments_dir": Path("/tmp/bub-eye-segments"),
        "tape_dir": Path("/tmp/bub-eye-tapes"),
        "display_index": None,
    }
    base.update(overrides)
    return EyeSettings(**base)  # type: ignore[arg-type]


def test_includes_avfoundation_input() -> None:
    cmd = build_command(_settings(), "/usr/bin/ffmpeg", screen_index=1, run_id="r1", run_start_iso="2026-04-17T00:00:00+00:00")
    assert "-f" in cmd and "avfoundation" in cmd
    # -i "<index>:none" audio-less capture
    i_pos = cmd.index("-i")
    assert cmd[i_pos + 1] == "1:none"


def test_respects_framerate_and_segment_seconds() -> None:
    cmd = build_command(_settings(framerate=2, segment_seconds=30), "ffmpeg", 0, "r", "t")
    # framerate flag preceding avfoundation? -framerate appears after -f/-framerate pair
    assert cmd[cmd.index("-framerate") + 1] == "2"
    assert cmd[cmd.index("-segment_time") + 1] == "30"


def test_progress_pipe_flag_present() -> None:
    cmd = build_command(_settings(), "ffmpeg", 0, "r", "t")
    assert "-progress" in cmd
    assert cmd[cmd.index("-progress") + 1] == "pipe:1"


def test_gop_is_framerate_times_segment() -> None:
    cmd = build_command(_settings(framerate=2, segment_seconds=30), "ffmpeg", 0, "r", "t")
    assert cmd[cmd.index("-g") + 1] == "60"


def test_scale_filter_included_when_height_positive() -> None:
    cmd = build_command(_settings(scale_height=540), "ffmpeg", 0, "r", "t")
    assert "-vf" in cmd
    assert cmd[cmd.index("-vf") + 1] == "scale=-2:540"


def test_scale_filter_omitted_when_disabled() -> None:
    cmd = build_command(_settings(scale_height=-1), "ffmpeg", 0, "r", "t")
    assert "-vf" not in cmd


def test_segment_path_uses_strftime_and_configured_dir() -> None:
    cmd = build_command(_settings(segments_dir=Path("/out")), "ffmpeg", 0, "r", "t")
    # Last element is the output pattern.
    assert cmd[-1] == "/out/eye_%Y%m%d_%H%M%S.mp4"
    assert cmd[cmd.index("-strftime") + 1] == "1"


def test_metadata_carries_run_identifiers() -> None:
    cmd = build_command(_settings(), "ffmpeg", 0, "abc123", "2026-04-17T12:00:00+00:00")
    # -metadata flags and their values arrive as successive list entries.
    assert "run_id=abc123" in cmd
    assert "run_start=2026-04-17T12:00:00+00:00" in cmd
    assert "title=bub-eye" in cmd
