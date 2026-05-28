# Stage 1O: strengthen source status regression tests

Goal: improve regression coverage for blocked or unavailable retailer sources so reports stay honest.

Change scope:
- Prefer tests only.
- If a small parser/status bug is found while writing tests, fix it narrowly.
- Do not run shopping notification scripts.

Work:
1. Inspect existing DNS and Citilink blocked-status tests.
2. Add or improve tests for:
   - blocked source status is rendered as `blocked / reason` in source summary;
   - HTTP 401, 403, and 429 style failures are not reported as raw 0 / filtered 0;
   - normal successful parsing still reports raw and filtered counts.
3. Keep fixtures local and deterministic.

Validation:
- Run `\.venv\Scripts\python.exe -m pytest`.

PR:
- Title: `Strengthen source blocked status tests`
- Body: summarize regression coverage for blocked source reporting.
