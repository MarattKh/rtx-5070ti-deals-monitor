import json

import tools.agent_queue_status as agent_queue_status


def write_queue(path, tasks):
    path.write_text(json.dumps({"tasks": tasks}, ensure_ascii=False), encoding="utf-8")


def test_format_status_shows_counts_rows_and_uses_cycle_runnable_logic():
    queue = [
        {
            "id": "done",
            "status": "pending",
            "task": "tools/agent_tasks/done.md",
            "branch": "agent/done",
            "pr_title": "Done task",
        },
        {
            "id": "review",
            "status": "needs_review",
            "task": "tools/agent_tasks/review.md",
            "branch": "agent/review",
            "pr_title": "Review task",
        },
        {
            "id": "failed",
            "status": "pending",
            "task": "tools/agent_tasks/failed.md",
            "branch": "agent/failed",
            "pr_title": "Failed task",
        },
        {
            "id": "next",
            "status": "pending",
            "task": "tools/agent_tasks/next.md",
            "branch": "agent/next",
            "pr_title": "Next task",
        },
    ]
    state = {
        "tasks": {
            "done": {"status": "completed", "branch": "agent/done"},
            "failed": {"status": "failed", "branch": "agent/failed"},
        }
    }

    output = agent_queue_status.format_status(queue, state)

    assert "Counts: total=4 pending=3 runnable=2 completed=1 failed=1 needs_review=1" in output
    assert "task id" in output
    assert "queue" in output
    assert "state" in output
    assert "done" in output
    assert "pending" in output
    assert "completed" in output
    assert "agent/next" in output
    assert "Next task" in output


def test_load_state_for_status_handles_missing_file(tmp_path):
    state, missing = agent_queue_status.load_state_for_status(tmp_path / "missing.json")

    assert missing is True
    assert state == {"tasks": {}}


def test_main_prints_missing_state_message_and_utf8_text(tmp_path, capsys):
    queue_path = tmp_path / "queue.json"
    state_path = tmp_path / "missing-state.json"
    write_queue(
        queue_path,
        [
            {
                "id": "utf8_task",
                "status": "pending",
                "task": "tools/agent_tasks/utf8.md",
                "branch": "agent/utf8",
                "pr_title": "Проверить очередь",
            }
        ],
    )

    result = agent_queue_status.main(["--queue", str(queue_path), "--state", str(state_path)])

    captured = capsys.readouterr()
    assert result == 0
    assert "State: missing" in captured.out
    assert "Проверить очередь" in captured.out
    assert "Counts: total=1 pending=1 runnable=1 completed=0 failed=0 needs_review=0" in captured.out
