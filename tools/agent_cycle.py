from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUEUE_PATH = ROOT / "tools" / "agent_tasks" / "queue.json"
DEFAULT_STATE_PATH = Path(r"C:\ProgramData\MonitorAgent\agent-cycle-state.json")
DEFAULT_LOG_PATH = Path(r"C:\ProgramData\MonitorAgent\agent-cycle-last.log")

DANGEROUS_EXACT_PATHS = {
    "tools/agent_run.py",
    "tools/agent_cycle.py",
    "tools/agent_tasks/queue.json",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "poetry.lock",
    "pdm.lock",
}
DANGEROUS_DIR_PREFIXES = (".github/", "scheduler/", "system/")
DANGEROUS_PATH_MARKERS = ("secret", "env", "token", "credential", "key")


class CycleError(RuntimeError):
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
            raise CycleError(f"Command failed with exit code {proc.returncode}: {display}")
        return proc


def format_command(args: Sequence[str]) -> str:
    return " ".join(quote_arg(str(arg)) for arg in args)


def quote_arg(arg: str) -> str:
    if not arg:
        return '""'
    if any(ch.isspace() for ch in arg):
        return '"' + arg.replace('"', '\\"') + '"'
    return arg


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run queued local agent tasks.")
    parser.add_argument("--queue", default=str(DEFAULT_QUEUE_PATH), help="Path to queue.json")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    parser.add_argument("--max-tasks", type=int, default=1, help="Maximum tasks to process in this run")
    parser.add_argument("--create-pr", action="store_true", help="Ask agent_run.py to create PRs")
    auto_merge = parser.add_mutually_exclusive_group()
    auto_merge.add_argument("--auto-merge-safe", action="store_true", help="Merge safe PRs after checks")
    auto_merge.add_argument("--no-auto-merge", action="store_false", dest="auto_merge_safe", help="Disable auto merge")
    parser.add_argument("--dry-run", action="store_true", help="Print mutating commands without running them")
    parser.add_argument("--state", help="Runtime state path")
    parser.add_argument("--log", help="Log path")
    parser.set_defaults(auto_merge_safe=False)
    return parser.parse_args(argv)


def resolve_path(raw_path: str | Path, *, base: Path = ROOT) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = base / path
    return path


def load_queue(path: Path) -> list[dict[str, Any]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CycleError(f"Queue file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CycleError(f"Queue file is not valid JSON: {path}: {exc}") from exc

    tasks = raw.get("tasks") if isinstance(raw, dict) else raw
    if not isinstance(tasks, list):
        raise CycleError("Queue JSON must be a list or an object with a tasks list.")

    normalized: list[dict[str, Any]] = []
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            raise CycleError(f"Queue task at index {index} is not an object.")
        if not task.get("id") or not task.get("task") or not task.get("branch"):
            raise CycleError(f"Queue task at index {index} must include id, task, and branch.")
        normalized.append(task)
    return normalized


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"tasks": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CycleError(f"State file is not valid JSON: {path}: {exc}") from exc
    if not isinstance(raw, dict):
        return {"tasks": {}}
    if not isinstance(raw.get("tasks"), dict):
        raw["tasks"] = {}
    return raw


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def select_pending_tasks(queue: list[dict[str, Any]], state: dict[str, Any], max_tasks: int) -> list[dict[str, Any]]:
    completed = {
        task_id
        for task_id, item in state.get("tasks", {}).items()
        if isinstance(item, dict) and item.get("status") == "completed"
    }
    pending: list[dict[str, Any]] = []
    for task in queue:
        if task.get("status", "pending") != "pending":
            continue
        if task["id"] in completed:
            continue
        pending.append(task)
        if len(pending) >= max_tasks:
            break
    return pending


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def update_task_state(
    state: dict[str, Any],
    task: dict[str, Any],
    *,
    status: str,
    result: str,
    pr: dict[str, Any] | None = None,
    changed_files: list[str] | None = None,
) -> None:
    state.setdefault("tasks", {})[task["id"]] = {
        "status": status,
        "branch": task["branch"],
        "pr_url": pr.get("url") if pr else None,
        "pr_number": pr.get("number") if pr else None,
        "updated_at": utc_timestamp(),
        "result": result,
        "changed_files": changed_files or [],
    }


def build_agent_run_command(task: dict[str, Any], *, create_pr: bool, dry_run: bool) -> list[str]:
    command = [
        sys.executable,
        str(ROOT / "tools" / "agent_run.py"),
        "--task",
        str(resolve_path(task["task"])),
        "--branch",
        str(task["branch"]),
        "--pr-title",
        str(task.get("pr_title") or task["id"]),
        "--pr-body",
        str(task.get("pr_body") or f"Automated queued agent task `{task['id']}`."),
    ]
    if create_pr:
        command.append("--create-pr")
    if dry_run:
        command.append("--dry-run")
    return command


def discover_pr(runner: CommandRunner, branch: str) -> dict[str, Any] | None:
    proc = runner.run(["gh", "pr", "view", branch, "--json", "number,url,state,mergeable"], check=False, capture=True)
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        raw = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    return raw if isinstance(raw, dict) else None


def list_pr_changed_files(runner: CommandRunner, pr_number: int | str) -> list[str]:
    proc = runner.run(["gh", "pr", "diff", str(pr_number), "--name-only"], check=True, capture=True)
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def is_dangerous_path(path: str, *, allow_dependency_files: bool = False) -> bool:
    normalized = path.replace("\\", "/").lower()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    name = Path(normalized).name

    if normalized in DANGEROUS_EXACT_PATHS:
        return True
    if any(normalized.startswith(prefix) for prefix in DANGEROUS_DIR_PREFIXES):
        return True
    if any(marker in normalized for marker in DANGEROUS_PATH_MARKERS):
        return True
    if name in {"taskschd.xml", "scheduled_task.xml"}:
        return True
    if "scheduler" in normalized or "systemd" in normalized or "windows-service" in normalized:
        return True
    if not allow_dependency_files and (normalized.endswith(".toml") or "requirements" in name):
        return True
    return False


def evaluate_auto_merge(
    pr: dict[str, Any] | None,
    changed_files: list[str],
    *,
    allow_dependency_files: bool = False,
) -> tuple[bool, str]:
    if not pr:
        return False, "PR was not discoverable"
    if str(pr.get("state", "")).upper() != "OPEN":
        return False, "PR is not open"
    if str(pr.get("mergeable", "")).upper() not in {"MERGEABLE", "TRUE"}:
        return False, f"PR is not mergeable: {pr.get('mergeable') or 'unknown'}"

    dangerous = [path for path in changed_files if is_dangerous_path(path, allow_dependency_files=allow_dependency_files)]
    if dangerous:
        return False, "dangerous files changed: " + ", ".join(dangerous)
    return True, "safe to merge"


def auto_merge_pr(runner: CommandRunner, pr_number: int | str) -> None:
    runner.run(["gh", "pr", "merge", str(pr_number), "--merge", "--delete-branch"], mutates=True)
    runner.run(["git", "checkout", "main"], mutates=True)
    runner.run(["git", "pull", "--ff-only"], mutates=True)


def run_cycle(args: argparse.Namespace, runner: CommandRunner) -> int:
    queue_path = resolve_path(args.queue)
    state_path = resolve_path(args.state, base=Path.cwd()) if args.state else DEFAULT_STATE_PATH
    queue = load_queue(queue_path)
    state = load_state(state_path)
    tasks = select_pending_tasks(queue, state, args.max_tasks)

    runner.logger.write(f"Agent cycle started: {utc_timestamp()}")
    runner.logger.write(f"Queue: {queue_path}")
    runner.logger.write(f"State: {state_path}")
    runner.logger.write(f"Selected tasks: {len(tasks)}")

    for task in tasks:
        runner.logger.write(f"Task {task['id']}: running on branch {task['branch']}")
        try:
            runner.run(build_agent_run_command(task, create_pr=args.create_pr, dry_run=args.dry_run), mutates=True)
        except CycleError as exc:
            update_task_state(state, task, status="failed", result=str(exc))
            save_state(state_path, state)
            runner.logger.write(f"Task {task['id']}: failed")
            continue

        pr = discover_pr(runner, task["branch"]) if args.create_pr else None
        changed_files: list[str] = []

        if args.auto_merge_safe and pr:
            changed_files = list_pr_changed_files(runner, pr["number"])
            should_merge, reason = evaluate_auto_merge(pr, changed_files)
            runner.logger.write(f"Auto-merge decision for {task['id']}: {reason}")
            if should_merge:
                auto_merge_pr(runner, pr["number"])
                update_task_state(state, task, status="completed", result="merged", pr=pr, changed_files=changed_files)
            else:
                update_task_state(state, task, status="needs_review", result=reason, pr=pr, changed_files=changed_files)
        else:
            status = "needs_review" if args.create_pr else "completed"
            update_task_state(state, task, status=status, result="agent_run succeeded", pr=pr, changed_files=changed_files)

        save_state(state_path, state)

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    log_path = resolve_path(args.log, base=Path.cwd()) if args.log else DEFAULT_LOG_PATH
    logger = Logger(log_path)
    runner = CommandRunner(args.dry_run, logger)
    try:
        return run_cycle(args, runner)
    except CycleError as exc:
        logger.write(f"ERROR: {exc}")
        return 1
    finally:
        logger.close()


if __name__ == "__main__":
    raise SystemExit(main())


