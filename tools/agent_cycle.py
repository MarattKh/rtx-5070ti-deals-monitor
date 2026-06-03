from __future__ import annotations

import argparse, json, locale, os, subprocess, sys, time, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import agent_notify
from tools.atomic_io import atomic_write_text

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUEUE_PATH = ROOT / "tools" / "agent_tasks" / "queue.json"
DEFAULT_STATE_PATH = Path(r"C:\ProgramData\MonitorAgent\agent-cycle-state.json")
DEFAULT_LOG_PATH = Path(r"C:\ProgramData\MonitorAgent\agent-cycle-last.log")
DEFAULT_LOCK_PATH = Path(r"C:\ProgramData\MonitorAgent\agent-cycle.lock")
LOCK_STALE_AFTER_SECONDS = 90 * 60
DEFAULT_NOTIFY_ON_EVENTS = ("needs_review", "failed", "auto_merge_denied", "dirty_worktree", "pr_created_without_merge", "cycle_completed_with_errors")
DEFAULT_NOTIFY_ON = ",".join(DEFAULT_NOTIFY_ON_EVENTS)
TERMINAL_RUNTIME_STATUSES = {"completed", "needs_review", "failed", "auto_merge_denied", "pr_created_without_merge"}
DANGEROUS_EXACT_PATHS = {"config.example.json", "config.json", "run_daily_report.bat", "run_monitor.bat", "run_monitor_browser.bat", "tools/agent_run.py", "tools/agent_cycle.py", "tools/agent_tasks/queue.json", "pyproject.toml", "requirements.txt", "requirements-dev.txt", "poetry.lock", "pdm.lock"}
DANGEROUS_DIR_PREFIXES = (".github/", "scheduler/", "system/")
DANGEROUS_PATH_MARKERS = ("secret", "env", "token", "credential", "key")
SAFE_DOC_EXACT_PATHS = {"readme.md"}
SAFE_DOC_DIR_PREFIXES = ("docs/", "doc/")
SAFE_DOC_SUFFIXES = (".md", ".rst", ".txt")
SAFE_TEST_DIR_PREFIXES = ("tests/", "test/")
SAFE_TEST_NAME_PREFIXES = ("test_",)
SAFE_TEST_NAME_SUFFIXES = ("_test.py",)

class CycleError(RuntimeError): pass

class CycleLock:
    def __init__(self, path: Path, token: str) -> None:
        self.path, self.token = path, token

def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        r = getattr(stream, "reconfigure", None)
        if r:
            try: r(errors="replace")
            except (OSError, ValueError): pass

def safe_console_write(message: str = "", *, stream=None) -> None:
    stream = stream or sys.stdout
    try:
        stream.write(message + "\n"); stream.flush()
    except UnicodeEncodeError:
        enc = getattr(stream, "encoding", None) or locale.getpreferredencoding(False) or "utf-8"
        stream.write(message.encode(enc, errors="replace").decode(enc, errors="replace") + "\n"); stream.flush()

class Logger:
    def __init__(self, path: Path = DEFAULT_LOG_PATH) -> None:
        self.path, self._fh = path, None
        try:
            path.parent.mkdir(parents=True, exist_ok=True); self._fh = path.open("w", encoding="utf-8")
        except OSError: self._fh = None
    def close(self) -> None:
        if self._fh: self._fh.close()
    def write(self, message: str = "") -> None:
        safe_console_write(message)
        if self._fh: self._fh.write(message + "\n"); self._fh.flush()

class CommandRunner:
    def __init__(self, dry_run: bool, logger: Logger, cwd: Path = ROOT) -> None:
        self.dry_run, self.logger, self.cwd = dry_run, logger, cwd
    def run(self, args: Sequence[str], *, check: bool = True, capture: bool = False, mutates: bool = False) -> subprocess.CompletedProcess[str]:
        display = format_command(args)
        if self.dry_run and mutates:
            self.logger.write(f"[dry-run] {display}"); return subprocess.CompletedProcess(args, 0, "", "")
        self.logger.write(f"$ {display}")
        try:
            p = subprocess.run(list(args), stdin=subprocess.DEVNULL, cwd=self.cwd, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=900)
        except subprocess.TimeoutExpired as exc:
            if exc.stdout: self.logger.write(exc.stdout.rstrip())
            if exc.stderr: self.logger.write(exc.stderr.rstrip())
            raise CycleError(f"Command timed out: {display}") from exc
        if p.stdout and not capture: self.logger.write(p.stdout.rstrip())
        if p.stderr and not capture: self.logger.write(p.stderr.rstrip())
        if check and p.returncode != 0: raise CycleError(f"Command failed with exit code {p.returncode}: {display}")
        return p

def format_command(args: Sequence[str]) -> str: return " ".join(quote_arg(str(a)) for a in args)
def quote_arg(arg: str) -> str: return '""' if not arg else ('"' + arg.replace('"', '\\"') + '"' if any(ch.isspace() for ch in arg) else arg)

def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run queued local agent tasks.")
    p.add_argument("--queue", default=str(DEFAULT_QUEUE_PATH)); p.add_argument("--once", action="store_true"); p.add_argument("--max-tasks", type=int, default=1)
    p.add_argument("--create-pr", action="store_true"); g = p.add_mutually_exclusive_group(); g.add_argument("--auto-merge-safe", action="store_true"); g.add_argument("--no-auto-merge", action="store_false", dest="auto_merge_safe")
    p.add_argument("--dry-run", action="store_true"); p.add_argument("--state"); p.add_argument("--log"); p.add_argument("--notify", action="store_true"); p.add_argument("--notify-test", action="store_true"); p.add_argument("--notify-on", default=DEFAULT_NOTIFY_ON)
    p.set_defaults(auto_merge_safe=False); return p.parse_args(argv)

def resolve_path(raw_path: str | Path, *, base: Path = ROOT) -> Path:
    path = Path(raw_path); return path if path.is_absolute() else base / path

def read_json(path: Path) -> Any: return json.loads(path.read_text(encoding="utf-8-sig"))

def load_queue(path: Path) -> list[dict[str, Any]]:
    try: raw = read_json(path)
    except FileNotFoundError as exc: raise CycleError(f"Queue file does not exist: {path}") from exc
    except json.JSONDecodeError as exc: raise CycleError(f"Queue file is not valid JSON: {path}: {exc}") from exc
    tasks = raw.get("tasks") if isinstance(raw, dict) else raw
    if not isinstance(tasks, list): raise CycleError("Queue JSON must be a list or an object with a tasks list.")
    for i, task in enumerate(tasks):
        if not isinstance(task, dict): raise CycleError(f"Queue task at index {i} is not an object.")
        if not task.get("id") or not task.get("task") or not task.get("branch"): raise CycleError(f"Queue task at index {i} must include id, task, and branch.")
    return tasks

def load_state(path: Path) -> dict[str, Any]:
    if not path.exists(): return {"tasks": {}}
    try: raw = read_json(path)
    except json.JSONDecodeError as exc: raise CycleError(f"State file is not valid JSON: {path}: {exc}") from exc
    if not isinstance(raw, dict): return {"tasks": {}}
    if not isinstance(raw.get("tasks"), dict): raw["tasks"] = {}
    return raw

def save_state(path: Path, state: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(state, ensure_ascii=False, indent=2) + "\n")

def select_pending_tasks(queue: list[dict[str, Any]], state: dict[str, Any], max_tasks: int) -> list[dict[str, Any]]:
    stopped = {tid for tid, item in state.get("tasks", {}).items() if isinstance(item, dict) and item.get("status") in TERMINAL_RUNTIME_STATUSES}
    out = []
    for t in queue:
        if t.get("status", "pending") == "pending" and t["id"] not in stopped: out.append(t)
        if len(out) >= max_tasks: break
    return out

def utc_timestamp() -> str: return datetime.now(timezone.utc).isoformat(timespec="seconds")

def _parse_lock_timestamp(raw: object) -> datetime | None:
    if not isinstance(raw, str): return None
    try: ts = datetime.fromisoformat(raw)
    except ValueError: return None
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)

def _read_lock(path: Path) -> dict[str, Any]:
    try: raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): return {}
    return raw if isinstance(raw, dict) else {}

def _pid_is_dead(pid: object) -> bool:
    try: pid_int = int(pid)
    except (TypeError, ValueError): return False
    if pid_int <= 0: return False
    try: os.kill(pid_int, 0)
    except ProcessLookupError: return True
    except (PermissionError, OSError): return False
    return False

def _lock_is_stale(info: dict[str, Any], *, now: datetime, stale_after_seconds: int) -> bool:
    ts = _parse_lock_timestamp(info.get("timestamp"))
    if ts and (now.astimezone(timezone.utc) - ts).total_seconds() > stale_after_seconds: return True
    return _pid_is_dead(info.get("pid"))

def acquire_cycle_lock(path: Path | None = None, *, stale_after_seconds: int = LOCK_STALE_AFTER_SECONDS, now: datetime | None = None) -> CycleLock | None:
    path = Path(path or DEFAULT_LOCK_PATH); now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc); token = uuid.uuid4().hex
    payload = json.dumps({"pid": os.getpid(), "timestamp": now.isoformat(timespec="seconds"), "token": token}, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            if not _lock_is_stale(_read_lock(path), now=now, stale_after_seconds=stale_after_seconds): return None
            try: path.unlink()
            except FileNotFoundError: pass
            except OSError: return None
            continue
        try: os.write(fd, payload.encode("utf-8"))
        finally: os.close(fd)
        return CycleLock(path, token)

def release_cycle_lock(lock: CycleLock | None) -> None:
    if not lock: return
    info = _read_lock(lock.path)
    if info.get("token") != lock.token: return
    try: lock.path.unlink()
    except FileNotFoundError: pass

def update_task_state(state: dict[str, Any], task: dict[str, Any], *, status: str, result: str, pr: dict[str, Any] | None = None, changed_files: list[str] | None = None, details: dict[str, object] | None = None) -> None:
    item = {"status": status, "branch": task["branch"], "pr_url": pr.get("url") if pr else None, "pr_number": pr.get("number") if pr else None, "updated_at": utc_timestamp(), "result": result, "changed_files": changed_files or []}
    if details: item.update(details)
    state.setdefault("tasks", {})[task["id"]] = item

def build_agent_run_command(task: dict[str, Any], *, create_pr: bool, dry_run: bool) -> list[str]:
    cmd = [sys.executable, str(ROOT / "tools" / "agent_run.py"), "--task", str(resolve_path(task["task"])), "--branch", str(task["branch"]), "--pr-title", str(task.get("pr_title") or task["id"]), "--pr-body", str(task.get("pr_body") or f"Automated queued agent task `{task['id']}`.")]
    if create_pr: cmd.append("--create-pr")
    if dry_run: cmd.append("--dry-run")
    return cmd

def retry(runner: CommandRunner, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    last = None
    for i in range(3):
        last = runner.run(args, check=False, capture=True)
        if last.returncode == 0: return last
        if i < 2: time.sleep(0.5 * (2 ** i))
    assert last is not None; return last

def discover_pr(runner: CommandRunner, branch: str) -> dict[str, Any] | None:
    p = retry(runner, ["gh", "pr", "view", branch, "--json", "number,url,state,mergeable"])
    if p.returncode != 0 or not p.stdout.strip(): return None
    try: raw = json.loads(p.stdout)
    except json.JSONDecodeError: return None
    return raw if isinstance(raw, dict) else None

def discover_remote_branch_sha(runner: CommandRunner, branch: str) -> str | None:
    p = retry(runner, ["git", "ls-remote", "--heads", "origin", branch])
    return p.stdout.split()[0] if p.returncode == 0 and p.stdout.strip() else None

def build_recovery_pr_create_command(task: dict[str, Any]) -> list[str]:
    return ["gh", "pr", "create", "--base", "main", "--head", str(task["branch"]), "--title", str(task.get("pr_title") or task["id"]), "--body", str(task.get("pr_body") or f"Automated queued agent task `{task['id']}`.")]

def check_dirty_worktree(runner: CommandRunner) -> str: return runner.run(["git", "status", "--porcelain"], check=False, capture=True).stdout.strip()

def pushed_branch_recovery_details(runner: CommandRunner, task: dict[str, Any]) -> dict[str, object] | None:
    sha = discover_remote_branch_sha(runner, task["branch"])
    if not sha: return None
    return {"branch": task["branch"], "commit_sha": sha, "suggested_pr_command": format_command(build_recovery_pr_create_command(task)), "worktree_clean": "no" if check_dirty_worktree(runner) else "yes"}

def format_pushed_branch_recovery_result(details: dict[str, object], error: Exception) -> str:
    return f"agent_run failed after pushing branch; no PR was recorded. branch={details['branch']} commit_sha={details['commit_sha']} worktree_clean={details['worktree_clean']} suggested_pr_command={details['suggested_pr_command']} original_error={error}"

def list_pr_changed_files(runner: CommandRunner, pr_number: int | str) -> list[str]: return [x.strip() for x in runner.run(["gh", "pr", "diff", str(pr_number), "--name-only"], check=True, capture=True).stdout.splitlines() if x.strip()]
def _norm(path: str) -> str:
    p = path.replace("\\", "/").lower()
    while p.startswith("./"): p = p[2:]
    return p

def is_dangerous_path(path: str, *, allow_dependency_files: bool = False) -> bool:
    n = _norm(path); name = Path(n).name
    return n in DANGEROUS_EXACT_PATHS or any(n.startswith(p) for p in DANGEROUS_DIR_PREFIXES) or any(m in n for m in DANGEROUS_PATH_MARKERS) or name in {"taskschd.xml", "scheduled_task.xml"} or "scheduler" in n or "systemd" in n or "windows-service" in n or (not allow_dependency_files and (n.endswith(".toml") or "requirements" in name))

def is_documentation_path(path: str) -> bool:
    n = _norm(path); return n in SAFE_DOC_EXACT_PATHS or (n.startswith(SAFE_DOC_DIR_PREFIXES) and n.endswith(SAFE_DOC_SUFFIXES))
def is_test_path(path: str) -> bool:
    n = _norm(path); name = Path(n).name; return n.startswith(SAFE_TEST_DIR_PREFIXES) or name.startswith(SAFE_TEST_NAME_PREFIXES) or name.endswith(SAFE_TEST_NAME_SUFFIXES)
def is_low_risk_auto_merge_path(path: str) -> bool: return is_documentation_path(path) or is_test_path(path)

def resolve_mergeable(runner: CommandRunner, pr: dict[str, Any], *, max_attempts: int = 6, delay: float = 2.5) -> dict[str, Any]:
    for attempt in range(max_attempts):
        if str(pr.get("mergeable", "")).upper() not in {"", "UNKNOWN"}: return pr
        if attempt < max_attempts - 1:
            time.sleep(delay)
            refreshed = discover_pr(runner, str(pr["number"]))
            if refreshed: pr = refreshed
    return pr

def evaluate_auto_merge(pr: dict[str, Any] | None, changed_files: list[str], *, allow_dependency_files: bool = False) -> tuple[bool, str]:
    if not pr: return False, "PR was not discoverable"
    if str(pr.get("state", "")).upper() != "OPEN": return False, "PR is not open"
    if str(pr.get("mergeable", "")).upper() not in {"MERGEABLE", "TRUE"}: return False, f"PR is not mergeable: {pr.get('mergeable') or 'unknown'}"
    bad = [p for p in changed_files if is_dangerous_path(p, allow_dependency_files=allow_dependency_files)]
    return (False, "dangerous files changed: " + ", ".join(bad)) if bad else (True, "safe to merge")

def auto_merge_pr(runner: CommandRunner, pr_number: int | str) -> None:
    runner.run(["gh", "pr", "merge", str(pr_number), "--merge", "--delete-branch"], mutates=True); runner.run(["git", "checkout", "main"], mutates=True); runner.run(["git", "pull", "--ff-only"], mutates=True)

def build_notifier(args: argparse.Namespace) -> agent_notify.Notifier:
    events = set(agent_notify.EVENTS) if getattr(args, "notify_test", False) else agent_notify.parse_notify_events(getattr(args, "notify_on", "all"))
    return agent_notify.Notifier(agent_notify.load_config(), enabled=bool(getattr(args, "notify", False) or getattr(args, "notify_test", False)), events=events)

SUGGESTED_ACTIONS = {"needs_review": "Review PR manually and decide whether to merge.", "failed": "Open the task log, inspect the failure, and rerun or fix manually.", "auto_merge_denied": "Review the PR manually because auto-merge policy denied it.", "dirty_worktree": "Inspect local changes and clean or commit the worktree.", "pr_created_without_merge": "Review the created PR and merge manually if acceptable.", "cycle_completed_with_errors": "Inspect cycle log/state and failed task entries."}

def _notification_value(v: object) -> str:
    if v is None: return ""
    if isinstance(v, Path): return str(v)
    if isinstance(v, (list, tuple, set)): return ", ".join(str(x) for x in v) if v else "(none)"
    return str(v)
def _notification_task_id(title: str) -> str:
    p = title.split(); return p[1] if len(p) >= 2 and p[0] == "Task" else "cycle"

def build_intervention_notification_details(event: str, title: str, details: dict[str, object] | None, logger: Logger) -> dict[str, object]:
    raw = dict(details or {}); status = _notification_value(raw.get("status"))
    if not status or "\n" in status or len(status) > 80: status = event
    payload = {"task_id": _notification_value(raw.get("task_id") or raw.get("task") or _notification_task_id(title)), "status": status, "reason": _notification_value(raw.get("reason") or raw.get("result") or raw.get("error") or raw.get("status") or title), "pr_url": _notification_value(raw.get("pr_url") or raw.get("pr")), "changed_files": _notification_value(raw.get("changed_files")), "log_path": _notification_value(getattr(logger, "path", "")), "state_path": _notification_value(raw.get("state_path") or raw.get("state")), "suggested_action": SUGGESTED_ACTIONS.get(event, "Inspect the agent log and state file.")}
    for k, v in raw.items():
        if k not in {"task_id", "task", "status", "reason", "result", "error", "pr_url", "pr", "changed_files", "state_path", "state"}: payload[k] = _notification_value(v)
    return payload

def notify_event(notifier: agent_notify.Notifier, logger: Logger, event: str, title: str, details: dict[str, object] | None = None) -> bool:
    try: sent = notifier.send(event, title, build_intervention_notification_details(event, title, details, logger))
    except agent_notify.NotifyError as exc: logger.write(f"Notification failed for {event}: {exc}"); return False
    if sent: logger.write(f"Notification sent: {event}")
    return sent

def notify_review(notifier, logger, task, event, title, details):
    notify_event(notifier, logger, event, title, details)
    if event != "needs_review": notify_event(notifier, logger, "needs_review", f"Task {task['id']} needs review", details)

def classify_pr_after_agent_run(state, task, *, pr, args, runner, notifier, state_path, result_prefix):
    changed_files: list[str] = []
    if args.auto_merge_safe and pr:
        pr = resolve_mergeable(runner, pr); changed_files = list_pr_changed_files(runner, pr["number"]); ok, reason = evaluate_auto_merge(pr, changed_files); runner.logger.write(f"Auto-merge decision for {task['id']}: {reason}")
        if ok: auto_merge_pr(runner, pr["number"]); update_task_state(state, task, status="completed", result="merged", pr=pr, changed_files=changed_files); return
        update_task_state(state, task, status="needs_review", result=reason, pr=pr, changed_files=changed_files); notify_review(notifier, runner.logger, task, "auto_merge_denied", f"Task {task['id']} PR was not auto-merged", {"task_id": task["id"], "branch": task["branch"], "pr": pr.get("url"), "reason": reason, "changed_files": changed_files, "state": state_path}); return
    status = "needs_review" if args.create_pr else "completed"; update_task_state(state, task, status=status, result=result_prefix, pr=pr, changed_files=changed_files)
    if status == "needs_review": notify_review(notifier, runner.logger, task, "pr_created_without_merge", f"Task {task['id']} created a PR without merge", {"task_id": task["id"], "branch": task["branch"], "pr": pr.get("url") if pr else None, "state": state_path, "reason": result_prefix if result_prefix != "agent_run succeeded" else "PR created without merge", "changed_files": changed_files})

def recover_after_agent_run_failure(state, task, *, error, args, runner, notifier, state_path) -> bool:
    if not args.create_pr: return False
    pr = discover_pr(runner, task["branch"])
    if pr:
        result = f"recovered after agent_run failure: existing PR found; original_error={error}"
        classify_pr_after_agent_run(state, task, pr=pr, args=args, runner=runner, notifier=notifier, state_path=state_path, result_prefix=result); runner.logger.write(f"Task {task['id']}: recovered from agent_run failure via existing PR"); return True
    details = pushed_branch_recovery_details(runner, task)
    if details:
        result = format_pushed_branch_recovery_result(details, error); update_task_state(state, task, status="pr_created_without_merge", result=result, details=details); runner.logger.write(f"Task {task['id']}: recovered from agent_run failure via pushed branch"); notify_review(notifier, runner.logger, task, "pr_created_without_merge", f"Task {task['id']} needs PR recovery", {"task_id": task["id"], "state": state_path, "reason": result, **details}); return True
    return False

def run_cycle(args: argparse.Namespace, runner: CommandRunner) -> int:
    notifier = build_notifier(args); queue_path = resolve_path(args.queue); state_path = resolve_path(args.state, base=Path.cwd()) if args.state else DEFAULT_STATE_PATH
    queue, state = load_queue(queue_path), load_state(state_path); tasks = select_pending_tasks(queue, state, args.max_tasks)
    runner.logger.write(f"Agent cycle started: {utc_timestamp()}"); runner.logger.write(f"Queue: {queue_path}"); runner.logger.write(f"State: {state_path}"); runner.logger.write(f"Selected tasks: {len(tasks)}")
    errors = 0
    for task in tasks:
        runner.logger.write(f"Task {task['id']}: running on branch {task['branch']}")
        try: runner.run(build_agent_run_command(task, create_pr=args.create_pr, dry_run=args.dry_run), mutates=True)
        except CycleError as exc:
            if recover_after_agent_run_failure(state, task, error=exc, args=args, runner=runner, notifier=notifier, state_path=state_path): save_state(state_path, state); continue
            errors += 1; update_task_state(state, task, status="failed", result=str(exc)); save_state(state_path, state); notify_event(notifier, runner.logger, "failed", f"Task {task['id']} failed", {"task_id": task["id"], "branch": task["branch"], "result": str(exc), "state": state_path}); continue
        classify_pr_after_agent_run(state, task, pr=discover_pr(runner, task["branch"]) if args.create_pr else None, args=args, runner=runner, notifier=notifier, state_path=state_path, result_prefix="agent_run succeeded"); save_state(state_path, state)
    if errors: notify_event(notifier, runner.logger, "cycle_completed_with_errors", "Agent cycle completed with errors", {"errors": errors, "state": state_path}); return 1
    return 0

def main(argv: Sequence[str] | None = None) -> int:
    configure_stdio(); args = parse_args(argv); logger = Logger(resolve_path(args.log, base=Path.cwd()) if args.log else DEFAULT_LOG_PATH); runner = CommandRunner(args.dry_run, logger)
    lock = None
    try:
        if args.notify_test:
            return 0 if notify_event(build_notifier(args), logger, "cycle_completed_with_errors", "Agent notification test", {"log": logger.path, "test": True}) else 1
        lock = acquire_cycle_lock()
        if not lock:
            logger.write("another cycle running"); return 0
        return run_cycle(args, runner)
    except (CycleError, agent_notify.NotifyError) as exc:
        logger.write(f"ERROR: {exc}"); return 1
    finally:
        release_cycle_lock(lock); logger.close()

if __name__ == "__main__": raise SystemExit(main())






