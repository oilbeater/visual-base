"""Visual tape writer: one TapeEntry.event per closed segment."""

from __future__ import annotations

import hashlib
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path

from bub.builtin.store import FileTapeStore
from loguru import logger
from republic import TapeEntry


def _host_hash() -> str:
    return hashlib.md5(
        socket.gethostname().encode("utf-8"), usedforsecurity=False
    ).hexdigest()[:16]


def visual_tape_name() -> str:
    """Tape identifier used for the visual stream.

    The single `__` matches FileTapeStore.list_tapes' filter (see bub/builtin/store.py:228),
    so the tape shows up in tooling that lists available tapes.
    """
    return f"visual__{_host_hash()}"


def _parse_segment_start(path: Path) -> datetime | None:
    """Extract the UTC datetime ffmpeg stamped into the filename.

    Relies on the supervisor passing `TZ=UTC` when launching ffmpeg so
    `-strftime 1` emits UTC timestamps.
    """
    stem = path.stem
    parts = stem.split("_")
    if len(parts) != 3 or parts[0] != "eye":
        return None
    try:
        return datetime.strptime(parts[1] + parts[2], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None


class VisualWriter:
    """Appends `vision/segment` events to the visual tape.

    One event per closed segment. No perceptual-hash dedup, no cleanup —
    that's deliberate for v1.
    """

    def __init__(
        self,
        tape_dir: Path,
        segment_seconds: int,
        run_id: str,
        host: str,
    ) -> None:
        tape_dir.mkdir(parents=True, exist_ok=True)
        self._store = FileTapeStore(directory=tape_dir)
        self._tape = visual_tape_name()
        self._segment_seconds = segment_seconds
        self._run_id = run_id
        self._host = host

    def on_new_segment(self, path: Path) -> None:
        try:
            stat = path.stat()
        except FileNotFoundError:
            logger.warning("bub-eye: segment vanished before write: {}", path)
            return

        start = _parse_segment_start(path)
        end = start + timedelta(seconds=self._segment_seconds) if start else None

        data: dict[str, object] = {
            "path": str(path),
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
            "duration_s": float(self._segment_seconds),
            "size_bytes": stat.st_size,
        }
        entry = TapeEntry.event(
            name="vision/segment",
            data=data,
            run_id=self._run_id,
            host=self._host,
        )
        self._store.append(self._tape, entry)
        logger.debug(
            "bub-eye: appended visual segment entry ({} bytes): {}",
            stat.st_size,
            path.name,
        )
