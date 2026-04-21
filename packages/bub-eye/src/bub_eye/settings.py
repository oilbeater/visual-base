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
    storage under `$BUB_HOME/eye/` so the segments stay next to the rest of a
    Bub installation.
    """

    model_config = SettingsConfigDict(env_prefix="BUB_EYE_", extra="ignore", env_file=".env")

    enabled: bool = True
    ffmpeg: str | None = None
    sample_interval_seconds: float = Field(
        default=1.0,
        gt=0.0,
        description=(
            "How many seconds between consecutive screen samples that enter the video. "
            "Typical values: 1 (one frame per second), 5 (one every 5 s), 30 (every half minute)."
        ),
    )
    segment_seconds: int = Field(default=900, ge=5, le=3600)
    keyframe_interval_seconds: int = Field(
        default=60,
        ge=1,
        description=(
            "Forced keyframe interval. Controls the number of seekable points inside a "
            "segment (segment_seconds / keyframe_interval_seconds) and bounds P-frame "
            "drift; smaller = better random access, slightly larger files."
        ),
    )
    codec: str = Field(
        default="hevc_videotoolbox",
        description=(
            "Video codec. Default uses Apple's hardware HEVC encoder for near-zero CPU. "
            "Use `libx264` as a software fallback if videotoolbox is unavailable."
        ),
    )
    bitrate: str = Field(
        default="1200k",
        description="Target bitrate for hardware/bitrate-based codecs (ignored by libx264).",
    )
    crf: int = Field(
        default=28,
        ge=0,
        le=51,
        description="Constant Rate Factor for libx264 (ignored by hardware codecs).",
    )
    scale_height: int = Field(default=720, description="Output height in px; -1 disables scaling.")
    segments_dir: Path = Field(default_factory=lambda: _bub_home() / "eye" / "segments")
    display_index: int | None = None
