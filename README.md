# monitor_5070ti

Полноценный мониторинг предложений **RTX 5070 Ti** по магазинам и маркетплейсам с фильтрацией, сигналами и отчетами.


## Price history maintenance

The monitor appends to `price_history.jsonl` by default and does not prune old records automatically. To keep the file bounded, run the explicit maintenance helper when needed:

```powershell
.\.venv\Scripts\python.exe -m tools.price_history_maintenance price_history.jsonl --keep-records 5000
.\.venv\Scripts\python.exe -m tools.price_history_maintenance price_history.jsonl --rotate-over-bytes 10485760
```

Use `--dry-run` with either option to preview the record and byte counts without writing changes. Rotation writes the current file to the next available numbered sibling such as `price_history.jsonl.1` and creates a fresh empty history file.
