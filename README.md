# monitor_5070ti

Полноценный мониторинг предложений **RTX 5070 Ti** по магазинам и маркетплейсам с фильтрацией, сигналами и отчетами.

## Agent stability contract

`tools/agent_run.py` owns checkout, commit, push and PR creation. Codex must only edit files in the prepared working tree. `tools/agent_cycle.py` reconciles a failed `agent_run.py` exit with GitHub before reporting `failed`: if a PR or pushed branch already exists, the task is recorded as review/recovery instead of a false failure.
