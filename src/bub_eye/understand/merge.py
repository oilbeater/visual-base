"""Merge a per-segment activity log into a daily YYYY-MM-DD.md file.

The `video-activity-log` skill writes a per-segment ``<video>.md`` that looks
roughly like::

    ---
    video: /path/to/eye_20260421_090000.mp4
    date: 2026-04-21
    start: 09:00:12
    end: 09:14:55
    ---

    # 活动日志

    - `09:00:12 - 09:05:00` 在 [[VS Code]] ...
    - `09:05:00 - 09:14:55` 在 [[微信]] ...

    ## 关键实体

    - 人: [[chenkai]]

This module aggregates those per-segment files into a single daily log::

    ---
    date: 2026-04-21
    start: 09:00:12
    end: 18:30:55
    videos:
      - eye_20260421_090000.mp4
      - eye_20260421_091500.mp4
    ---

    # [[2026-04-21]] 活动日志

    - `09:00:12 - 09:05:00` ...
    - `09:05:00 - 09:14:55` ...
    - `09:15:00 - 09:30:00` ...

Bullets are sorted by top-level start time and deduped by the (line, children)
pair, so re-merging the same segment is a no-op. Indented sub-bullets stay
attached to their parent — the skill may emit nested blocks when several
adjacent activities share one URL / article / project, and this module keeps
that hierarchy intact across the daily aggregation. The ``关键实体`` section
is intentionally dropped from the daily view — wikilinks inside each bullet
still connect in Obsidian, and a per-segment roll-up would grow unwieldy.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_BULLET_RE = re.compile(
    r"^- `(\d{1,2}:\d{2}(?::\d{2})?)\s*-\s*(\d{1,2}:\d{2}(?::\d{2})?)`\s*(.*)$"
)
_DAILY_RE = re.compile(r"^eye_(\d{4})(\d{2})(\d{2})_\d{6}\.mp4$")


@dataclass(frozen=True)
class Bullet:
    start_sec: int
    end_sec: int
    line: str
    children: tuple[str, ...] = ()


def daily_log_path(logs_dir: Path, video: Path) -> Path | None:
    """Return ``logs_dir / YYYY-MM-DD.md`` derived from the segment filename.

    Returns ``None`` if the filename doesn't match ``eye_YYYYMMDD_HHMMSS.mp4``.
    """
    m = _DAILY_RE.match(video.name)
    if m is None:
        return None
    year, month, day = m.groups()
    return logs_dir / f"{year}-{month}-{day}.md"


def _parse_hms(s: str) -> int:
    parts = [int(p) for p in s.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    raise ValueError(f"bad time: {s!r}")


def _fmt_hms(sec: int) -> str:
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _extract_frontmatter(md: str) -> tuple[dict[str, str], list[str]]:
    """Return (scalar fields, videos list). Extremely tolerant YAML subset."""
    m = _FRONTMATTER_RE.match(md)
    if m is None:
        return {}, []
    scalars: dict[str, str] = {}
    videos: list[str] = []
    in_videos = False
    for raw in m.group(1).splitlines():
        if raw.startswith("videos:"):
            in_videos = True
            continue
        if in_videos:
            stripped = raw.strip()
            if stripped.startswith("- "):
                videos.append(stripped[2:].strip())
                continue
            if raw and not raw.startswith(" ") and not raw.startswith("\t"):
                in_videos = False
            else:
                continue
        if ":" in raw and not raw.startswith(" "):
            key, _, val = raw.partition(":")
            scalars[key.strip()] = val.strip()
    return scalars, videos


def _body_after_frontmatter(md: str) -> str:
    m = _FRONTMATTER_RE.match(md)
    if m is None:
        return md
    return md[m.end() :]


def _extract_bullets(md: str) -> list[Bullet]:
    bullets: list[Bullet] = []
    body = _body_after_frontmatter(md)
    in_main_section = False

    current_start: int | None = None
    current_end: int | None = None
    current_line: str | None = None
    current_children: list[str] = []

    def flush() -> None:
        nonlocal current_start, current_end, current_line, current_children
        if current_line is not None:
            assert current_start is not None and current_end is not None
            bullets.append(
                Bullet(
                    current_start,
                    current_end,
                    current_line,
                    tuple(current_children),
                )
            )
        current_start = None
        current_end = None
        current_line = None
        current_children = []

    for line in body.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("## "):
            flush()
            in_main_section = False
            continue
        if stripped.startswith("# "):
            flush()
            in_main_section = True
            continue
        if not in_main_section:
            continue
        m = _BULLET_RE.match(line)
        if m is not None:
            flush()
            try:
                start = _parse_hms(m.group(1))
                end = _parse_hms(m.group(2))
            except ValueError:
                continue
            current_start = start
            current_end = end
            current_line = line.rstrip()
            current_children = []
            continue
        if current_line is not None and line and line[0] in (" ", "\t"):
            current_children.append(line.rstrip())
            continue
        flush()
    flush()
    return bullets


def _normalize_videos(videos: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in videos:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def render_daily(
    *,
    date: str,
    bullets: list[Bullet],
    videos: list[str],
) -> str:
    """Render the final daily markdown. Pure function — easy to test."""
    start = _fmt_hms(bullets[0].start_sec) if bullets else ""
    end = _fmt_hms(max(b.end_sec for b in bullets)) if bullets else ""

    lines: list[str] = ["---"]
    if date:
        lines.append(f"date: {date}")
    if start:
        lines.append(f"start: {start}")
    if end:
        lines.append(f"end: {end}")
    lines.append("videos:")
    for v in videos:
        lines.append(f"  - {v}")
    lines.append("---")
    lines.append("")
    lines.append(f"# [[{date}]] 活动日志" if date else "# 活动日志")
    lines.append("")
    for b in bullets:
        lines.append(b.line)
        lines.extend(b.children)
    lines.append("")
    return "\n".join(lines)


def merge_segment(
    *,
    segment_md: str,
    segment_video_basename: str,
    existing_daily_md: str,
) -> str:
    """Return the new daily-md content after folding in ``segment_md``."""
    existing_scalars, existing_videos = _extract_frontmatter(existing_daily_md)
    segment_scalars, _ = _extract_frontmatter(segment_md)

    date = segment_scalars.get("date") or existing_scalars.get("date") or ""

    combined = _extract_bullets(existing_daily_md) + _extract_bullets(segment_md)
    seen: set[tuple[str, tuple[str, ...]]] = set()
    deduped: list[Bullet] = []
    for b in combined:
        key = (b.line, b.children)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(b)
    deduped.sort(key=lambda b: (b.start_sec, b.end_sec, b.line))

    videos = _normalize_videos([*existing_videos, segment_video_basename])

    return render_daily(date=date, bullets=deduped, videos=videos)


def merge_segment_file(
    segment_md_path: Path,
    segment_video: Path,
    daily_md_path: Path,
) -> None:
    """Read ``segment_md_path``, merge into ``daily_md_path`` atomically."""
    daily_md_path.parent.mkdir(parents=True, exist_ok=True)
    segment_text = segment_md_path.read_text(encoding="utf-8")
    existing = (
        daily_md_path.read_text(encoding="utf-8") if daily_md_path.exists() else ""
    )
    merged = merge_segment(
        segment_md=segment_text,
        segment_video_basename=segment_video.name,
        existing_daily_md=existing,
    )
    tmp = daily_md_path.with_suffix(daily_md_path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.write(merged)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, daily_md_path)
