# Stage 1O: add queue/state hygiene command

Goal: make it easier to see which queue tasks are runnable, completed, or stuck without manually opening JSON files.

Change scope:
- Add a small local helper under `tools/`, for example `tools/agent_queue_status.py`.
- Add tests for the helper.
- Do not modify scheduler setup or notification configuration.
- Do not run shopping notification scripts.

Work:
1. Read `tools/agent_tasks/queue.json` and the runtime state path used by `agent_cycle.py`.
2. Print a concise status table or plain text summary with task id, queue status, state status, branch, and PR title.
3. Include counts: total, pending, runnable, completed, failed, needs_review.
4. Handle missing state file gracefully.
5. Keep output UTF-8 safe on Windows.

Validation:
- Run `\.venv\Scripts\python.exe -m pytest`.

PR:
- Title: `Add agent queue status helper`
- Body: explain that this helps check what the autonomous agent will pick up next.
