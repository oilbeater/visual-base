"""State machine + filesystem helpers for the auto-understand worker.

Pure-sync; no asyncio. The worker module drives these with its scan tick.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

Status = Literal["pending", "processing", "done", "idle", "failed"]
_TERMINAL: frozenset[Status] = frozenset({"done", "idle"})

SEGMENT_RE = re.compile(r"^eye_\d{8}_\d{6}\.mp4$")
_IDLE_HEAD_BYTES = 2048


@dataclass
class SegmentState:
    status: Status = "pending"
    attempts: int = 0
    last_error: str | None = None
    updated_at: str = ""

    def mark(
        self,
        status: Status,
        *,
        last_error: str | None = None,
        bump_attempts: bool = False,
    ) -> None:
        self.status = status
        if bump_attempts:
            self.attempts += 1
        self.last_error = last_error
        self.updated_at = now_iso()

    @property
    def terminal(self) -> bool:
        return self.status in _TERMINAL


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def state_path(state_dir: Path, video: Path) -> Path:
    return state_dir / f"{video.stem}.json"


def load_state(state_dir: Path, video: Path) -> SegmentState:
    path = state_path(state_dir, video)
    if not path.exists():
        return SegmentState(updated_at=now_iso())
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return SegmentState(updated_at=now_iso())
    status = raw.get("status", "pending")
    if status not in {"pending", "processing", "done", "idle", "failed"}:
        status = "pending"
    return SegmentState(
        status=status,
        attempts=int(raw.get("attempts", 0)),
        last_error=raw.get("last_error"),
        updated_at=raw.get("updated_at", ""),
    )


def save_state(state_dir: Path, video: Path, state: SegmentState) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_path(state_dir, video)
    tmp = path.with_suffix(".json.tmp")
    payload = json.dumps(asdict(state), ensure_ascii=False, indent=2)
    with tmp.open("w", encoding="utf-8") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def list_finalized_segments(
    segments_dir: Path,
    *,
    now: float,
    grace_seconds: float,
) -> list[Path]:
    """Segments considered safe to process.

    Rules:
      - filename must match ``eye_YYYYMMDD_HHMMSS.mp4``
      - the newest matching file is skipped (ffmpeg is still writing it)
      - remaining files must have ``mtime`` older than ``now - grace_seconds``
    """
    if not segments_dir.is_dir():
        return []
    candidates = sorted(
        (p for p in segments_dir.iterdir() if p.is_file() and SEGMENT_RE.match(p.name)),
        key=lambda p: p.name,
    )
    if len(candidates) < 2:
        return []
    finalized = candidates[:-1]
    threshold = now - grace_seconds
    return [p for p in finalized if p.stat().st_mtime <= threshold]


def md_output_path(video: Path) -> Path:
    """Where `video-activity-log` writes its final markdown by default."""
    return video.with_suffix(".md")


def md_is_idle(md_path: Path) -> bool:
    """Whether ``md_path`` was written by Phase 0's idle preflight."""
    try:
        text = md_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    head = text[:_IDLE_HEAD_BYTES]
    return "#idle" in head or "idle: true" in head


def parse_iso(s: str) -> float | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).timestamp()
    except ValueError:
        return None


def stale_processing(state: SegmentState, *, now: float, timeout: float) -> bool:
    if state.status != "processing":
        return False
    last = parse_iso(state.updated_at)
    if last is None:
        return True
    return (now - last) >= timeout


def retry_due(
    state: SegmentState,
    *,
    now: float,
    retry_after: float,
    max_attempts: int,
) -> bool:
    """Whether a ``failed`` state is eligible for another attempt now."""
    if state.status != "failed":
        return False
    if state.attempts >= max_attempts:
        return False
    last = parse_iso(state.updated_at)
    if last is None:
        return True
    backoff = retry_after * (2 ** max(0, state.attempts - 1))
    return (now - last) >= backoff
