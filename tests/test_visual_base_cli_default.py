from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from visual_base import cli as cli_module


def test_no_workspace_flag_chdirs_to_default_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUB_HOME", str(tmp_path))
    monkeypatch.delenv("VISUAL_BASE_WORKSPACE", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["visual-base", "chat"])
    expected = (tmp_path / "visual-base" / "default").resolve()

    # Patch the lazy-imported app symbol so .main() doesn't actually boot bub.
    with patch.dict("sys.modules", {"bub.__main__": _StubBubMain()}):
        cli_module.main()

    assert Path(os.getcwd()).resolve() == expected
    assert expected.is_dir()


def test_explicit_workspace_long_flag_skips_chdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUB_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    starting_cwd = Path(os.getcwd()).resolve()
    monkeypatch.setattr(
        "sys.argv", ["visual-base", "--workspace", "/some/explicit/path", "chat"]
    )

    with patch.dict("sys.modules", {"bub.__main__": _StubBubMain()}):
        cli_module.main()

    assert Path(os.getcwd()).resolve() == starting_cwd


def test_explicit_workspace_short_flag_skips_chdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUB_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    starting_cwd = Path(os.getcwd()).resolve()
    monkeypatch.setattr("sys.argv", ["visual-base", "-w", "/some/path", "chat"])

    with patch.dict("sys.modules", {"bub.__main__": _StubBubMain()}):
        cli_module.main()

    assert Path(os.getcwd()).resolve() == starting_cwd


def test_env_var_overrides_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUB_HOME", str(tmp_path))
    target = tmp_path / "from-env"
    monkeypatch.setenv("VISUAL_BASE_WORKSPACE", str(target))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["visual-base", "chat"])

    with patch.dict("sys.modules", {"bub.__main__": _StubBubMain()}):
        cli_module.main()

    assert Path(os.getcwd()).resolve() == target.resolve()


class _StubBubMain:
    """Stand-in for ``bub.__main__`` so ``cli.main`` can ``import`` and call
    ``app()`` without booting the real framework or running typer."""

    def app(self) -> None:
        return None
