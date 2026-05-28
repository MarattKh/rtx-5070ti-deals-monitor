# Stage 1N: Durable price history

Goal: add a simple durable history log for filtered offers so price changes can be inspected later.

Constraints:

- Keep the implementation conservative and separate from Telegram notifications.
- Do not add a database or external dependency.
- Do not send notifications from the history code.
- Do not run `monitor_5070_ti_v_2.py` by default.
- Do not commit, push, create PR, or merge; `tools/agent_run.py` handles git and PR after checks.

Implementation notes:

- Prefer a JSONL file such as `price_history.jsonl` or another small append-only local artifact.
- Record enough fields to audit an offer over time: timestamp, source, title, price, currency, url, condition, availability, and signal.
- Keep history writing near report saving, but make it easy to test in isolation.
- Treat history as best-effort local persistence; report generation and notifications should not depend on it succeeding.
- Add focused tests using a temporary directory.

Verification:

- Run `python -m pytest -q`.
- Do not manually run the monitor unless the user explicitly asks.
