from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MaintenanceResult:
    path: Path
    original_bytes: int
    final_bytes: int
    original_records: int
    final_records: int
    rotated_to: Path | None = None
    dry_run: bool = False


def _file_size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


def _read_record_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def retain_recent_records(path: str | Path, keep_records: int, dry_run: bool = False) -> MaintenanceResult:
    if keep_records < 0:
        raise ValueError("keep_records must be >= 0")

    history_path = Path(path)
    original_bytes = _file_size(history_path)
    lines = _read_record_lines(history_path)
    kept_lines = lines[-keep_records:] if keep_records else []
    final_content = ("\n".join(kept_lines) + "\n") if kept_lines else ""

    if not dry_run and history_path.exists() and len(kept_lines) != len(lines):
        history_path.write_text(final_content, encoding="utf-8")

    final_bytes = len(final_content.encode("utf-8")) if dry_run else _file_size(history_path)
    return MaintenanceResult(
        path=history_path,
        original_bytes=original_bytes,
        final_bytes=final_bytes,
        original_records=len(lines),
        final_records=len(kept_lines),
        dry_run=dry_run,
    )


def _next_rotation_path(path: Path) -> Path:
    index = 1
    while True:
        candidate = path.with_name(f"{path.name}.{index}")
        if not candidate.exists():
            return candidate
        index += 1


def rotate_if_larger_than(path: str | Path, max_bytes: int, dry_run: bool = False) -> MaintenanceResult:
    if max_bytes < 0:
        raise ValueError("max_bytes must be >= 0")

    history_path = Path(path)
    original_bytes = _file_size(history_path)
    lines = _read_record_lines(history_path)
    should_rotate = history_path.exists() and original_bytes > max_bytes
    rotated_to = _next_rotation_path(history_path) if should_rotate else None

    if should_rotate and not dry_run:
        assert rotated_to is not None
        history_path.replace(rotated_to)
        history_path.write_text("", encoding="utf-8")

    final_bytes = 0 if should_rotate else original_bytes
    final_records = 0 if should_rotate else len(lines)
    return MaintenanceResult(
        path=history_path,
        original_bytes=original_bytes,
        final_bytes=final_bytes,
        original_records=len(lines),
        final_records=final_records,
        rotated_to=rotated_to,
        dry_run=dry_run,
    )


def _format_result(result: MaintenanceResult) -> str:
    lines = [
        f"Path: {result.path}",
        f"Records: {result.original_records} -> {result.final_records}",
        f"Bytes: {result.original_bytes} -> {result.final_bytes}",
    ]
    if result.rotated_to is not None:
        lines.append(f"Rotated to: {result.rotated_to}")
    if result.dry_run:
        lines.append("Dry run: no changes written")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Maintain a JSONL price history file.")
    parser.add_argument("path", nargs="?", default="price_history.jsonl", help="Path to price_history.jsonl")
    parser.add_argument("--keep-records", type=int, help="Keep only the most recent N JSONL records")
    parser.add_argument("--rotate-over-bytes", type=int, help="Rotate the file when it is larger than N bytes")
    parser.add_argument("--dry-run", action="store_true", help="Show the planned maintenance without writing changes")
    args = parser.parse_args(argv)

    actions = [args.keep_records is not None, args.rotate_over_bytes is not None]
    if sum(actions) != 1:
        parser.error("choose exactly one of --keep-records or --rotate-over-bytes")

    if args.keep_records is not None:
        result = retain_recent_records(args.path, args.keep_records, dry_run=args.dry_run)
    else:
        result = rotate_if_larger_than(args.path, args.rotate_over_bytes, dry_run=args.dry_run)

    print(_format_result(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
