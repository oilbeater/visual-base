from __future__ import annotations

from pathlib import Path

import pytest

from bub_eye.settings import EyeSettings, build_settings

_PATH_ENV_VARS = (
    "BUB_EYE_SEGMENTS_DIR",
    "BUB_EYE_LOGS_DIR",
    "BUB_EYE_UNDERSTAND_STATE_DIR",
    "BUB_EYE_UNDERSTAND_LOGS_DIR",
)


def _clear_path_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _PATH_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_build_settings_lays_out_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_path_env(monkeypatch)
    settings = build_settings(tmp_path)
    assert settings.segments_dir == tmp_path / "recordings"
    assert settings.logs_dir == tmp_path / "logs"
    assert settings.understand_state_dir == tmp_path / ".eye-state"
    assert settings.understand_logs_dir == tmp_path / "daily-logs"


def test_segments_env_var_overrides_workspace_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_path_env(monkeypatch)
    monkeypatch.setenv("BUB_EYE_SEGMENTS_DIR", str(tmp_path / "custom-rec"))
    settings = build_settings(tmp_path)
    # env wins for segments_dir; the rest still follow the workspace default
    assert settings.segments_dir == tmp_path / "custom-rec"
    assert settings.logs_dir == tmp_path / "logs"
    assert settings.understand_state_dir == tmp_path / ".eye-state"
    assert settings.understand_logs_dir == tmp_path / "daily-logs"


def test_each_path_env_var_independent_escape_hatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_path_env(monkeypatch)
    monkeypatch.setenv("BUB_EYE_LOGS_DIR", "/tmp/eye-logs-test")
    monkeypatch.setenv("BUB_EYE_UNDERSTAND_STATE_DIR", "/tmp/eye-state-test")
    settings = build_settings(tmp_path)
    assert settings.segments_dir == tmp_path / "recordings"
    assert settings.logs_dir == Path("/tmp/eye-logs-test")
    assert settings.understand_state_dir == Path("/tmp/eye-state-test")
    assert settings.understand_logs_dir == tmp_path / "daily-logs"


def test_bare_eye_settings_keeps_paths_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_path_env(monkeypatch)
    settings = EyeSettings()
    assert settings.segments_dir is None
    assert settings.logs_dir is None
    assert settings.understand_state_dir is None
    assert settings.understand_logs_dir is None
