from __future__ import annotations

import pytest

from bub_kimi import plugin


@pytest.fixture(autouse=True)
def _stub_kimi_install(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent tests from running a real `uv tool install kimi-cli`."""
    monkeypatch.setattr(plugin, "_ensure_kimi_installed", lambda: None)
