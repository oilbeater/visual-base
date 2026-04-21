from __future__ import annotations

import subprocess

import pytest

from bub_kimi import plugin
from bub_kimi.plugin import _ensure_kimi_installed as _real_ensure_kimi_installed


@pytest.fixture(autouse=True)
def _reset_install_flag() -> None:
    plugin._kimi_install_checked = False
    yield
    plugin._kimi_install_checked = False


def test_skips_install_when_kimi_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plugin.shutil, "which", lambda _name: "/usr/local/bin/kimi")

    def explode(*_a: object, **_k: object) -> None:
        raise AssertionError("subprocess.run should not be called when kimi is present")

    monkeypatch.setattr(plugin.subprocess, "run", explode)

    _real_ensure_kimi_installed()
    assert plugin._kimi_install_checked is True


def test_runs_uv_tool_install_when_kimi_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    which_calls: list[str] = []

    def fake_which(name: str) -> str | None:
        which_calls.append(name)
        return "/home/u/.local/bin/kimi" if len(which_calls) > 1 else None

    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append(cmd)
        assert kwargs.get("check") is True
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(plugin.shutil, "which", fake_which)
    monkeypatch.setattr(plugin.subprocess, "run", fake_run)

    _real_ensure_kimi_installed()

    assert calls == [
        ["uv", "tool", "install", "--python", plugin.KIMI_CLI_PYTHON, plugin.KIMI_CLI_PACKAGE]
    ]
    assert plugin._kimi_install_checked is True


def test_only_probes_once_per_process(monkeypatch: pytest.MonkeyPatch) -> None:
    probes: list[str] = []
    monkeypatch.setattr(plugin.shutil, "which", lambda name: probes.append(name) or "/bin/kimi")

    _real_ensure_kimi_installed()
    _real_ensure_kimi_installed()
    _real_ensure_kimi_installed()

    assert len(probes) == 1


def test_raises_when_uv_binary_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plugin.shutil, "which", lambda _name: None)

    def fake_run(*_a: object, **_k: object) -> None:
        raise FileNotFoundError("uv")

    monkeypatch.setattr(plugin.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="uv.*not on PATH"):
        _real_ensure_kimi_installed()
    assert plugin._kimi_install_checked is False


def test_raises_when_install_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plugin.shutil, "which", lambda _name: None)

    def fake_run(cmd: list[str], **_k: object) -> None:
        raise subprocess.CalledProcessError(returncode=17, cmd=cmd)

    monkeypatch.setattr(plugin.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="exit code 17"):
        _real_ensure_kimi_installed()


def test_raises_when_path_still_missing_after_install(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plugin.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        plugin.subprocess,
        "run",
        lambda cmd, **_k: subprocess.CompletedProcess(cmd, 0),
    )

    with pytest.raises(RuntimeError, match="not on PATH"):
        _real_ensure_kimi_installed()
    assert plugin._kimi_install_checked is False
