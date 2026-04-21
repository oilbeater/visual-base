from __future__ import annotations

import pytest

from bub_eye import ffmpeg as bub_eye_ffmpeg
from bub_kimi import plugin as bub_kimi_plugin


@pytest.fixture(autouse=True)
def _stub_kimi_install(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent tests from running a real `uv tool install kimi-cli`."""
    monkeypatch.setattr(bub_kimi_plugin, "_ensure_kimi_installed", lambda: None)


@pytest.fixture(autouse=True)
def _stub_imageio_ffmpeg_install(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent tests from running a real `uv pip install imageio-ffmpeg`."""
    monkeypatch.setattr(bub_eye_ffmpeg, "_ensure_imageio_ffmpeg_installed", lambda: None)
