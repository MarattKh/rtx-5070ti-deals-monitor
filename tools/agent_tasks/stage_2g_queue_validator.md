# Task: Final queue validation — tests, main cleanliness, source smoke-check, report
## Context
This is the last task in the current queue cycle. It validates that the entire queue ran cleanly
and summarises the state of the project for the operator.
## Goal
Run the full test suite, verify main is clean, check every enabled source returns a parseable
response or logs a clear reason why not, and write a summary report.
## Steps
1. Run `python -m pytest --tb=short -q` and capture output. Assert all tests pass; abort with
   `needs_review` if any test is red.
2. Run `git status` on main and confirm the working tree is clean. If dirty, abort `needs_review`.
3. For each source in `ENABLED_SOURCES` (from monitor_5070_ti_v_2.py):
   a. Call `module.parse_offers()` or `module.parse_offers_with_status()` with a short timeout.
   b. Record: source name, raw offer count, filtered offer count, blocked/error status.
   c. Any source returning 0 offers AND no explicit error: log as `dark (silent)`.
4. Write the summary as JSON to `C:\ProgramData\MonitorAgent\validation-report.json` with keys:
   `{ "timestamp_utc": "...", "tests_passed": N, "sources": [{name, raw, filtered, status}], "dark_sources": [...] }`
5. Also append a human-readable summary line to `docs/agent-runs/cycle-log.md`:
   `YYYY-MM-DD | stage_2g_queue_validator | tests=N passed | sources_live=X | dark=Y`
6. Create a PR with the updated `docs/agent-runs/cycle-log.md` only (the JSON report goes to
   ProgramData, not to git — it is a local runtime artifact).
## Constraints
- Do NOT add new Python modules or modify existing parsers in this task.
- Touch only `docs/agent-runs/cycle-log.md` in git. Runtime report goes to ProgramData only.
- If pytest fails or main is dirty: set task to `needs_review` immediately and do NOT create a PR.
## Validation
The task itself IS the validation run.
## PR
- Title: `Agent cycle log: queue validation summary`
- Body: paste the per-source table (name, raw count, filtered count, status).
