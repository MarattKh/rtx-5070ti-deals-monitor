from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import agent_cycle
from tools.atomic_io import atomic_write_text


class MarkCompletedError(RuntimeError):
    pass


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mark an agent queue task as completed.")
    parser.add_argument("task_id", help="Task id to mark completed")
    parser.add_argument("--queue", default=str(agent_cycle.DEFAULT_QUEUE_PATH), help="Path to queue.json")
    parser.add_argument("--dry-run", action="store_true", help="Show the change without writing queue.json")
    return parser.parse_args(argv)


def load_queue_document(path: Path) -> dict[str, Any]:
    try:
        raw = agent_cycle.read_json(path)
    except FileNotFoundError as exc:
        raise MarkCompletedError(f"Queue file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise MarkCompletedError(f"Queue file is not valid JSON: {path}: {exc}") from exc

    if not isinstance(raw, dict) or not isinstance(raw.get("tasks"), list):
        raise MarkCompletedError("Queue JSON must be an object with a tasks list.")
    for index, task in enumerate(raw["tasks"]):
        if not isinstance(task, dict):
            raise MarkCompletedError(f"Queue task at index {index} is not an object.")
    return raw


def mark_completed(queue_doc: dict[str, Any], task_id: str) -> tuple[str, str]:
    for task in queue_doc["tasks"]:
        if str(task.get("id", "")) == task_id:
            previous_status = str(task.get("status", "pending") or "pending")
            task["status"] = "completed"
            return previous_status, "completed"
    raise MarkCompletedError(f"Task id not found in queue: {task_id}")


def save_queue_document(path: Path, queue_doc: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(queue_doc, ensure_ascii=False, indent=2) + "\n")


def complete_task(queue_path: Path, task_id: str, *, dry_run: bool = False) -> tuple[str, str]:
    queue_doc = load_queue_document(queue_path)
    previous_status, new_status = mark_completed(queue_doc, task_id)
    if not dry_run:
        save_queue_document(queue_path, queue_doc)
    return previous_status, new_status


def main(argv: Sequence[str] | None = None) -> int:
    agent_cycle.configure_stdio()
    args = parse_args(argv)
    queue_path = agent_cycle.resolve_path(args.queue)
    try:
        previous_status, new_status = complete_task(queue_path, args.task_id, dry_run=args.dry_run)
    except MarkCompletedError as exc:
        agent_cycle.safe_console_write(f"ERROR: {exc}", stream=sys.stderr)
        return 1

    prefix = "[dry-run] " if args.dry_run else ""
    agent_cycle.safe_console_write(f"{prefix}{args.task_id}: {previous_status} -> {new_status} in {queue_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
