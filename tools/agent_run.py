from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_PATH = Path(r"C:\ProgramData\MonitorAgent\agent-last.log")


class RunnerError(RuntimeError):
    pass


class Logger:
    def __init__(self, path: Path = DEFAULT_LOG_PATH) -> None:
        self.path = path
        self._fh = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = path.open("w", encoding="utf-8")
        except OSError:
            self._fh = None

    def close(self) -> None:
        if self._fh:
            self._fh.close()

    def write(self, message: str = "") -> None:
        message = redact_secrets(message)
        print(message)
        if self._fh:
            self._fh.write(message + "\n")
            self._fh.flush()


class CommandRunner:
    def __init__(self, dry_run: bool, logger: Logger, cwd: Path = ROOT) -> None:
        self.dry_run = dry_run
        self.logger = logger
        self.cwd = cwd

    def run(
        self,
        args: Sequence[str],
        *,
        input_text: str | None = None,
        check: bool = True,
        capture: bool = False,
        mutates: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        display = format_command(args)
        if self.dry_run and mutates:
            self.logger.write(f"[dry-run] {display}")
            return subprocess.CompletedProcess(args, 0, "", "")

        self.logger.write(f"$ {display}")
        proc = subprocess.run(
            list(args),
            cwd=self.cwd,
            input=input_text,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
        if proc.stdout and not capture:
            self.logger.write(proc.stdout.rstrip())
        if proc.stderr and not capture:
            self.logger.write(proc.stderr.rstrip())
        if check and proc.returncode != 0:
            raise RunnerError(f"Command failed with exit code {proc.returncode}: {display}")
        return proc


def redact_secrets(message: str) -> str:
    redacted = message
    secret_markers = ("TOKEN", "SECRET", "PASSWORD", "PASS", "API_KEY", "CHAT_ID")
    for key, value in os.environ.items():
        if not value or len(value) < 4:
            continue
        if any(marker in key.upper() for marker in secret_markers):
            redacted = redacted.replace(value, "[redacted]")
    return redacted


def format_command(args: Sequence[str]) -> str:
    return " ".join(quote_arg(arg) for arg in args)


def quote_arg(arg: str) -> str:
    if not arg:
        return '""'
    if any(ch.isspace() for ch in arg):
        return '"' + arg.replace('"', '\\"') + '"'
    return arg


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local Codex agent task safely.")
    parser.add_argument("--task", required=True, help="Path to task markdown")
    parser.add_argument("--branch", required=True, help="Branch name to create")
    parser.add_argument("--create-pr", action="store_true", help="Create a GitHub PR with gh after pushing")
    parser.add_argument("--dry-run", action="store_true", help="Print mutating commands without running them")
    parser.add_argument("--pr-title", help="PR title; also used as commit message when set")
    parser.add_argument("--pr-body", help="PR body text")
    parser.add_argument(
        "--check-monitor",
        action="store_true",
        help="Also run monitor_5070_ti_v_2.py. This may send notifications depending on config/env.",
    )
    return parser.parse_args(argv)


def resolve_task_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = ROOT / path
    return path


def default_checks(include_monitor: bool = False) -> list[list[str]]:
    checks = [[sys.executable, "-m", "pytest", "-q"]]
    if (ROOT / "tools" / "smoke_dns.py").exists():
        checks.append([sys.executable, "tools/smoke_dns.py"])
    if include_monitor:
        checks.append([sys.executable, "monitor_5070_ti_v_2.py"])
    return checks


def ensure_git_repo(runner: CommandRunner) -> None:
    proc = runner.run(["git", "rev-parse", "--is-inside-work-tree"], capture=True)
    if proc.stdout.strip() != "true":
        raise RunnerError("Not inside a git working tree.")


def ensure_clean_worktree(runner: CommandRunner) -> None:
    proc = runner.run(["git", "status", "--porcelain"], capture=True)
    if proc.stdout.strip():
        raise RunnerError("Working tree is not clean. Commit or stash changes before running the agent.")


def has_changes(runner: CommandRunner) -> bool:
    proc = runner.run(["git", "status", "--porcelain"], capture=True)
    return bool(proc.stdout.strip())


def show_diff_summary(runner: CommandRunner) -> None:
    status = runner.run(["git", "status", "--short"], check=False, capture=True)
    diff = runner.run(["git", "diff", "--stat"], check=False, capture=True)
    runner.logger.write("Git change summary:")
    if status.stdout.strip():
        runner.logger.write(status.stdout.rstrip())
    if diff.stdout.strip():
        runner.logger.write(diff.stdout.rstrip())
    if not status.stdout.strip() and not diff.stdout.strip():
        runner.logger.write("No changes.")


def run_checks(runner: CommandRunner, checks: Iterable[Sequence[str]]) -> None:
    for check_cmd in checks:
        runner.run(check_cmd)


def run_workflow(args: argparse.Namespace, runner: CommandRunner) -> None:
    task_path = resolve_task_path(args.task)
    if not task_path.exists():
        raise RunnerError(f"Task file does not exist: {task_path}")
    task_text = task_path.read_text(encoding="utf-8")

    runner.logger.write(f"Agent run started: {datetime.now().isoformat(timespec='seconds')}")
    runner.logger.write(f"Task: {task_path}")
    runner.logger.write(f"Branch: {args.branch}")
    runner.logger.write(f"Log: {runner.logger.path if runner.logger._fh else 'console only'}")

    ensure_git_repo(runner)
    ensure_clean_worktree(runner)

    runner.run(["git", "checkout", "main"], mutates=True)
    runner.run(["git", "pull", "--ff-only"], mutates=True)
    runner.run(["git", "checkout", "-b", args.branch], mutates=True)

    runner.run(["codex", "exec", "--profile", "agent"], input_text=task_text, mutates=True)

    run_checks(runner, default_checks(args.check_monitor))
    show_diff_summary(runner)

    if not has_changes(runner):
        runner.logger.write("No diff after agent run; nothing to commit or push.")
        return

    runner.run(["git", "add", "-A"], mutates=True)
    commit_message = args.pr_title or f"Run agent task {task_path.stem}"
    runner.run(["git", "commit", "-m", commit_message], mutates=True)
    runner.run(["git", "push", "-u", "origin", args.branch], mutates=True)

    if args.create_pr:
        pr_title = args.pr_title or commit_message
        pr_body = args.pr_body or f"Automated local agent run for `{task_path.name}`."
        runner.run(
            ["gh", "pr", "create", "--base", "main", "--head", args.branch, "--title", pr_title, "--body", pr_body],
            mutates=True,
        )
    else:
        runner.logger.write("PR creation skipped. Re-run with --create-pr or create it manually after review.")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    logger = Logger()
    runner = CommandRunner(args.dry_run, logger)
    try:
        run_workflow(args, runner)
    except RunnerError as exc:
        logger.write(f"ERROR: {exc}")
        return 1
    finally:
        logger.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

