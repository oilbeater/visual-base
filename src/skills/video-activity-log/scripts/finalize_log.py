#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Shift relative time ranges in a video-activity-log draft to absolute wall-clock times.

The LLM writes a draft where every `MM:SS - MM:SS` (or `HH:MM:SS - HH:MM:SS`) backtick span is
relative to the video start. This script:

  1. Parses the wall-clock start from the video filename (`eye_YYYYMMDD_HHMMSS.<ext>`) — or takes
     `--base-time` as an override.
  2. Rewrites every time-range span in the draft to absolute `HH:MM:SS`.
  3. Fills (or replaces) the YAML frontmatter with `video`, `date`, `start`, `end`.
  4. Validates bullet coverage and duration (warn-only; see --no-validate to skip).
  5. Writes the finalized Markdown to `--output` (default: `<video>.md`).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from _common import fmt_abs, get_video_duration, parse_video_start

TIME_RANGE_RE = re.compile(r"`(\d{1,2}:\d{2}(?::\d{2})?)\s*-\s*(\d{1,2}:\d{2}(?::\d{2})?)`")
FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)


@dataclass
class Span:
    start: datetime
    end: datetime
    line: str  # the full draft line containing this span (already shifted to absolute)
    is_top_level: bool  # True iff the line starts with "- " (not an indented sub-bullet)


def parse_relative(t: str) -> timedelta:
    parts = [int(p) for p in t.split(":")]
    if len(parts) == 2:
        return timedelta(minutes=parts[0], seconds=parts[1])
    if len(parts) == 3:
        return timedelta(hours=parts[0], minutes=parts[1], seconds=parts[2])
    raise ValueError(f"bad time: {t!r}")


def shift_ranges(draft: str, base: datetime) -> tuple[str, list[Span]]:
    spans: list[Span] = []
    out_lines: list[str] = []

    for line in draft.splitlines(keepends=False):
        line_spans_start: list[datetime] = []
        line_spans_end: list[datetime] = []

        def repl(m: re.Match[str]) -> str:
            start_abs = base + parse_relative(m.group(1))
            end_abs = base + parse_relative(m.group(2))
            line_spans_start.append(start_abs)
            line_spans_end.append(end_abs)
            return f"`{fmt_abs(start_abs)} - {fmt_abs(end_abs)}`"

        shifted_line = TIME_RANGE_RE.sub(repl, line)
        out_lines.append(shifted_line)
        is_top_level = shifted_line.startswith("- ")
        for s, e in zip(line_spans_start, line_spans_end):
            spans.append(
                Span(
                    start=s,
                    end=e,
                    line=shifted_line.strip(),
                    is_top_level=is_top_level,
                )
            )

    shifted = "\n".join(out_lines)
    if draft.endswith("\n"):
        shifted += "\n"
    return shifted, spans


def apply_frontmatter(
    doc: str, video: Path, spans: list[Span], base: datetime
) -> str:
    first = min((s.start for s in spans), default=None)
    last = max((s.end for s in spans), default=None)
    date = (first or base).date().isoformat()
    start = fmt_abs(first) if first else fmt_abs(base)
    end = fmt_abs(last) if last else ""
    fm = (
        "---\n"
        f"video: {video}\n"
        f"date: {date}\n"
        f"start: {start}\n"
        f"end: {end}\n"
        "---\n"
    )
    if FRONTMATTER_RE.match(doc):
        return FRONTMATTER_RE.sub(fm, doc, count=1)
    return fm + "\n" + doc.lstrip()


@dataclass
class Issue:
    kind: str  # "gap" | "short" | "head" | "tail"
    message: str


def validate_bullets(
    spans: list[Span],
    base: datetime,
    video_duration: float | None,
    min_bullet_seconds: int,
    max_gap_seconds: int,
) -> list[Issue]:
    """Return a list of quality issues, in reading order. Non-blocking.

    Only top-level bullets are validated — indented sub-bullets belong to a
    parent that owns the full span, so they may legitimately be short or
    have gaps between siblings.
    """
    issues: list[Issue] = []
    top_level = [s for s in spans if s.is_top_level]
    if not top_level:
        return issues

    ordered = sorted(top_level, key=lambda s: s.start)

    # head gap
    head_gap = (ordered[0].start - base).total_seconds()
    if head_gap > max_gap_seconds:
        issues.append(
            Issue(
                "head",
                f"first bullet starts {int(head_gap)}s after video start (>{max_gap_seconds}s): "
                f"{ordered[0].line}",
            )
        )

    # inter-bullet gaps and short bullets
    for i, span in enumerate(ordered):
        dur = (span.end - span.start).total_seconds()
        is_last = i == len(ordered) - 1
        if dur < min_bullet_seconds and not is_last:
            issues.append(
                Issue(
                    "short",
                    f"bullet duration {int(dur)}s < {min_bullet_seconds}s: {span.line}",
                )
            )
        if not is_last:
            gap = (ordered[i + 1].start - span.end).total_seconds()
            if gap > max_gap_seconds:
                issues.append(
                    Issue(
                        "gap",
                        f"{int(gap)}s gap (>{max_gap_seconds}s) after: {span.line}",
                    )
                )

    # tail gap (needs video duration)
    if video_duration is not None:
        tail_span_end = (ordered[-1].end - base).total_seconds()
        tail_gap = video_duration - tail_span_end
        if tail_gap > max_gap_seconds:
            issues.append(
                Issue(
                    "tail",
                    f"last bullet ends {int(tail_gap)}s before video end (>{max_gap_seconds}s): "
                    f"{ordered[-1].line}",
                )
            )

    return issues


def report_issues(issues: list[Issue]) -> None:
    if not issues:
        return
    print("", file=sys.stderr)
    for issue in issues:
        print(f"  [{issue.kind}] {issue.message}", file=sys.stderr)
    print(
        f"validation: {len(issues)} issue(s) found — review and consider re-prompting",
        file=sys.stderr,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--video", type=Path, required=True, help="source video path")
    ap.add_argument("--draft", type=Path, required=True, help="draft markdown with relative times")
    ap.add_argument("--output", type=Path, help="output path (default: sibling of the video, .md)")
    ap.add_argument("--base-time", help="override wall-clock start (ISO-8601, e.g. 2026-04-17T13:00:00)")
    ap.add_argument("--min-bullet-seconds", type=int, default=30, help="minimum bullet duration for validation (default: 30)")
    ap.add_argument("--max-gap-seconds", type=int, default=60, help="maximum allowed gap between bullets / at head or tail (default: 60)")
    ap.add_argument("--no-validate", action="store_true", help="skip post-shift validation")
    args = ap.parse_args()

    base = datetime.fromisoformat(args.base_time) if args.base_time else parse_video_start(args.video)
    draft = args.draft.read_text(encoding="utf-8")
    shifted, spans = shift_ranges(draft, base)
    final = apply_frontmatter(shifted, args.video.resolve(), spans, base)

    out = args.output or args.video.with_suffix(".md")
    out.write_text(final, encoding="utf-8")

    print(f"wrote {out}", file=sys.stderr)
    if spans:
        first = min(s.start for s in spans)
        last = max(s.end for s in spans)
        print(f"span: {fmt_abs(first)} - {fmt_abs(last)}", file=sys.stderr)
    else:
        print("warning: no time ranges found in draft", file=sys.stderr)

    if not args.no_validate and spans:
        duration = get_video_duration(args.video)
        issues = validate_bullets(
            spans,
            base,
            duration,
            min_bullet_seconds=args.min_bullet_seconds,
            max_gap_seconds=args.max_gap_seconds,
        )
        report_issues(issues)


if __name__ == "__main__":
    main()
