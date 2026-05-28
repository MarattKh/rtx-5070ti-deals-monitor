# Stage 1N: Citilink diagnostics

Goal: diagnose why Citilink currently reports raw 0 / filtered 0, without broad parser rewrites.

Constraints:

- Keep the PR small and focused.
- Add `tools/smoke_citilink.py`.
- Do not modify `monitor_5070_ti_v_2.py` unless absolutely necessary.
- Do not send notifications.
- Do not commit, push, create PR, or merge.

Implementation notes:

- Inspect `parsers/citilink.py` and existing parser/test patterns.
- The smoke script should print clear diagnostics for a Citilink request:
  - HTTP status.
  - Final URL.
  - Content-Type.
  - Response size.
  - Block, captcha, anti-bot, or access-denied signs.
  - Candidate product/card counts.
  - Sample names and prices when available.
- Reuse existing parser helpers where practical.
- Keep network timeouts bounded.
- Add or update focused tests if the parser diagnostics are factored into testable functions.

Verification:

- Run `python -m pytest -q`.
- Run `python tools/smoke_citilink.py` manually and inspect output.
