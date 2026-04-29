from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import bub_eye.channel as channel_module
from bub_eye.channel import EyeChannel
from bub_eye.plugin import EyeImpl
from bub_eye.settings import EyeSettings


async def _noop_handler(_msg: Any) -> None:
    return None


def test_provide_channels_threads_handler_into_eye_channel(tmp_path: Path) -> None:
    framework = SimpleNamespace(workspace=tmp_path)
    impl = EyeImpl(framework=framework)
    channels = impl.provide_channels(_noop_handler)
    assert len(channels) == 1
    assert isinstance(channels[0], EyeChannel)
    assert channels[0]._message_handler is _noop_handler


def test_provide_channels_uses_framework_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for var in (
        "BUB_EYE_SEGMENTS_DIR",
        "BUB_EYE_LOGS_DIR",
        "BUB_EYE_UNDERSTAND_STATE_DIR",
        "BUB_EYE_UNDERSTAND_LOGS_DIR",
    ):
        monkeypatch.delenv(var, raising=False)
    framework = SimpleNamespace(workspace=tmp_path)
    impl = EyeImpl(framework=framework)
    channels = impl.provide_channels(_noop_handler)
    settings = channels[0]._settings
    assert settings.segments_dir == tmp_path / "recordings"
    assert settings.logs_dir == tmp_path / "logs"
    assert settings.understand_state_dir == tmp_path / ".eye-state"
    assert settings.understand_logs_dir == tmp_path / "daily-logs"


def test_provide_channels_without_framework_falls_back_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for var in (
        "BUB_EYE_SEGMENTS_DIR",
        "BUB_EYE_LOGS_DIR",
        "BUB_EYE_UNDERSTAND_STATE_DIR",
        "BUB_EYE_UNDERSTAND_LOGS_DIR",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)
    impl = EyeImpl()
    channels = impl.provide_channels(_noop_handler)
    assert channels[0]._settings.segments_dir == tmp_path / "recordings"


def test_eye_channel_without_handler_stores_none() -> None:
    c = EyeChannel(EyeSettings())
    assert c._message_handler is None


@pytest.mark.asyncio
async def test_start_off_mac_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(channel_module, "_is_mac", lambda: False)
    c = EyeChannel(EyeSettings(), message_handler=_noop_handler)
    await c.start(asyncio.Event())
    assert c._supervisor_task is None
    assert c._understand_task is None


@pytest.mark.asyncio
async def test_start_on_mac_spawns_understand_when_handler_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    monkeypatch.setattr(channel_module, "_is_mac", lambda: True)

    class _FakeSupervisor:
        def __init__(self, _settings: Any) -> None:
            pass

        async def run(self, stop_event: asyncio.Event) -> None:
            await stop_event.wait()

    monkeypatch.setattr(channel_module, "FFmpegSupervisor", _FakeSupervisor)

    settings = EyeSettings(
        segments_dir=tmp_path / "segments",
        understand_state_dir=tmp_path / "state",
        understand_logs_dir=tmp_path / "daily-logs",
        logs_dir=tmp_path / "logs",
        understand_scan_interval_seconds=60.0,
    )
    c = EyeChannel(settings, message_handler=_noop_handler)
    outer_stop = asyncio.Event()
    await c.start(outer_stop)
    try:
        assert c._supervisor_task is not None
        assert c._understand_task is not None
    finally:
        outer_stop.set()
        await c.stop()


@pytest.mark.asyncio
async def test_start_skips_understand_when_auto_understand_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    monkeypatch.setattr(channel_module, "_is_mac", lambda: True)

    class _FakeSupervisor:
        def __init__(self, _settings: Any) -> None:
            pass

        async def run(self, stop_event: asyncio.Event) -> None:
            await stop_event.wait()

    monkeypatch.setattr(channel_module, "FFmpegSupervisor", _FakeSupervisor)

    settings = EyeSettings(
        segments_dir=tmp_path / "segments",
        understand_state_dir=tmp_path / "state",
        understand_logs_dir=tmp_path / "daily-logs",
        logs_dir=tmp_path / "logs",
        auto_understand_enabled=False,
    )
    c = EyeChannel(settings, message_handler=_noop_handler)
    outer_stop = asyncio.Event()
    await c.start(outer_stop)
    try:
        assert c._supervisor_task is not None
        assert c._understand_task is None
    finally:
        outer_stop.set()
        await c.stop()
