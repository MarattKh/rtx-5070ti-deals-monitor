from pathlib import Path
from types import SimpleNamespace

import pytest

import tools.agent_run as agent_run
import tools.agent_cycle as agent_cycle


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
        output = self.outputs.get(key, "")
        if isinstance(output, tuple):
            returncode, stdout, stderr = output
        else:
            returncode, stdout, stderr = 0, output, ""
        if kwargs.get("check", True) and returncode != 0:
            raise agent_run.RunnerError(f"Command failed with exit code {returncode}: {agent_run.format_command(args)}")
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_resolve_codex_executable_uses_shutil_which_candidates(monkeypatch):
    calls = []

    def fake_which(candidate):
        calls.append(candidate)
        return r"C:\npm\codex.cmd" if candidate == "codex.cmd" else None

    monkeypatch.setattr(agent_run.shutil, "which", fake_which)

    assert agent_run.resolve_codex_executable() == r"C:\npm\codex.cmd"
    assert calls == ["codex", "codex.cmd"]


def test_resolve_codex_executable_raises_clear_error_when_missing(monkeypatch):
    calls = []

    def fake_which(candidate):
        calls.append(candidate)
        return None

    monkeypatch.setattr(agent_run.shutil, "which", fake_which)

    with pytest.raises(RuntimeError, match="Codex CLI is not found in PATH"):
        agent_run.resolve_codex_executable()

    assert calls == ["codex", "codex.cmd", "codex.exe"]


def test_default_checks_include_pytest_and_dns_smoke():
    checks = agent_run.default_checks()

    assert checks[0][1:] == ["-m", "pytest", "-q"]
    assert checks[1][1:] == ["tools/smoke_dns.py"]
    assert all("monitor_5070_ti_v_2.py" not in cmd for check in checks for cmd in check)


def test_default_checks_allow_optional_monitor_check():
    checks = agent_run.default_checks(include_monitor=True)

    assert checks[-1][1:] == ["monitor_5070_ti_v_2.py"]


def test_run_workflow_uses_resolved_codex_profile_agent_and_pr_flag(tmp_path, monkeypatch):
    task = tmp_path / "task.md"
    task.write_text("do the thing", encoding="utf-8")
    monkeypatch.setattr(agent_run, "ROOT", tmp_path)
    monkeypatch.setattr(agent_run, "default_checks", lambda include_monitor=False: [["python", "-m", "pytest", "-q"]])
    resolved_codex = r"C:\npm\codex.cmd"
    monkeypatch.setattr(agent_run, "resolve_codex_executable", lambda: resolved_codex)

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
    assert [resolved_codex, "exec", "--profile", "agent"] in commands
    assert ["codex", "exec", "--profile", "agent"] not in commands
    codex_call = next(kwargs for cmd, kwargs in runner.commands if cmd == [resolved_codex, "exec", "--profile", "agent"])
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
    monkeypatch.setattr(agent_run, "resolve_codex_executable", lambda: r"C:\npm\codex.cmd")

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


def test_prepare_task_branch_creates_missing_branch():
    runner = FakeRunner({("git", "branch", "--list", "--format=%(refname:short)", "agent/new"): ""})

    agent_run.prepare_task_branch(runner, "agent/new")

    commands = [cmd for cmd, _ in runner.commands]
    assert ["git", "checkout", "-b", "agent/new"] in commands
    assert ["git", "reset", "--hard", "main"] not in commands


def test_prepare_task_branch_reuses_existing_branch_with_no_unique_commits():
    runner = FakeRunner(
        {
            ("git", "branch", "--list", "--format=%(refname:short)", "agent/retry"): "agent/retry\n",
            ("git", "rev-list", "--count", "main..agent/retry"): "0\n",
        }
    )

    agent_run.prepare_task_branch(runner, "agent/retry")

    commands = [cmd for cmd, _ in runner.commands]
    assert ["git", "checkout", "agent/retry"] in commands
    assert ["git", "reset", "--hard", "main"] in commands
    assert any("has no commits outside main" in line for line in runner.logger.lines)


def test_prepare_task_branch_stops_when_existing_branch_has_unique_commits():
    runner = FakeRunner(
        {
            ("git", "branch", "--list", "--format=%(refname:short)", "agent/work"): "agent/work\n",
            ("git", "rev-list", "--count", "main..agent/work"): "2\n",
        }
    )

    with pytest.raises(agent_run.RunnerError, match="already exists and has 2 commit"):
        agent_run.prepare_task_branch(runner, "agent/work")

    commands = [cmd for cmd, _ in runner.commands]
    assert ["git", "checkout", "agent/work"] not in commands
    assert ["git", "reset", "--hard", "main"] not in commands


class StrictEncodedStream:
    encoding = "cp1251"

    def __init__(self):
        self.lines = []

    def write(self, value):
        value.encode(self.encoding, errors="strict")
        self.lines.append(value)

    def flush(self):
        pass


@pytest.mark.parametrize("module", [agent_run, agent_cycle])
def test_logger_write_is_unicode_safe_for_cp1251_console_and_keeps_utf8_log(tmp_path, monkeypatch, module):
    stream = StrictEncodedStream()
    monkeypatch.setattr(module.sys, "stdout", stream)
    log_path = tmp_path / "agent.log"
    logger = module.Logger(log_path)
    message = "BOM:\ufeff Cyrillic: \u041f\u0440\u0438\u0432\u0435\u0442 emoji: \U0001f680 replacement: \ufffd"

    logger.write(message)
    logger.close()

    assert "BOM:?" in "".join(stream.lines)
    assert "Cyrillic: \u041f\u0440\u0438\u0432\u0435\u0442" in "".join(stream.lines)
    assert log_path.read_text(encoding="utf-8") == message + "\n"
