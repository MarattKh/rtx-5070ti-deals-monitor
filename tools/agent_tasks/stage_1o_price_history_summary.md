# Stage 1O: add price history summary helper

Goal: make `price_history.jsonl` useful for quick local review, not only as a raw log.

Change scope:
- Add a small helper under `tools/`, for example `tools/price_history_summary.py`.
- Add deterministic tests with temporary JSONL files.
- Do not change notification sending behavior.
- Do not run shopping notification scripts.

Work:
1. Read a JSONL price history file path from an argument, defaulting to `price_history.jsonl`.
2. Print a concise summary:
   - number of records;
   - best current known price by source;
   - best overall price;
   - latest timestamp;
   - count by signal label.
3. Ignore invalid JSON lines with a warning count rather than crashing.
4. Keep the script offline and UTF-8 safe.

Validation:
- Run `\.venv\Scripts\python.exe -m pytest`.

PR:
- Title: `Add price history summary helper`
- Body: explain how the helper turns the durable offer log into a quick review summary.
