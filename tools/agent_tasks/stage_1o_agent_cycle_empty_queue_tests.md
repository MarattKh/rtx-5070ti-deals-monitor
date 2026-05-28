# Stage 1O: strengthen agent-cycle empty-queue tests

Goal: improve confidence that the scheduled Lenovo agent does nothing expensive when there is no runnable work.

Change scope:
- Prefer tests only.
- If a small bug is found while writing tests, fix it in the narrowest possible place.
- Do not run shopping notification scripts.

Work:
1. Inspect current tests around `tools/agent_cycle.py`.
2. Add or improve pytest coverage for:
   - empty queue selects zero tasks;
   - pending queue entries already completed in runtime state are skipped;
   - `--max-tasks 1` limits one runnable task;
   - no Codex command is executed when selected task count is zero.
3. Keep tests deterministic and offline.

Validation:
- Run `\.venv\Scripts\python.exe -m pytest`.

PR:
- Title: `Strengthen agent cycle empty queue tests`
- Body: summarize the new regression coverage and confirm that empty queue mode does not call Codex.
