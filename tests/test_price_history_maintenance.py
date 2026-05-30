import json
from pathlib import Path

from tools import price_history_maintenance


def write_jsonl(path: Path, count: int) -> list[dict[str, object]]:
    records = [
        {
            "timestamp": f"2026-05-29T0{i}:00:00+00:00",
            "source": "DNS",
            "title": f"Offer {i}",
            "price": 90000 + i,
        }
        for i in range(count)
    ]
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    return records


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_retain_recent_records_keeps_only_newest_lines(tmp_path):
    history_path = tmp_path / "price_history.jsonl"
    records = write_jsonl(history_path, 5)

    result = price_history_maintenance.retain_recent_records(history_path, keep_records=2)

    assert read_jsonl(history_path) == records[-2:]
    assert result.original_records == 5
    assert result.final_records == 2
    assert result.original_bytes > result.final_bytes


def test_retain_recent_records_dry_run_does_not_modify_file(tmp_path):
    history_path = tmp_path / "price_history.jsonl"
    records = write_jsonl(history_path, 3)
    original_content = history_path.read_text(encoding="utf-8")

    result = price_history_maintenance.retain_recent_records(history_path, keep_records=1, dry_run=True)

    assert history_path.read_text(encoding="utf-8") == original_content
    assert read_jsonl(history_path) == records
    assert result.original_records == 3
    assert result.final_records == 1
    assert result.dry_run is True


def test_rotate_if_larger_than_moves_history_to_numbered_file(tmp_path):
    history_path = tmp_path / "price_history.jsonl"
    records = write_jsonl(history_path, 3)
    original_content = history_path.read_text(encoding="utf-8")

    result = price_history_maintenance.rotate_if_larger_than(history_path, max_bytes=1)

    rotated_path = tmp_path / "price_history.jsonl.1"
    assert result.rotated_to == rotated_path
    assert rotated_path.read_text(encoding="utf-8") == original_content
    assert history_path.exists()
    assert history_path.read_text(encoding="utf-8") == ""
    assert read_jsonl(rotated_path) == records
    assert result.original_records == 3
    assert result.final_records == 0


def test_rotate_if_larger_than_uses_next_available_number(tmp_path):
    history_path = tmp_path / "price_history.jsonl"
    existing_rotation = tmp_path / "price_history.jsonl.1"
    existing_rotation.write_text("existing\n", encoding="utf-8")
    write_jsonl(history_path, 1)

    result = price_history_maintenance.rotate_if_larger_than(history_path, max_bytes=1)

    assert result.rotated_to == tmp_path / "price_history.jsonl.2"
    assert existing_rotation.read_text(encoding="utf-8") == "existing\n"
    assert result.rotated_to.exists()


def test_rotate_if_larger_than_leaves_small_file_unchanged(tmp_path):
    history_path = tmp_path / "price_history.jsonl"
    write_jsonl(history_path, 2)
    original_content = history_path.read_text(encoding="utf-8")

    result = price_history_maintenance.rotate_if_larger_than(history_path, max_bytes=history_path.stat().st_size)

    assert history_path.read_text(encoding="utf-8") == original_content
    assert result.rotated_to is None
    assert result.original_records == 2
    assert result.final_records == 2


def test_cli_reports_retention_result(tmp_path, capsys):
    history_path = tmp_path / "price_history.jsonl"
    write_jsonl(history_path, 4)

    result = price_history_maintenance.main([str(history_path), "--keep-records", "2"])

    captured = capsys.readouterr()
    assert result == 0
    assert "Records: 4 -> 2" in captured.out
    assert "Bytes:" in captured.out
    assert captured.err == ""
