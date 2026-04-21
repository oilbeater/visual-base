from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bub.channels.message import ChannelMessage

from bub_eye.settings import EyeSettings
from bub_eye.understand import SegmentUnderstander
from bub_eye.understand.state import SegmentState, load_state, save_state


def _build_settings(tmp_path: Path, **overrides: Any) -> EyeSettings:
    defaults: dict[str, Any] = {
        "segments_dir": tmp_path / "segments",
        "understand_state_dir": tmp_path / "state",
        "understand_logs_dir": tmp_path / "logs",
        "understand_finalize_grace_seconds": 1.0,
        "understand_processing_timeout_seconds": 1200.0,
        "understand_retry_after_seconds": 3600.0,
        "understand_max_attempts": 3,
        "understand_trigger_phrase": "please analyze {video}",
    }
    defaults.update(overrides)
    (tmp_path / "segments").mkdir(exist_ok=True)
    (tmp_path / "state").mkdir(exist_ok=True)
    return EyeSettings(**defaults)


def _make_segment(
    settings: EyeSettings, name: str, *, age_seconds: float = 60.0
) -> Path:
    path = settings.segments_dir / name
    path.write_bytes(b"")
    past = time.time() - age_seconds
    os.utime(path, (past, past))
    return path


def _iso(seconds_ago: float) -> str:
    return (datetime.now(UTC) - timedelta(seconds=seconds_ago)).isoformat()


class _Handler:
    """Async callable that records every ChannelMessage it receives."""

    def __init__(self) -> None:
        self.calls: list[ChannelMessage] = []
        self.raise_exc: Exception | None = None

    async def __call__(self, message: ChannelMessage) -> None:
        if self.raise_exc is not None:
            raise self.raise_exc
        self.calls.append(message)


@pytest.mark.asyncio
async def test_pending_segment_is_injected_and_marked_processing(
    tmp_path: Path,
) -> None:
    settings = _build_settings(tmp_path)
    handler = _Handler()
    understander = SegmentUnderstander(settings, handler)

    older = _make_segment(settings, "eye_20260421_090000.mp4", age_seconds=3600)
    _make_segment(
        settings, "eye_20260421_100000.mp4", age_seconds=60
    )  # newest — skipped

    await understander.tick(now=time.time())

    assert len(handler.calls) == 1
    msg = handler.calls[0]
    assert msg.channel == "eye"
    assert msg.session_id == "eye-eye_20260421_090000"
    assert str(older.resolve()) in msg.content
    assert "please analyze" in msg.content

    state = load_state(settings.understand_state_dir, older)
    assert state.status == "processing"


@pytest.mark.asyncio
async def test_newest_segment_is_never_processed(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    handler = _Handler()
    understander = SegmentUnderstander(settings, handler)
    _make_segment(settings, "eye_20260421_100000.mp4", age_seconds=60)

    await understander.tick(now=time.time())

    assert handler.calls == []


@pytest.mark.asyncio
async def test_md_already_exists_triggers_drift_heal_to_done(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    handler = _Handler()
    understander = SegmentUnderstander(settings, handler)

    older = _make_segment(settings, "eye_20260421_090000.mp4", age_seconds=3600)
    _make_segment(settings, "eye_20260421_100000.mp4", age_seconds=60)
    (settings.segments_dir / "eye_20260421_090000.md").write_text(
        "---\ndate: 2026-04-21\nstart: 09:00:00\nend: 09:05:00\n---\n\n"
        "# 活动日志\n\n- `09:00:00 - 09:05:00` 在 [[VS Code]] 写代码\n"
    )

    await understander.tick(now=time.time())

    assert handler.calls == []
    state = load_state(settings.understand_state_dir, older)
    assert state.status == "done"

    daily = settings.understand_logs_dir / "2026-04-21.md"
    assert daily.exists()
    body = daily.read_text(encoding="utf-8")
    assert "- `09:00:00 - 09:05:00` 在 [[VS Code]] 写代码" in body
    assert "  - eye_20260421_090000.mp4" in body
    assert "# [[2026-04-21]] 活动日志" in body


@pytest.mark.asyncio
async def test_two_segments_aggregate_into_single_daily(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    handler = _Handler()
    understander = SegmentUnderstander(settings, handler)

    seg_a = _make_segment(settings, "eye_20260421_090000.mp4", age_seconds=7200)
    seg_b = _make_segment(settings, "eye_20260421_091500.mp4", age_seconds=3600)
    # A third newest file is needed so seg_b is considered finalized
    # (list_finalized_segments always skips the newest).
    _make_segment(settings, "eye_20260421_100000.mp4", age_seconds=60)

    (settings.segments_dir / "eye_20260421_090000.md").write_text(
        "---\ndate: 2026-04-21\nstart: 09:00:00\nend: 09:05:00\n---\n\n"
        "# 活动日志\n\n- `09:00:00 - 09:05:00` 在 [[VS Code]] 写代码\n"
    )
    (settings.segments_dir / "eye_20260421_091500.md").write_text(
        "---\ndate: 2026-04-21\nstart: 09:15:00\nend: 09:30:00\n---\n\n"
        "# 活动日志\n\n- `09:15:00 - 09:30:00` 在 [[微信]] 和 [[chenkai]] 讨论\n"
    )

    await understander.tick(now=time.time())

    for video in (seg_a, seg_b):
        assert load_state(settings.understand_state_dir, video).status == "done"

    daily = settings.understand_logs_dir / "2026-04-21.md"
    assert daily.exists()
    body = daily.read_text(encoding="utf-8")
    assert body.index("- `09:00:00 - 09:05:00`") < body.index("- `09:15:00 - 09:30:00`")
    assert "  - eye_20260421_090000.mp4" in body
    assert "  - eye_20260421_091500.mp4" in body
    assert "start: 09:00:00" in body
    assert "end: 09:30:00" in body


@pytest.mark.asyncio
async def test_idle_segment_is_not_merged_into_daily(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    handler = _Handler()
    understander = SegmentUnderstander(settings, handler)

    older = _make_segment(settings, "eye_20260421_090000.mp4", age_seconds=3600)
    _make_segment(settings, "eye_20260421_100000.mp4", age_seconds=60)
    (settings.segments_dir / "eye_20260421_090000.md").write_text(
        "---\nidle: true\n---\n#idle screensaver only\n"
    )

    await understander.tick(now=time.time())

    assert load_state(settings.understand_state_dir, older).status == "idle"
    daily = settings.understand_logs_dir / "2026-04-21.md"
    assert not daily.exists()


@pytest.mark.asyncio
async def test_idle_md_transitions_to_idle_terminal(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    handler = _Handler()
    understander = SegmentUnderstander(settings, handler)

    older = _make_segment(settings, "eye_20260421_090000.mp4", age_seconds=3600)
    _make_segment(settings, "eye_20260421_100000.mp4", age_seconds=60)
    (settings.segments_dir / "eye_20260421_090000.md").write_text(
        "---\nidle: true\n---\n#idle screensaver only\n"
    )

    await understander.tick(now=time.time())

    assert handler.calls == []
    state = load_state(settings.understand_state_dir, older)
    assert state.status == "idle"


@pytest.mark.asyncio
async def test_already_done_segment_is_skipped(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    handler = _Handler()
    understander = SegmentUnderstander(settings, handler)

    older = _make_segment(settings, "eye_20260421_090000.mp4", age_seconds=3600)
    _make_segment(settings, "eye_20260421_100000.mp4", age_seconds=60)
    done_state = SegmentState(status="done")
    done_state.mark("done")
    save_state(settings.understand_state_dir, older, done_state)

    await understander.tick(now=time.time())

    assert handler.calls == []


@pytest.mark.asyncio
async def test_handler_exception_keeps_state_pending_and_does_not_bump_attempts(
    tmp_path: Path,
) -> None:
    settings = _build_settings(tmp_path)
    handler = _Handler()
    handler.raise_exc = RuntimeError("queue full")
    understander = SegmentUnderstander(settings, handler)

    older = _make_segment(settings, "eye_20260421_090000.mp4", age_seconds=3600)
    _make_segment(settings, "eye_20260421_100000.mp4", age_seconds=60)

    await understander.tick(now=time.time())

    state = load_state(settings.understand_state_dir, older)
    assert state.status == "pending"
    assert state.attempts == 0
    assert state.last_error and "queue full" in state.last_error


@pytest.mark.asyncio
async def test_stale_processing_is_reset_and_counts_as_attempt(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path, understand_processing_timeout_seconds=60.0)
    handler = _Handler()
    understander = SegmentUnderstander(settings, handler)

    older = _make_segment(settings, "eye_20260421_090000.mp4", age_seconds=3600)
    _make_segment(settings, "eye_20260421_100000.mp4", age_seconds=60)

    stale = SegmentState(status="processing")
    stale.updated_at = _iso(1000)  # far past timeout
    save_state(settings.understand_state_dir, older, stale)

    await understander.tick(now=time.time())

    state = load_state(settings.understand_state_dir, older)
    # After bumping to `failed` in the same tick, updated_at is fresh so
    # the retry backoff hasn't elapsed yet → no re-inject in the same tick.
    assert state.status == "failed"
    assert state.attempts == 1
    assert handler.calls == []


@pytest.mark.asyncio
async def test_retry_due_segment_is_reinjected(tmp_path: Path) -> None:
    settings = _build_settings(
        tmp_path,
        understand_retry_after_seconds=10.0,
        understand_max_attempts=3,
    )
    handler = _Handler()
    understander = SegmentUnderstander(settings, handler)

    older = _make_segment(settings, "eye_20260421_090000.mp4", age_seconds=3600)
    _make_segment(settings, "eye_20260421_100000.mp4", age_seconds=60)

    failed = SegmentState(status="failed", attempts=1)
    failed.updated_at = _iso(30)  # past 10s * 2^0 = 10s backoff
    save_state(settings.understand_state_dir, older, failed)

    await understander.tick(now=time.time())

    assert len(handler.calls) == 1
    state = load_state(settings.understand_state_dir, older)
    assert state.status == "processing"
    # attempts untouched by the inject; next failure will bump.
    assert state.attempts == 1


@pytest.mark.asyncio
async def test_max_attempts_terminal_never_reinjects(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path, understand_max_attempts=3)
    handler = _Handler()
    understander = SegmentUnderstander(settings, handler)

    older = _make_segment(settings, "eye_20260421_090000.mp4", age_seconds=3600)
    _make_segment(settings, "eye_20260421_100000.mp4", age_seconds=60)

    done_failing = SegmentState(status="failed", attempts=3)
    done_failing.updated_at = _iso(9_999_999)
    save_state(settings.understand_state_dir, older, done_failing)

    await understander.tick(now=time.time())

    assert handler.calls == []
    state = load_state(settings.understand_state_dir, older)
    assert state.status == "failed"
    assert state.attempts == 3


@pytest.mark.asyncio
async def test_disabled_worker_never_runs(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path, auto_understand_enabled=False)
    handler = _Handler()
    understander = SegmentUnderstander(settings, handler)

    _make_segment(settings, "eye_20260421_090000.mp4", age_seconds=3600)
    _make_segment(settings, "eye_20260421_100000.mp4", age_seconds=60)

    import asyncio

    stop = asyncio.Event()
    stop.set()  # short-circuit: loop should not even start
    await understander.run(stop)

    assert handler.calls == []
