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

    model_config = SettingsConfigDict(
        env_prefix="BUB_EYE_", extra="ignore", env_file=".env"
    )

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
    scale_height: int = Field(
        default=720, description="Output height in px; -1 disables scaling."
    )
    segments_dir: Path = Field(default_factory=lambda: _bub_home() / "eye" / "segments")
    display_index: int | None = None

    auto_understand_enabled: bool = Field(
        default=True,
        description=(
            "Whether to auto-trigger the `video-activity-log` skill on each finalized segment. "
            "Requires `enabled` and an Intel Mac host."
        ),
    )
    understand_state_dir: Path = Field(
        default_factory=lambda: _bub_home() / "eye" / "state",
        description="Directory holding one JSON per segment tracking understand status.",
    )
    understand_logs_dir: Path = Field(
        default_factory=lambda: _bub_home() / "eye" / "logs",
        description=(
            "Directory receiving daily activity logs named `YYYY-MM-DD.md`. "
            "One file per day, aggregating bullets across all segments recorded on that date."
        ),
    )
    understand_scan_interval_seconds: float = Field(
        default=30.0,
        gt=0.0,
        description="Seconds between scans of the segments directory.",
    )
    understand_finalize_grace_seconds: float = Field(
        default=10.0,
        ge=0.0,
        description="A non-newest segment must be older than this (mtime) before it is considered finalized.",
    )
    understand_processing_timeout_seconds: float = Field(
        default=1200.0,
        gt=0.0,
        description="If a segment stays in `processing` longer than this with no `.md` output, mark it failed.",
    )
    understand_retry_after_seconds: float = Field(
        default=3600.0,
        ge=0.0,
        description="Base backoff after a failed attempt; effective wait = base * 2^(attempts-1).",
    )
    understand_max_attempts: int = Field(
        default=3,
        ge=1,
        description="After this many failed attempts the segment is abandoned (terminal `failed`).",
    )
    understand_trigger_phrase: str = Field(
        default=(
            "请对录屏文件 {video} 写一份活动日志（调用 video-activity-log 技能，总结这段录屏）。"
            "按 Phase 0 / Phase 1 / Phase 2 执行，输出路径使用技能默认（<video>.md）。"
            "完成后回复最终 md 的绝对路径。"
        ),
        description="Template used as the injected turn's content. `{video}` is replaced with the segment's absolute path.",
    )
