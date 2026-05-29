import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import tools.agent_cycle as agent_cycle


class MemoryLogger:
    path = Path("cycle.log")
    _fh = None

    def __init__(self):
        self.lines = []

    def write(self, message=""):
        self.lines.append(message)


class FakeRunner:
    def __init__(self, outputs=None, fail_prefix=None):
        self.outputs = outputs or {}
        self.fail_prefix = fail_prefix or []
        self.commands = []
        self.logger = MemoryLogger()

    def run(self, args, **kwargs):
        command = list(args)
        self.commands.append((command, kwargs))
        for prefix in self.fail_prefix:
            if command[: len(prefix)] == prefix:
                raise agent_cycle.CycleError("forced failure")
        value = self.outputs.get(tuple(command), "")
        return SimpleNamespace(returncode=0, stdout=value, stderr="")


def write_queue(path, tasks):
    path.write_text(json.dumps({"tasks": tasks}, ensure_ascii=False), encoding="utf-8")


def make_cycle_args(queue_path, state_path, *, max_tasks=1, create_pr=True, auto_merge_safe=False, dry_run=False):
    return SimpleNamespace(
        queue=str(queue_path),
        state=str(state_path),
        max_tasks=max_tasks,
        create_pr=create_pr,
        auto_merge_safe=auto_merge_safe,
        dry_run=dry_run,
        once=True,
    )


def test_load_queue_accepts_tasks_object(tmp_path):
    queue_path = tmp_path / "queue.json"
    write_queue(
        queue_path,
        [
            {
                "id": "task_a",
                "status": "pending",
                "task": "tools/agent_tasks/a.md",
                "branch": "agent/a",
            }
        ],
    )

    tasks = agent_cycle.load_queue(queue_path)

    assert tasks[0]["id"] == "task_a"
    assert tasks[0]["branch"] == "agent/a"


def test_load_queue_accepts_utf8_bom(tmp_path):
    queue_path = tmp_path / "queue.json"
    queue_path.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": "task_bom",
                        "status": "pending",
                        "task": "tools/agent_tasks/bom.md",
                        "branch": "agent/bom",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8-sig",
    )

    tasks = agent_cycle.load_queue(queue_path)

    assert tasks[0]["id"] == "task_bom"


def test_select_pending_tasks_empty_queue_selects_zero_tasks():
    selected = agent_cycle.select_pending_tasks([], {"tasks": {}}, max_tasks=1)

    assert selected == []


def test_select_pending_tasks_skips_terminal_state_and_non_pending_queue_items():
    queue = [
        {"id": status, "status": "pending", "task": f"{status}.md", "branch": f"agent/{status}"}
        for status in agent_cycle.TERMINAL_RUNTIME_STATUSES
    ]
    queue.extend(
        [
            {"id": "paused", "status": "paused", "task": "b.md", "branch": "agent/paused"},
            {"id": "next", "status": "pending", "task": "c.md", "branch": "agent/next"},
        ]
    )
    state = {"tasks": {status: {"status": status} for status in agent_cycle.TERMINAL_RUNTIME_STATUSES}}

    selected = agent_cycle.select_pending_tasks(queue, state, max_tasks=10)

    assert [task["id"] for task in selected] == ["next"]


def test_select_pending_tasks_max_tasks_one_limits_one_runnable_task():
    queue = [
        {"id": "first", "status": "pending", "task": "a.md", "branch": "agent/first"},
        {"id": "second", "status": "pending", "task": "b.md", "branch": "agent/second"},
    ]

    selected = agent_cycle.select_pending_tasks(queue, {"tasks": {}}, max_tasks=1)

    assert [task["id"] for task in selected] == ["first"]


def test_update_task_state_records_pr_metadata_and_result(monkeypatch):
    monkeypatch.setattr(agent_cycle, "utc_timestamp", lambda: "2026-05-28T10:00:00+00:00")
    state = {"tasks": {}}
    task = {"id": "task_a", "branch": "agent/a"}

    agent_cycle.update_task_state(
        state,
        task,
        status="needs_review",
        result="dangerous files changed: tools/agent_cycle.py",
        pr={"url": "https://github.test/pull/7", "number": 7},
        changed_files=["tools/agent_cycle.py"],
    )

    assert state["tasks"]["task_a"] == {
        "status": "needs_review",
        "branch": "agent/a",
        "pr_url": "https://github.test/pull/7",
        "pr_number": 7,
        "updated_at": "2026-05-28T10:00:00+00:00",
        "result": "dangerous files changed: tools/agent_cycle.py",
        "changed_files": ["tools/agent_cycle.py"],
    }


def test_build_agent_run_command_includes_task_branch_pr_and_dry_run():
    task = {
        "id": "task_a",
        "task": "tools/agent_tasks/a.md",
        "branch": "agent/a",
        "pr_title": "Task A",
        "pr_body": "Body A",
    }

    command = agent_cycle.build_agent_run_command(task, create_pr=True, dry_run=True)

    assert command[:2] == [agent_cycle.sys.executable, str(agent_cycle.ROOT / "tools" / "agent_run.py")]
    assert "--task" in command
    assert str(agent_cycle.ROOT / "tools" / "agent_tasks" / "a.md") in command
    assert command[command.index("--branch") + 1] == "agent/a"
    assert command[command.index("--pr-title") + 1] == "Task A"
    assert command[command.index("--pr-body") + 1] == "Body A"
    assert "--create-pr" in command
    assert "--dry-run" in command


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/tests.yml",
        "tools/agent_run.py",
        "tools/agent_cycle.py",
        "tools/agent_tasks/queue.json",
        "config.env",
        "secrets/token.txt",
        "scheduler/install.ps1",
        "systemd/monitor.service",
        "pyproject.toml",
        "requirements.txt",
    ],
)
def test_dangerous_path_detection_denies_sensitive_paths(path):
    assert agent_cycle.is_dangerous_path(path) is True


def test_dangerous_path_detection_allows_normal_application_files():
    assert agent_cycle.is_dangerous_path("parsers/citilink.py") is False
    assert agent_cycle.is_dangerous_path("tests/test_monitor.py") is False


def test_auto_merge_decision_requires_open_mergeable_pr_and_safe_paths():
    pr = {"number": 3, "url": "https://github.test/pull/3", "state": "OPEN", "mergeable": "MERGEABLE"}

    assert agent_cycle.evaluate_auto_merge(pr, ["parsers/citilink.py", "tests/test_monitor.py"]) == (
        True,
        "safe to merge",
    )

    allowed, reason = agent_cycle.evaluate_auto_merge(pr, ["tools/agent_cycle.py"])
    assert allowed is False
    assert "dangerous files changed" in reason

    allowed, reason = agent_cycle.evaluate_auto_merge({**pr, "mergeable": "CONFLICTING"}, ["parsers/citilink.py"])
    assert allowed is False
    assert "not mergeable" in reason


def test_run_cycle_calls_agent_run_and_records_needs_review_pr(tmp_path):
    task_file = tmp_path / "task.md"
    task_file.write_text("do work", encoding="utf-8")
    queue_path = tmp_path / "queue.json"
    state_path = tmp_path / "state.json"
    task = {
        "id": "task_a",
        "status": "pending",
        "task": str(task_file),
        "branch": "agent/a",
        "pr_title": "Task A",
        "pr_body": "Body A",
    }
    write_queue(queue_path, [task])
    pr_view = json.dumps({"number": 4, "url": "https://github.test/pull/4", "state": "OPEN", "mergeable": "MERGEABLE"})
    runner = FakeRunner({("gh", "pr", "view", "agent/a", "--json", "number,url,state,mergeable"): pr_view})
    args = make_cycle_args(queue_path, state_path)

    agent_cycle.run_cycle(args, runner)

    commands = [cmd for cmd, _ in runner.commands]
    agent_command = commands[0]
    assert agent_command[:2] == [agent_cycle.sys.executable, str(agent_cycle.ROOT / "tools" / "agent_run.py")]
    assert "--create-pr" in agent_command
    assert ["gh", "pr", "view", "agent/a", "--json", "number,url,state,mergeable"] in commands
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["tasks"]["task_a"]["status"] == "needs_review"
    assert state["tasks"]["task_a"]["pr_number"] == 4


def test_run_cycle_records_pushed_branch_without_pr_as_needs_review(tmp_path):
    task_file = tmp_path / "task.md"
    task_file.write_text("do work", encoding="utf-8")
    queue_path = tmp_path / "queue.json"
    state_path = tmp_path / "state.json"
    task = {
        "id": "task_a",
        "status": "pending",
        "task": str(task_file),
        "branch": "agent/a",
        "pr_title": "Task A",
        "pr_body": "Body A",
    }
    write_queue(queue_path, [task])
    runner = FakeRunner(
        {
            ("git", "ls-remote", "--heads", "origin", "agent/a"): "abc123def456\trefs/heads/agent/a\n",
            ("git", "status", "--porcelain"): "",
        },
        fail_prefix=[[agent_cycle.sys.executable, str(agent_cycle.ROOT / "tools" / "agent_run.py")]],
    )
    args = make_cycle_args(queue_path, state_path, create_pr=True)

    result = agent_cycle.run_cycle(args, runner)

    assert result == 0
    state = json.loads(state_path.read_text(encoding="utf-8"))
    task_state = state["tasks"]["task_a"]
    assert task_state["status"] == "needs_review"
    assert task_state["pr_url"] is None
    assert "branch=agent/a" in task_state["result"]
    assert "commit_sha=abc123def456" in task_state["result"]
    assert "worktree_clean=yes" in task_state["result"]
    assert 'suggested_pr_command=gh pr create --base main --head agent/a --title "Task A" --body "Body A"' in task_state["result"]
    assert "Task task_a: pushed branch needs PR recovery" in runner.logger.lines


@pytest.mark.parametrize("runtime_status", sorted(agent_cycle.TERMINAL_RUNTIME_STATUSES))
def test_run_cycle_zero_selected_terminal_tasks_do_not_execute_agent_or_codex(tmp_path, runtime_status):
    task_file = tmp_path / "task.md"
    task_file.write_text("do work", encoding="utf-8")
    queue_path = tmp_path / "queue.json"
    state_path = tmp_path / "state.json"
    task = {
        "id": "terminal_task",
        "status": "pending",
        "task": str(task_file),
        "branch": "agent/terminal-task",
    }
    write_queue(queue_path, [task])
    state_path.write_text(
        json.dumps({"tasks": {"terminal_task": {"status": runtime_status}}}),
        encoding="utf-8",
    )
    runner = FakeRunner()

    result = agent_cycle.run_cycle(make_cycle_args(queue_path, state_path), runner)

    commands = [cmd for cmd, _ in runner.commands]
    assert result == 0
    assert commands == []
    assert "Selected tasks: 0" in runner.logger.lines


def test_run_cycle_auto_merge_safe_merges_safe_pr(tmp_path):
    task_file = tmp_path / "task.md"
    task_file.write_text("do work", encoding="utf-8")
    queue_path = tmp_path / "queue.json"
    state_path = tmp_path / "state.json"
    task = {"id": "task_a", "status": "pending", "task": str(task_file), "branch": "agent/a"}
    write_queue(queue_path, [task])
    pr_view = json.dumps({"number": 4, "url": "https://github.test/pull/4", "state": "OPEN", "mergeable": "MERGEABLE"})
    runner = FakeRunner(
        {
            ("gh", "pr", "view", "agent/a", "--json", "number,url,state,mergeable"): pr_view,
            ("gh", "pr", "diff", "4", "--name-only"): "parsers/citilink.py\ntests/test_monitor.py\n",
        }
    )
    args = make_cycle_args(queue_path, state_path, auto_merge_safe=True)

    agent_cycle.run_cycle(args, runner)

    commands = [cmd for cmd, _ in runner.commands]
    assert ["gh", "pr", "merge", "4", "--merge", "--delete-branch"] in commands
    assert ["git", "checkout", "main"] in commands
    assert ["git", "pull", "--ff-only"] in commands
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["tasks"]["task_a"]["status"] == "completed"
    assert state["tasks"]["task_a"]["result"] == "merged"


def test_run_cycle_auto_merge_safe_leaves_dangerous_pr_open(tmp_path):
    task_file = tmp_path / "task.md"
    task_file.write_text("do work", encoding="utf-8")
    queue_path = tmp_path / "queue.json"
    state_path = tmp_path / "state.json"
    task = {"id": "task_a", "status": "pending", "task": str(task_file), "branch": "agent/a"}
    write_queue(queue_path, [task])
    pr_view = json.dumps({"number": 4, "url": "https://github.test/pull/4", "state": "OPEN", "mergeable": "MERGEABLE"})
    runner = FakeRunner(
        {
            ("gh", "pr", "view", "agent/a", "--json", "number,url,state,mergeable"): pr_view,
            ("gh", "pr", "diff", "4", "--name-only"): "tools/agent_cycle.py\n",
        }
    )
    args = make_cycle_args(queue_path, state_path, auto_merge_safe=True)

    agent_cycle.run_cycle(args, runner)

    commands = [cmd for cmd, _ in runner.commands]
    assert ["gh", "pr", "merge", "4", "--merge", "--delete-branch"] not in commands
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["tasks"]["task_a"]["status"] == "needs_review"
    assert "dangerous files changed" in state["tasks"]["task_a"]["result"]

