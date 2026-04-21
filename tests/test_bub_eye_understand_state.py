from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from bub_eye.understand.state import (
    SegmentState,
    list_finalized_segments,
    load_state,
    md_is_idle,
    md_output_path,
    retry_due,
    save_state,
    stale_processing,
)


def _write_segment(dir_path: Path, name: str, *, age_seconds: float = 3600) -> Path:
    path = dir_path / name
    path.write_bytes(b"")
    past = time.time() - age_seconds
    os.utime(path, (past, past))
    return path


def _iso(seconds_ago: float) -> str:
    return (datetime.now(UTC) - timedelta(seconds=seconds_ago)).isoformat()


def test_save_then_load_roundtrip(tmp_path: Path) -> None:
    video = tmp_path / "eye_20260421_100000.mp4"
    state = SegmentState()
    state.mark("processing")
    save_state(tmp_path, video, state)

    loaded = load_state(tmp_path, video)
    assert loaded.status == "processing"
    assert loaded.attempts == 0
    assert loaded.updated_at


def test_load_missing_file_returns_fresh_pending(tmp_path: Path) -> None:
    video = tmp_path / "eye_20260421_100000.mp4"
    loaded = load_state(tmp_path, video)
    assert loaded.status == "pending"
    assert loaded.attempts == 0


def test_load_corrupted_json_falls_back_to_pending(tmp_path: Path) -> None:
    video = tmp_path / "eye_20260421_100000.mp4"
    state_file = tmp_path / "eye_20260421_100000.json"
    state_file.write_text("{not valid json")
    loaded = load_state(tmp_path, video)
    assert loaded.status == "pending"


def test_save_is_atomic_no_tmp_left_behind(tmp_path: Path) -> None:
    video = tmp_path / "eye_20260421_100000.mp4"
    state = SegmentState(status="done")
    state.mark("done")
    save_state(tmp_path, video, state)
    assert (tmp_path / "eye_20260421_100000.json").exists()
    assert not (tmp_path / "eye_20260421_100000.json.tmp").exists()


def test_load_rejects_unknown_status(tmp_path: Path) -> None:
    video = tmp_path / "eye_20260421_100000.mp4"
    (tmp_path / "eye_20260421_100000.json").write_text(
        json.dumps(
            {"status": "BOGUS", "attempts": 0, "last_error": None, "updated_at": ""}
        )
    )
    loaded = load_state(tmp_path, video)
    assert loaded.status == "pending"


def test_list_finalized_skips_newest(tmp_path: Path) -> None:
    older = _write_segment(tmp_path, "eye_20260421_090000.mp4", age_seconds=3600)
    _write_segment(tmp_path, "eye_20260421_100000.mp4", age_seconds=3600)
    out = list_finalized_segments(tmp_path, now=time.time(), grace_seconds=1.0)
    assert out == [older]


def test_list_finalized_with_single_segment_returns_empty(tmp_path: Path) -> None:
    _write_segment(tmp_path, "eye_20260421_100000.mp4", age_seconds=3600)
    out = list_finalized_segments(tmp_path, now=time.time(), grace_seconds=1.0)
    assert out == []


def test_list_finalized_respects_grace(tmp_path: Path) -> None:
    _write_segment(tmp_path, "eye_20260421_090000.mp4", age_seconds=2)
    _write_segment(tmp_path, "eye_20260421_100000.mp4", age_seconds=1)
    # Older segment age=2s; grace=10s → excluded.
    out = list_finalized_segments(tmp_path, now=time.time(), grace_seconds=10.0)
    assert out == []


def test_list_finalized_ignores_non_matching_filenames(tmp_path: Path) -> None:
    older = _write_segment(tmp_path, "eye_20260421_090000.mp4", age_seconds=3600)
    _write_segment(tmp_path, "eye_20260421_100000.mp4", age_seconds=3600)
    _write_segment(tmp_path, "stray.mp4", age_seconds=3600)
    _write_segment(tmp_path, "eye_bad.mp4", age_seconds=3600)
    _write_segment(tmp_path, "eye_20260421_090000.mp4.md", age_seconds=3600)
    out = list_finalized_segments(tmp_path, now=time.time(), grace_seconds=1.0)
    assert out == [older]


def test_list_finalized_missing_dir_returns_empty(tmp_path: Path) -> None:
    out = list_finalized_segments(tmp_path / "nope", now=time.time(), grace_seconds=1.0)
    assert out == []


def test_md_output_path(tmp_path: Path) -> None:
    video = tmp_path / "eye_20260421_100000.mp4"
    assert md_output_path(video) == tmp_path / "eye_20260421_100000.md"


def test_md_is_idle_detects_marker(tmp_path: Path) -> None:
    md = tmp_path / "a.md"
    md.write_text("---\nidle: true\n---\n")
    assert md_is_idle(md) is True

    md.write_text("# 活动日志\n\n#idle this is a stub from preflight\n")
    assert md_is_idle(md) is True


def test_md_is_idle_returns_false_for_normal_log(tmp_path: Path) -> None:
    md = tmp_path / "a.md"
    md.write_text("# 活动日志\n\n- `00:00 - 05:00` 在 [[VS Code]] 写代码\n")
    assert md_is_idle(md) is False


def test_md_is_idle_missing_file(tmp_path: Path) -> None:
    assert md_is_idle(tmp_path / "nope.md") is False


def test_stale_processing_true_when_timeout_exceeded() -> None:
    state = SegmentState(status="processing", updated_at=_iso(1500))
    assert stale_processing(state, now=time.time(), timeout=1200) is True


def test_stale_processing_false_for_fresh_processing() -> None:
    state = SegmentState(status="processing", updated_at=_iso(10))
    assert stale_processing(state, now=time.time(), timeout=1200) is False


def test_stale_processing_false_for_non_processing() -> None:
    state = SegmentState(status="pending", updated_at=_iso(9999))
    assert stale_processing(state, now=time.time(), timeout=1200) is False


def test_stale_processing_true_when_updated_at_missing() -> None:
    state = SegmentState(status="processing", updated_at="")
    assert stale_processing(state, now=time.time(), timeout=1200) is True


def test_retry_due_respects_exponential_backoff() -> None:
    # attempts=1: wait >= retry_after * 2^0 = retry_after
    state = SegmentState(status="failed", attempts=1, updated_at=_iso(3601))
    assert retry_due(state, now=time.time(), retry_after=3600, max_attempts=3) is True
    state2 = SegmentState(status="failed", attempts=1, updated_at=_iso(100))
    assert retry_due(state2, now=time.time(), retry_after=3600, max_attempts=3) is False


def test_retry_due_second_attempt_doubles_backoff() -> None:
    # attempts=2: wait >= retry_after * 2^1 = 2h; after 1h should still not retry
    state = SegmentState(status="failed", attempts=2, updated_at=_iso(3700))
    assert retry_due(state, now=time.time(), retry_after=3600, max_attempts=5) is False
    # after >2h it becomes eligible
    state2 = SegmentState(status="failed", attempts=2, updated_at=_iso(7300))
    assert retry_due(state2, now=time.time(), retry_after=3600, max_attempts=5) is True


def test_retry_due_not_eligible_at_max_attempts() -> None:
    state = SegmentState(status="failed", attempts=3, updated_at=_iso(999999))
    assert retry_due(state, now=time.time(), retry_after=3600, max_attempts=3) is False


def test_retry_due_not_eligible_for_non_failed() -> None:
    for status in ("pending", "processing", "done", "idle"):
        state = SegmentState(status=status, attempts=1, updated_at=_iso(999999))  # type: ignore[arg-type]
        assert retry_due(state, now=time.time(), retry_after=0, max_attempts=3) is False


@pytest.mark.parametrize(
    "status,expected_terminal",
    [
        ("pending", False),
        ("processing", False),
        ("done", True),
        ("idle", True),
        ("failed", False),
    ],
)
def test_terminal_property(status: str, expected_terminal: bool) -> None:
    state = SegmentState(status=status)  # type: ignore[arg-type]
    assert state.terminal is expected_terminal


def test_mark_bumps_attempts_and_error() -> None:
    state = SegmentState()
    state.mark("failed", last_error="boom", bump_attempts=True)
    assert state.status == "failed"
    assert state.attempts == 1
    assert state.last_error == "boom"
    assert state.updated_at  # not empty

    state.mark("processing")  # bump defaults to False
    assert state.attempts == 1
    assert state.last_error is None
