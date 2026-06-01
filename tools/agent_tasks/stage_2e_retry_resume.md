# Task: Add retry/resume for transient agent cycle errors
## Context
Long tasks (C, D stages) risk hitting Codex rate limits or transient network errors. Currently
any error marks the task failed permanently. This task adds the infrastructure needed before
heavy work begins.
## Goal
Distinguish transient errors (rate limit HTTP 429, network timeout, connection reset) from
permanent errors (auth failure, bad task spec, git conflicts). Retry transient errors with
exponential backoff. Resume an interrupted cycle from the last saved checkpoint.
## Steps
1. In `tools/agent_cycle.py`, add a helper `classify_error(exc) -> Literal["transient", "permanent"]`.
   Transient: `urllib.error.URLError` with network/timeout message, `subprocess.TimeoutExpired`,
   HTTP 429/503 responses, common rate-limit strings ("rate limit", "too many requests").
   Permanent: everything else.
2. Add `exponential_backoff(attempt: int, base_sec: float = 5.0, cap_sec: float = 300.0) -> float`
   returning `min(base_sec * 2**attempt, cap_sec)`.
3. Wrap the Codex call in `run_task()` with up to 5 retry attempts for transient errors.
   Log each retry with attempt number, wait time, and error snippet.
4. After each successful step inside a task (branch created, code written, tests passed, PR created),
   write a checkpoint to `C:\ProgramData\MonitorAgent\agent-cycle-state.json` under the key
   `current_task_checkpoint`. On cycle start, if a checkpoint exists for the current task ID and
   the task is still `in_progress`, resume from that checkpoint instead of restarting.
5. On permanent error or retry exhaustion: set task to `failed`, clear checkpoint, log full error.
## Tests
Add to `tests/test_agent_cycle.py`:
- `test_classify_transient_urlopen_error` — URLError("Connection reset") → "transient"
- `test_classify_permanent_auth_error` — subprocess.CalledProcessError(1, "git", b"auth failed") → "permanent"
- `test_exponential_backoff_cap` — attempt=10 returns cap_sec, not more
- `test_retry_succeeds_on_third_attempt` — mock Codex call fails twice with transient, succeeds third
## Constraints
- Touch `tools/agent_cycle.py`, `tools/agent_run.py` (if needed), and `tests/`.
- Do NOT change queue.json format. Do NOT change task .md spec files.
- This touches agent core → PR will land in `needs_review`, not auto-merge. That is expected.
## Validation
Run `python -m pytest --tb=short -q`.
## PR
- Title: `Add retry/resume for transient agent cycle errors`
- Body: describe transient vs permanent classification, backoff params, checkpoint location, and retry limit.
