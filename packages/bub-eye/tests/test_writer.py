"""Unit tests for VisualWriter — verify payload shape without real ffmpeg."""

from __future__ import annotations

from pathlib import Path

from bub_eye.tape import VisualWriter, visual_tape_name


def _make_segment(tmp: Path, name: str, size: int = 12345) -> Path:
    path = tmp / name
    path.write_bytes(b"\x00" * size)
    return path


def test_appends_one_event_per_segment(tmp_path: Path) -> None:
    segments_dir = tmp_path / "segments"
    tape_dir = tmp_path / "tapes"
    segments_dir.mkdir()

    writer = VisualWriter(
        tape_dir=tape_dir,
        segment_seconds=60,
        run_id="run-xyz",
        host="laptop.local",
    )

    seg = _make_segment(segments_dir, "eye_20260417_143022.mp4", size=12345)
    writer.on_new_segment(seg)

    tape_file = tape_dir / f"{visual_tape_name()}.jsonl"
    assert tape_file.exists()

    lines = tape_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_payload_shape(tmp_path: Path) -> None:
    import json

    segments_dir = tmp_path / "segments"
    tape_dir = tmp_path / "tapes"
    segments_dir.mkdir()

    writer = VisualWriter(
        tape_dir=tape_dir,
        segment_seconds=60,
        run_id="run-xyz",
        host="laptop.local",
    )

    seg = _make_segment(segments_dir, "eye_20260417_143022.mp4", size=12345)
    writer.on_new_segment(seg)

    line = (tape_dir / f"{visual_tape_name()}.jsonl").read_text().strip()
    record = json.loads(line)

    assert record["kind"] == "event"
    assert record["payload"]["name"] == "vision/segment"

    data = record["payload"]["data"]
    assert data["path"] == str(seg)
    assert data["size_bytes"] == 12345
    assert data["duration_s"] == 60.0
    assert data["start"] == "2026-04-17T14:30:22+00:00"
    assert data["end"] == "2026-04-17T14:31:22+00:00"

    meta = record["meta"]
    assert meta["run_id"] == "run-xyz"
    assert meta["host"] == "laptop.local"


def test_missing_segment_does_not_raise(tmp_path: Path) -> None:
    tape_dir = tmp_path / "tapes"

    writer = VisualWriter(
        tape_dir=tape_dir,
        segment_seconds=60,
        run_id="r",
        host="h",
    )

    writer.on_new_segment(tmp_path / "does_not_exist.mp4")

    tape_file = tape_dir / f"{visual_tape_name()}.jsonl"
    assert not tape_file.exists() or tape_file.read_text() == ""


def test_multiple_segments_are_appended_in_order(tmp_path: Path) -> None:
    import json

    segments_dir = tmp_path / "segments"
    tape_dir = tmp_path / "tapes"
    segments_dir.mkdir()

    writer = VisualWriter(
        tape_dir=tape_dir,
        segment_seconds=60,
        run_id="r",
        host="h",
    )

    names = [
        "eye_20260417_143022.mp4",
        "eye_20260417_143122.mp4",
        "eye_20260417_143222.mp4",
    ]
    for i, n in enumerate(names):
        writer.on_new_segment(_make_segment(segments_dir, n, size=1000 + i))

    lines = (tape_dir / f"{visual_tape_name()}.jsonl").read_text().splitlines()
    assert len(lines) == 3

    records = [json.loads(line) for line in lines]
    assert [r["payload"]["data"]["path"].rsplit("/", 1)[-1] for r in records] == names
    assert [r["payload"]["data"]["size_bytes"] for r in records] == [1000, 1001, 1002]

    # IDs are assigned by FileTapeStore and must be sequential.
    assert [r["id"] for r in records] == [1, 2, 3]


def test_parse_bad_filename_writes_null_times(tmp_path: Path) -> None:
    import json

    segments_dir = tmp_path / "segments"
    tape_dir = tmp_path / "tapes"
    segments_dir.mkdir()

    writer = VisualWriter(
        tape_dir=tape_dir,
        segment_seconds=60,
        run_id="r",
        host="h",
    )

    odd = _make_segment(segments_dir, "weird_name.mp4", size=10)
    writer.on_new_segment(odd)

    record = json.loads(
        (tape_dir / f"{visual_tape_name()}.jsonl").read_text().strip()
    )
    assert record["payload"]["data"]["start"] is None
    assert record["payload"]["data"]["end"] is None
    assert record["payload"]["data"]["path"] == str(odd)


def test_visual_tape_name_is_list_compatible() -> None:
    # FileTapeStore.list_tapes expects exactly one '__' separator.
    name = visual_tape_name()
    assert name.count("__") == 1
    assert name.startswith("visual__")
