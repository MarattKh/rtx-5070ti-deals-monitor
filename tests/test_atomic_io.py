from __future__ import annotations

import os
from pathlib import Path

import pytest

from tools.atomic_io import atomic_write_text


# ---------------------------------------------------------------------------
# (a) Round-trip: write then read back equals the original text
# ---------------------------------------------------------------------------

def test_atomic_write_text_round_trip(tmp_path):
    target = tmp_path / "state.json"
    text = '{"tasks": {}}\n'

    atomic_write_text(target, text)

    assert target.read_text(encoding="utf-8") == text


def test_atomic_write_text_round_trip_unicode(tmp_path):
    target = tmp_path / "output.json"
    text = '{"source": "Ситилинк", "price": 90000}\n'

    atomic_write_text(target, text)

    assert target.read_text(encoding="utf-8") == text


def test_atomic_write_text_creates_parent_directory(tmp_path):
    target = tmp_path / "new" / "nested" / "file.json"

    atomic_write_text(target, "hello\n")

    assert target.read_text(encoding="utf-8") == "hello\n"


def test_atomic_write_text_overwrites_existing_file(tmp_path):
    target = tmp_path / "file.json"
    target.write_text("old content\n", encoding="utf-8")

    atomic_write_text(target, "new content\n")

    assert target.read_text(encoding="utf-8") == "new content\n"


# ---------------------------------------------------------------------------
# (b) Byte-identical to Path.write_text for the same input
# ---------------------------------------------------------------------------

def test_atomic_write_text_bytes_identical_to_write_text(tmp_path):
    text = '{"tasks": {"stage_1n": {"status": "completed"}}}\n'
    ref = tmp_path / "reference.json"
    via_helper = tmp_path / "via_helper.json"

    ref.write_text(text, encoding="utf-8")
    atomic_write_text(via_helper, text, encoding="utf-8")

    assert via_helper.read_bytes() == ref.read_bytes()


def test_atomic_write_text_bytes_identical_multiline(tmp_path):
    import json
    data = {"tasks": {"a": {"status": "completed", "result": "merged"}, "b": {"status": "failed"}}}
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    ref = tmp_path / "ref.json"
    via_helper = tmp_path / "helper.json"

    ref.write_text(text, encoding="utf-8")
    atomic_write_text(via_helper, text, encoding="utf-8")

    assert via_helper.read_bytes() == ref.read_bytes()


def test_atomic_write_text_bytes_identical_utf8_bom_free(tmp_path):
    """Ensures no BOM is written (Path.write_text with encoding='utf-8' never adds one)."""
    ref = tmp_path / "ref.json"
    via_helper = tmp_path / "helper.json"
    text = '{"x": 1}\n'

    ref.write_text(text, encoding="utf-8")
    atomic_write_text(via_helper, text, encoding="utf-8")

    assert not via_helper.read_bytes().startswith(b"\xef\xbb\xbf")
    assert via_helper.read_bytes() == ref.read_bytes()


# ---------------------------------------------------------------------------
# (c) Failure-safety: os.replace raises → original untouched, no .tmp left
# ---------------------------------------------------------------------------

def test_atomic_write_text_failure_leaves_original_unchanged(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    original_text = '{"tasks": {"existing": {"status": "completed"}}}\n'
    target.write_text(original_text, encoding="utf-8")

    def boom(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", boom)

    with pytest.raises(OSError, match="simulated replace failure"):
        atomic_write_text(target, '{"tasks": {}}\n')

    assert target.read_text(encoding="utf-8") == original_text


def test_atomic_write_text_failure_removes_tmp_file(tmp_path, monkeypatch):
    target = tmp_path / "state.json"

    def boom(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", boom)

    with pytest.raises(OSError):
        atomic_write_text(target, "content\n")

    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == [], f"leftover .tmp files: {tmp_files}"


def test_atomic_write_text_failure_on_new_file_leaves_no_target(tmp_path, monkeypatch):
    """When the target did not exist before, a failed write must not create it."""
    target = tmp_path / "new_state.json"

    def boom(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", boom)

    with pytest.raises(OSError):
        atomic_write_text(target, "content\n")

    assert not target.exists()
    assert list(tmp_path.glob("*.tmp")) == []
