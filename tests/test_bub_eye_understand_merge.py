from __future__ import annotations

from pathlib import Path

from bub_eye.understand.merge import daily_log_path, merge_segment, merge_segment_file


_SEG_A = """---
video: /path/eye_20260421_090000.mp4
date: 2026-04-21
start: 09:00:00
end: 09:14:55
---

# 活动日志

- `09:00:00 - 09:04:58` 在 [[VS Code]] 编辑 [[bub-eye]]
- `09:05:00 - 09:14:55` 在 [[微信]] 和 [[chenkai]] 对话

## 关键实体

- 人: [[chenkai]]
- 应用: [[VS Code]], [[微信]]
"""

_SEG_B = """---
video: /path/eye_20260421_091500.mp4
date: 2026-04-21
start: 09:15:00
end: 09:30:00
---

# 活动日志

- `09:15:00 - 09:30:00` 在 [[trac.ffmpeg.org]] 查阅 [[HEVC]] 关键帧

## 关键实体

- 站点: [[trac.ffmpeg.org]]
"""


def test_daily_log_path_matches_eye_filename(tmp_path: Path) -> None:
    assert (
        daily_log_path(tmp_path, Path("eye_20260421_100000.mp4"))
        == tmp_path / "2026-04-21.md"
    )


def test_daily_log_path_rejects_unexpected_filename(tmp_path: Path) -> None:
    assert daily_log_path(tmp_path, Path("stray.mp4")) is None
    assert daily_log_path(tmp_path, Path("eye_2026-04-21_100000.mp4")) is None


def test_merge_into_empty_daily() -> None:
    out = merge_segment(
        segment_md=_SEG_A,
        segment_video_basename="eye_20260421_090000.mp4",
        existing_daily_md="",
    )
    assert "# [[2026-04-21]] 活动日志" in out
    assert "videos:" in out
    assert "  - eye_20260421_090000.mp4" in out
    assert "- `09:00:00 - 09:04:58` 在 [[VS Code]]" in out
    assert "- `09:05:00 - 09:14:55` 在 [[微信]]" in out
    # Entity roll-up is dropped intentionally.
    assert "## 关键实体" not in out
    assert "date: 2026-04-21" in out
    assert "start: 09:00:00" in out
    assert "end: 09:14:55" in out


def test_merge_two_segments_aggregates_and_sorts() -> None:
    step1 = merge_segment(
        segment_md=_SEG_A,
        segment_video_basename="eye_20260421_090000.mp4",
        existing_daily_md="",
    )
    step2 = merge_segment(
        segment_md=_SEG_B,
        segment_video_basename="eye_20260421_091500.mp4",
        existing_daily_md=step1,
    )
    assert step2.count("  - eye_20260421_") == 2
    assert "  - eye_20260421_090000.mp4" in step2
    assert "  - eye_20260421_091500.mp4" in step2
    assert "start: 09:00:00" in step2
    assert "end: 09:30:00" in step2

    # Bullet order is chronological.
    idx_a = step2.index("- `09:00:00 - 09:04:58`")
    idx_b = step2.index("- `09:05:00 - 09:14:55`")
    idx_c = step2.index("- `09:15:00 - 09:30:00`")
    assert idx_a < idx_b < idx_c


def test_merge_out_of_order_segments_still_sorts_correctly() -> None:
    step1 = merge_segment(
        segment_md=_SEG_B,  # later timestamp first
        segment_video_basename="eye_20260421_091500.mp4",
        existing_daily_md="",
    )
    step2 = merge_segment(
        segment_md=_SEG_A,
        segment_video_basename="eye_20260421_090000.mp4",
        existing_daily_md=step1,
    )
    idx_early = step2.index("- `09:00:00 - 09:04:58`")
    idx_late = step2.index("- `09:15:00 - 09:30:00`")
    assert idx_early < idx_late
    # videos list preserves insertion order — early segment appended second.
    videos_block = step2.split("videos:\n")[1].split("---", 1)[0]
    assert videos_block.index("eye_20260421_091500") < videos_block.index(
        "eye_20260421_090000"
    )


def test_merge_is_idempotent() -> None:
    once = merge_segment(
        segment_md=_SEG_A,
        segment_video_basename="eye_20260421_090000.mp4",
        existing_daily_md="",
    )
    twice = merge_segment(
        segment_md=_SEG_A,
        segment_video_basename="eye_20260421_090000.mp4",
        existing_daily_md=once,
    )
    assert twice == once


def test_merge_file_writes_and_is_atomic(tmp_path: Path) -> None:
    segment_md = tmp_path / "eye_20260421_090000.md"
    segment_md.write_text(_SEG_A)
    video = tmp_path / "eye_20260421_090000.mp4"
    daily = tmp_path / "logs" / "2026-04-21.md"

    merge_segment_file(segment_md, video, daily)

    assert daily.exists()
    assert not (tmp_path / "logs" / "2026-04-21.md.tmp").exists()
    body = daily.read_text(encoding="utf-8")
    assert "- `09:00:00 - 09:04:58`" in body


def test_merge_tolerates_malformed_segment() -> None:
    # Non-bullet content, missing frontmatter — should produce an empty daily
    # rather than crashing.
    out = merge_segment(
        segment_md="not a real log, just text",
        segment_video_basename="eye_20260421_090000.mp4",
        existing_daily_md="",
    )
    assert "  - eye_20260421_090000.mp4" in out
    assert "- `" not in out  # no bullets


_SEG_NESTED = """---
video: /path/eye_20260421_142800.mp4
date: 2026-04-21
start: 14:28:11
end: 14:38:39
---

# 活动日志

- `14:28:11 - 14:38:39` 在 [[x.com]] 阅读 [[Garry Tan]] "Thin Harness, Fat Skills"
    - `14:28:11 - 14:33:09` 通读原文，期间在 [[VS Code]] 查看 [[visual-base]] 代码
    - `14:33:11 - 14:35:46` 浏览关于 [[AI agent]] 的论述
    - `14:35:46 - 14:38:06` 用 [[Raycast]] Quick AI 翻译
    - `14:38:11 - 14:38:39` 通过 [[Kimi]] 浮窗复核翻译

## 关键实体

- 人: [[Garry Tan]]
"""


def test_merge_preserves_indented_sub_bullets() -> None:
    out = merge_segment(
        segment_md=_SEG_NESTED,
        segment_video_basename="eye_20260421_142800.mp4",
        existing_daily_md="",
    )
    assert "- `14:28:11 - 14:38:39` 在 [[x.com]]" in out
    assert "    - `14:28:11 - 14:33:09` 通读原文" in out
    assert "    - `14:33:11 - 14:35:46` 浏览关于 [[AI agent]]" in out
    assert "    - `14:35:46 - 14:38:06` 用 [[Raycast]]" in out
    assert "    - `14:38:11 - 14:38:39` 通过 [[Kimi]]" in out
    # Sub-bullets sit under their parent, not promoted to top-level order.
    parent_idx = out.index("- `14:28:11 - 14:38:39`")
    first_sub_idx = out.index("    - `14:28:11 - 14:33:09`")
    last_sub_idx = out.index("    - `14:38:11 - 14:38:39`")
    assert parent_idx < first_sub_idx < last_sub_idx


def test_merge_with_nested_bullets_is_idempotent() -> None:
    once = merge_segment(
        segment_md=_SEG_NESTED,
        segment_video_basename="eye_20260421_142800.mp4",
        existing_daily_md="",
    )
    twice = merge_segment(
        segment_md=_SEG_NESTED,
        segment_video_basename="eye_20260421_142800.mp4",
        existing_daily_md=once,
    )
    assert twice == once


def test_merge_sub_bullets_stay_between_siblings() -> None:
    seg = """---
date: 2026-04-21
---

# 活动日志

- `09:00:00 - 09:30:00` 在 [[VS Code]] 编辑 [[bub-eye]]
    - `09:00:00 - 09:10:00` 调 `merge.py`
    - `09:10:00 - 09:30:00` 跑 pytest
- `10:00:00 - 10:05:00` 在 [[微信]] 和 [[chenkai]] 对话
"""
    out = merge_segment(
        segment_md=seg,
        segment_video_basename="eye_20260421_090000.mp4",
        existing_daily_md="",
    )
    idx_vscode = out.index("- `09:00:00 - 09:30:00` 在 [[VS Code]]")
    idx_sub1 = out.index("    - `09:00:00 - 09:10:00` 调")
    idx_sub2 = out.index("    - `09:10:00 - 09:30:00` 跑")
    idx_wechat = out.index("- `10:00:00 - 10:05:00` 在 [[微信]]")
    assert idx_vscode < idx_sub1 < idx_sub2 < idx_wechat


def test_merge_preserves_existing_date_when_new_segment_is_bare() -> None:
    bare_seg = "# 活动日志\n\n- `10:00:00 - 10:05:00` something\n"
    existing = (
        "---\ndate: 2026-04-21\nstart: 09:00:00\nend: 09:05:00\n"
        "videos:\n  - eye_20260421_090000.mp4\n---\n\n"
        "# [[2026-04-21]] 活动日志\n\n"
        "- `09:00:00 - 09:05:00` 之前记录\n"
    )
    out = merge_segment(
        segment_md=bare_seg,
        segment_video_basename="eye_20260421_100000.mp4",
        existing_daily_md=existing,
    )
    assert "date: 2026-04-21" in out
    assert "start: 09:00:00" in out
    assert "end: 10:05:00" in out
