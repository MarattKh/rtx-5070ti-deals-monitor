from pathlib import Path
from types import SimpleNamespace

import tools.agent_run as agent_run


class MemoryLogger:
    path = Path("agent.log")
    _fh = None

    def __init__(self):
        self.lines = []

    def write(self, message=""):
        self.lines.append(message)


class FakeRunner:
    def __init__(self, outputs=None):
        self.outputs = outputs or {}
        self.commands = []
        self.logger = MemoryLogger()

    def run(self, args, **kwargs):
        self.commands.append((list(args), kwargs))
        key = tuple(args)
        stdout = self.outputs.get(key, "")
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")


def test_default_checks_include_pytest_and_dns_smoke():
    checks = agent_run.default_checks()

    assert checks[0][1:] == ["-m", "pytest", "-q"]
    assert checks[1][1:] == ["tools/smoke_dns.py"]
    assert all("monitor_5070_ti_v_2.py" not in cmd for check in checks for cmd in check)


def test_default_checks_allow_optional_monitor_check():
    checks = agent_run.default_checks(include_monitor=True)

    assert checks[-1][1:] == ["monitor_5070_ti_v_2.py"]


def test_run_workflow_uses_codex_profile_agent_and_pr_flag(tmp_path, monkeypatch):
    task = tmp_path / "task.md"
    task.write_text("do the thing", encoding="utf-8")
    monkeypatch.setattr(agent_run, "ROOT", tmp_path)
    monkeypatch.setattr(agent_run, "default_checks", lambda include_monitor=False: [["python", "-m", "pytest", "-q"]])

    status_calls = {"count": 0}

    class StatusAwareRunner(FakeRunner):
        def run(self, args, **kwargs):
            self.commands.append((list(args), kwargs))
            key = tuple(args)
            if key == ("git", "status", "--porcelain"):
                status_calls["count"] += 1
                stdout = "" if status_calls["count"] == 1 else " M file.py\n"
            else:
                stdout = self.outputs.get(key, "")
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    runner = StatusAwareRunner(
        {
            ("git", "rev-parse", "--is-inside-work-tree"): "true\n",
            ("git", "status", "--short"): " M file.py\n",
            ("git", "diff", "--stat"): " file.py | 1 +\n",
        }
    )
    args = SimpleNamespace(
        task=str(task),
        branch="agent/test",
        create_pr=True,
        pr_title="Agent test",
        pr_body="Body",
        check_monitor=False,
    )

    agent_run.run_workflow(args, runner)

    commands = [cmd for cmd, _ in runner.commands]
    assert ["codex", "exec", "--profile", "agent"] in commands
    codex_call = next(kwargs for cmd, kwargs in runner.commands if cmd == ["codex", "exec", "--profile", "agent"])
    assert codex_call["input_text"] == "do the thing"
    assert ["git", "commit", "-m", "Agent test"] in commands
    assert [
        "gh",
        "pr",
        "create",
        "--base",
        "main",
        "--head",
        "agent/test",
        "--title",
        "Agent test",
        "--body",
        "Body",
    ] in commands


def test_run_workflow_skips_commit_when_no_changes(tmp_path, monkeypatch):
    task = tmp_path / "task.md"
    task.write_text("noop", encoding="utf-8")
    monkeypatch.setattr(agent_run, "ROOT", tmp_path)
    monkeypatch.setattr(agent_run, "default_checks", lambda include_monitor=False: [])

    runner = FakeRunner(
        {
            ("git", "rev-parse", "--is-inside-work-tree"): "true\n",
            ("git", "status", "--porcelain"): "",
            ("git", "status", "--short"): "",
            ("git", "diff", "--stat"): "",
        }
    )
    args = SimpleNamespace(
        task=str(task),
        branch="agent/noop",
        create_pr=False,
        pr_title=None,
        pr_body=None,
        check_monitor=False,
    )

    agent_run.run_workflow(args, runner)

    commands = [cmd for cmd, _ in runner.commands]
    assert ["git", "commit", "-m", "Run agent task task"] not in commands
    assert ["git", "push", "-u", "origin", "agent/noop"] not in commands
