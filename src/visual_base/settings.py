"""Distribution-level settings (workspace default, etc.).

These are *not* the same as ``bub_eye.EyeSettings`` — those govern the
recorder. This class governs the visual-base CLI itself: where to land
when the user doesn't pass ``--workspace``.

Resolution order, highest-first:

1. ``VISUAL_BASE_WORKSPACE`` env var
2. ``workspace = "..."`` in ``$BUB_HOME/visual-base/config.toml``
3. ``None`` — caller falls back to ``$BUB_HOME/visual-base/default``
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)


def bub_home() -> Path:
    """Root for visual-base's own config + default project directory."""
    return Path(os.environ.get("BUB_HOME", str(Path.home() / ".bub")))


def config_file_path() -> Path:
    return bub_home() / "visual-base" / "config.toml"


def default_project_dir() -> Path:
    return bub_home() / "visual-base" / "default"


class VisualBaseSettings(BaseSettings):
    """User-tunable defaults for the visual-base CLI."""

    model_config = SettingsConfigDict(
        env_prefix="VISUAL_BASE_",
        extra="ignore",
        toml_file=config_file_path(),
    )

    workspace: Path | None = None

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            TomlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )

    def resolve_workspace(self) -> Path:
        """Final, expanded, resolved workspace path. Falls back to the
        default project dir if neither env nor config provided one.
        """
        chosen = self.workspace if self.workspace is not None else default_project_dir()
        return Path(chosen).expanduser().resolve()
