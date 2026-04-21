from __future__ import annotations

import subprocess
import sys
import types

import pytest

from bub_eye import ffmpeg
from bub_eye.ffmpeg import _ensure_imageio_ffmpeg_installed as _real_ensure


@pytest.fixture(autouse=True)
def _reset_install_flag() -> None:
    ffmpeg._imageio_ffmpeg_install_checked = False
    yield
    ffmpeg._imageio_ffmpeg_install_checked = False


def _install_fake_imageio_ffmpeg(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate that `import imageio_ffmpeg` succeeds."""
    module = types.ModuleType("imageio_ffmpeg")
    module.get_ffmpeg_exe = lambda: "/fake/ffmpeg"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "imageio_ffmpeg", module)


def _force_import_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate `import imageio_ffmpeg` raising ImportError."""
    monkeypatch.delitem(sys.modules, "imageio_ffmpeg", raising=False)
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__  # noqa: E501

    def faked_import(name, *args, **kwargs):
        if name == "imageio_ffmpeg":
            raise ImportError("simulated missing imageio_ffmpeg")
        return real_import(name, *args, **kwargs)

    import builtins
    monkeypatch.setattr(builtins, "__import__", faked_import)


def test_skips_install_when_package_present(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_imageio_ffmpeg(monkeypatch)

    def explode(*_a: object, **_k: object) -> None:
        raise AssertionError("subprocess.run should not run when the package is present")

    monkeypatch.setattr(ffmpeg.subprocess, "run", explode)

    _real_ensure()
    assert ffmpeg._imageio_ffmpeg_install_checked is True


def test_runs_uv_pip_install_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    attempts: list[int] = []

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append(cmd)
        assert kwargs.get("check") is True
        # After install, make the next import succeed.
        _install_fake_imageio_ffmpeg(monkeypatch)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(ffmpeg.subprocess, "run", fake_run)

    # Force the first import to fail; the post-install import should succeed
    # because fake_run installed the fake module into sys.modules.
    import builtins
    real_import = builtins.__import__

    def import_that_fails_until_installed(name, *args, **kwargs):
        if name == "imageio_ffmpeg" and name not in sys.modules:
            attempts.append(1)
            raise ImportError("simulated missing imageio_ffmpeg")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_that_fails_until_installed)

    _real_ensure()

    assert calls == [
        ["uv", "pip", "install", "--python", sys.executable, ffmpeg.IMAGEIO_FFMPEG_SPEC]
    ]
    assert ffmpeg._imageio_ffmpeg_install_checked is True
    assert attempts == [1]  # only one pre-install probe


def test_only_probes_once_per_process(monkeypatch: pytest.MonkeyPatch) -> None:
    probes: list[int] = []

    import builtins
    real_import = builtins.__import__

    def counting_import(name, *args, **kwargs):
        if name == "imageio_ffmpeg":
            probes.append(1)
            _install_fake_imageio_ffmpeg(monkeypatch)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", counting_import)

    _real_ensure()
    _real_ensure()
    _real_ensure()

    assert len(probes) == 1


def test_raises_when_uv_binary_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_import_failure(monkeypatch)

    def fake_run(*_a: object, **_k: object) -> None:
        raise FileNotFoundError("uv")

    monkeypatch.setattr(ffmpeg.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="uv.*not on PATH"):
        _real_ensure()
    assert ffmpeg._imageio_ffmpeg_install_checked is False


def test_raises_when_install_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_import_failure(monkeypatch)

    def fake_run(cmd: list[str], **_k: object) -> None:
        raise subprocess.CalledProcessError(returncode=11, cmd=cmd)

    monkeypatch.setattr(ffmpeg.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="exit code 11"):
        _real_ensure()


def test_raises_when_import_still_fails_after_install(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_import_failure(monkeypatch)
    monkeypatch.setattr(
        ffmpeg.subprocess,
        "run",
        lambda cmd, **_k: subprocess.CompletedProcess(cmd, 0),
    )

    with pytest.raises(RuntimeError, match="still cannot be imported"):
        _real_ensure()
    assert ffmpeg._imageio_ffmpeg_install_checked is False
