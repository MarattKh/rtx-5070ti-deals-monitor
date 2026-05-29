from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import agent_cycle


COUNT_STATUSES = ("completed", "failed", "needs_review")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show queued agent task status.")
    parser.add_argument("--queue", default=str(agent_cycle.DEFAULT_QUEUE_PATH), help="Path to queue.json")
    parser.add_argument("--state", default=str(agent_cycle.DEFAULT_STATE_PATH), help="Runtime state path")
    return parser.parse_args(argv)


def effective_status(queue_status: str, state_status: str) -> str:
    return state_status or queue_status


def build_rows(queue: list[dict[str, Any]], state: dict[str, Any]) -> list[dict[str, str]]:
    state_tasks = state.get("tasks", {})
    rows: list[dict[str, str]] = []
    for task in queue:
        task_id = str(task.get("id", ""))
        state_item = state_tasks.get(task_id, {}) if isinstance(state_tasks, dict) else {}
        if not isinstance(state_item, dict):
            state_item = {}

        rows.append(
            {
                "id": task_id,
                "queue_status": str(task.get("status", "pending") or "pending"),
                "state_status": str(state_item.get("status", "") or ""),
                "branch": str(task.get("branch") or state_item.get("branch") or ""),
                "pr_title": str(task.get("pr_title") or ""),
            }
        )
    return rows


def build_counts(queue: list[dict[str, Any]], state: dict[str, Any], rows: list[dict[str, str]]) -> dict[str, int]:
    counts = {
        "total": len(queue),
        "pending": sum(1 for row in rows if row["queue_status"] == "pending"),
        "runnable": len(agent_cycle.select_pending_tasks(queue, state, max_tasks=len(queue))),
        "completed": 0,
        "failed": 0,
        "needs_review": 0,
    }
    for row in rows:
        status = effective_status(row["queue_status"], row["state_status"])
        if status in COUNT_STATUSES:
            counts[status] += 1
    return counts


def format_table(rows: list[dict[str, str]]) -> list[str]:
    headers = {
        "id": "task id",
        "queue_status": "queue",
        "state_status": "state",
        "branch": "branch",
        "pr_title": "PR title",
    }
    keys = list(headers)
    widths = {
        key: max([len(headers[key]), *(len(row[key]) for row in rows)] or [len(headers[key])])
        for key in keys
    }
    header = "  ".join(headers[key].ljust(widths[key]) for key in keys)
    divider = "  ".join("-" * widths[key] for key in keys)
    lines = [header, divider]
    for row in rows:
        lines.append("  ".join(row[key].ljust(widths[key]) for key in keys))
    return lines


def format_status(queue: list[dict[str, Any]], state: dict[str, Any], *, state_missing: bool = False) -> str:
    rows = build_rows(queue, state)
    counts = build_counts(queue, state, rows)
    lines = [
        "Agent queue status",
        (
            "Counts: "
            f"total={counts['total']} "
            f"pending={counts['pending']} "
            f"runnable={counts['runnable']} "
            f"completed={counts['completed']} "
            f"failed={counts['failed']} "
            f"needs_review={counts['needs_review']}"
        ),
    ]
    if state_missing:
        lines.append("State: missing; treating all runtime state statuses as empty.")
    lines.append("")
    lines.extend(format_table(rows))
    return "\n".join(lines)


def load_state_for_status(path: Path) -> tuple[dict[str, Any], bool]:
    if not path.exists():
        return {"tasks": {}}, True
    return agent_cycle.load_state(path), False


def main(argv: Sequence[str] | None = None) -> int:
    agent_cycle.configure_stdio()
    args = parse_args(argv)
    queue_path = agent_cycle.resolve_path(args.queue)
    state_path = agent_cycle.resolve_path(args.state, base=Path.cwd())
    try:
        queue = agent_cycle.load_queue(queue_path)
        state, state_missing = load_state_for_status(state_path)
    except agent_cycle.CycleError as exc:
        agent_cycle.safe_console_write(f"ERROR: {exc}", stream=sys.stderr)
        return 1

    agent_cycle.safe_console_write(format_status(queue, state, state_missing=state_missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
