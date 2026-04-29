from __future__ import annotations

from pathlib import Path

import pytest

import visual_base.settings as settings_module


def _clear_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VISUAL_BASE_WORKSPACE", raising=False)


def test_resolve_workspace_falls_back_to_default_project_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("BUB_HOME", str(tmp_path))
    # toml file does not exist at <bub_home>/visual-base/config.toml
    monkeypatch.setattr(
        settings_module,
        "config_file_path",
        lambda: tmp_path / "visual-base" / "config.toml",
    )
    monkeypatch.setattr(
        settings_module,
        "default_project_dir",
        lambda: tmp_path / "visual-base" / "default",
    )

    class _Reload(settings_module.VisualBaseSettings):
        model_config = {
            **settings_module.VisualBaseSettings.model_config,
            "toml_file": tmp_path / "visual-base" / "config.toml",
        }

    resolved = _Reload().resolve_workspace()
    assert resolved == (tmp_path / "visual-base" / "default").resolve()


def test_env_overrides_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / "visual-base"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "config.toml"
    config_file.write_text(f'workspace = "{tmp_path / "from-toml"}"\n')

    monkeypatch.setenv("VISUAL_BASE_WORKSPACE", str(tmp_path / "from-env"))

    class _Reload(settings_module.VisualBaseSettings):
        model_config = {
            **settings_module.VisualBaseSettings.model_config,
            "toml_file": config_file,
        }

    resolved = _Reload().resolve_workspace()
    assert resolved == (tmp_path / "from-env").resolve()


def test_toml_used_when_env_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_settings_env(monkeypatch)
    config_dir = tmp_path / "visual-base"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "config.toml"
    config_file.write_text(f'workspace = "{tmp_path / "from-toml"}"\n')

    class _Reload(settings_module.VisualBaseSettings):
        model_config = {
            **settings_module.VisualBaseSettings.model_config,
            "toml_file": config_file,
        }

    resolved = _Reload().resolve_workspace()
    assert resolved == (tmp_path / "from-toml").resolve()


def test_workspace_with_tilde_is_expanded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("VISUAL_BASE_WORKSPACE", "~/somewhere/under/home")

    class _Reload(settings_module.VisualBaseSettings):
        model_config = {
            **settings_module.VisualBaseSettings.model_config,
            "toml_file": tmp_path / "no-such-config.toml",
        }

    resolved = _Reload().resolve_workspace()
    assert "~" not in str(resolved)
    assert resolved.is_absolute()
