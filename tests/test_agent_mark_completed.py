import json

import pytest

import tools.agent_mark_completed as agent_mark_completed


def write_queue(path, tasks):
    path.write_text(json.dumps({"tasks": tasks}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_queue(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_complete_task_marks_matching_task_completed(tmp_path):
    queue_path = tmp_path / "queue.json"
    write_queue(
        queue_path,
        [
            {"id": "first", "status": "pending", "task": "first.md", "branch": "agent/first"},
            {"id": "second", "status": "needs_review", "task": "second.md", "branch": "agent/second"},
        ],
    )

    previous_status, new_status = agent_mark_completed.complete_task(queue_path, "first")

    queue = read_queue(queue_path)
    assert (previous_status, new_status) == ("pending", "completed")
    assert queue["tasks"][0]["status"] == "completed"
    assert queue["tasks"][1]["status"] == "needs_review"


def test_main_dry_run_reports_change_without_writing(tmp_path, capsys):
    queue_path = tmp_path / "queue.json"
    write_queue(
        queue_path,
        [
            {
                "id": "reviewed",
                "status": "needs_review",
                "task": "reviewed.md",
                "branch": "agent/reviewed",
            }
        ],
    )
    before = queue_path.read_bytes()

    result = agent_mark_completed.main(["reviewed", "--queue", str(queue_path), "--dry-run"])

    captured = capsys.readouterr()
    assert result == 0
    assert "[dry-run] reviewed: needs_review -> completed" in captured.out
    assert queue_path.read_bytes() == before


def test_complete_task_fails_clearly_when_task_id_is_missing(tmp_path):
    queue_path = tmp_path / "queue.json"
    write_queue(
        queue_path,
        [{"id": "known", "status": "pending", "task": "known.md", "branch": "agent/known"}],
    )

    with pytest.raises(agent_mark_completed.MarkCompletedError, match="Task id not found in queue: missing"):
        agent_mark_completed.complete_task(queue_path, "missing")

    assert read_queue(queue_path)["tasks"][0]["status"] == "pending"


def test_main_missing_task_id_prints_error(tmp_path, capsys):
    queue_path = tmp_path / "queue.json"
    write_queue(
        queue_path,
        [{"id": "known", "status": "pending", "task": "known.md", "branch": "agent/known"}],
    )

    result = agent_mark_completed.main(["missing", "--queue", str(queue_path)])

    captured = capsys.readouterr()
    assert result == 1
    assert "ERROR: Task id not found in queue: missing" in captured.err


def test_complete_task_preserves_utf8_text_without_bom(tmp_path):
    queue_path = tmp_path / "queue.json"
    title = "\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u043e\u0447\u0435\u0440\u0435\u0434\u044c"
    write_queue(
        queue_path,
        [
            {
                "id": "utf8_task",
                "status": "pending",
                "task": "utf8.md",
                "branch": "agent/utf8",
                "pr_title": title,
            }
        ],
    )

    agent_mark_completed.complete_task(queue_path, "utf8_task")

    raw = queue_path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert title in text
    assert read_queue(queue_path)["tasks"][0]["status"] == "completed"
