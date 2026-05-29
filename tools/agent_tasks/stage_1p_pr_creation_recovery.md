# Stage 1P: improve PR creation recovery

Goal: make agent runs easier to recover when code was committed and pushed but PR creation did not complete.

Change scope:
- Update `tools/agent_run.py` and/or `tools/agent_cycle.py` narrowly.
- Add tests for the recovery behavior.
- Do not change shopping monitor execution or notification credentials.

Work:
1. Inspect how `agent_run.py` handles a successful branch push followed by a PR creation failure.
2. Ensure the log clearly records:
   - branch name;
   - commit SHA;
   - suggested `gh pr create` command;
   - whether the worktree is clean.
3. If possible, have `agent_cycle.py` classify this as a review-needed state rather than a generic failed state when a branch with committed changes exists remotely.
4. Add tests for a pushed-branch/no-PR scenario so it does not look like lost work.

Validation:
- Run `\.venv\Scripts\python.exe -m pytest`.

PR:
- Title: `Improve agent PR creation recovery`
- Body: explain how pushed work without a PR is reported and recovered.
