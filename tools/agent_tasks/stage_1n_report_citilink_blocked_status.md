# Stage 1N: Citilink blocked status in reports

Goal: make Source summary report `Ситилинк: blocked / 429 too many requests` when Citilink is blocked, instead of showing `raw 0 / filtered 0`.

Constraints:

- Keep the PR small and focused.
- Do not add browser automation, proxies, credentials, or anti-bot bypass.
- Do not run `monitor_5070_ti_v_2.py` by default.
- Do not change notification sending behavior except for source summary text when blocked.
- Do not commit, push, create PR, or merge; `tools/agent_run.py` handles git and PR after checks.

Implementation notes:

- Follow the existing DNS blocked-status shape where practical: `offers`, `blocked`, `block_reason`, `warnings`, and `errors`.
- Add a conservative Citilink status path so HTTP 429 or obvious blocked HTML can be represented in source stats.
- Update report and Telegram summary tests so `Ситилинк: blocked / 429 too many requests` appears and `Ситилинк: raw 0 / filtered 0` does not appear for a blocked Citilink response.
- Avoid broad parser rewrites.

Verification:

- Run `python -m pytest -q`.
- Do not manually run the monitor unless the user explicitly asks.
