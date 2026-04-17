from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _bub_home() -> Path:
    return Path(os.environ.get("BUB_HOME", str(Path.home() / ".bub")))


class EyeSettings(BaseSettings):
    """Configuration for the bub-eye screen recorder.

    All fields are driven by `BUB_EYE_*` environment variables. Defaults root
    storage under `$BUB_HOME/eye/` so the visual tape and segments stay next to
    the rest of a Bub installation but never mix with conversation tapes.
    """

    model_config = SettingsConfigDict(env_prefix="BUB_EYE_", extra="ignore", env_file=".env")

    enabled: bool = True
    ffmpeg: str | None = None
    framerate: int = Field(default=1, ge=1, le=30)
    segment_seconds: int = Field(default=60, ge=5, le=3600)
    crf: int = Field(default=28, ge=0, le=51)
    scale_height: int = Field(default=720, description="Output height in px; -1 disables scaling.")
    segments_dir: Path = Field(default_factory=lambda: _bub_home() / "eye" / "segments")
    tape_dir: Path = Field(default_factory=lambda: _bub_home() / "eye" / "tapes")
    display_index: int | None = None
