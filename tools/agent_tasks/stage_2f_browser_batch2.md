# Task: Add browser scraping for dark RTX sources — batch 2 (2–3 sources)
## Context
stage_2f_browser_first_source proved the browser-parser pattern for one source. This task extends
it to the next 2–3 sources that still return 0 filtered offers. Do NOT re-do DNS, Ситилинк, or
the source already handled in stage_2f_browser_first_source.
## Goal
Write dedicated browser parsers for 2–3 additional dark sources, each in its own parser file, with
offline fixture tests.
## Steps
1. Check source stats (run monitor or inspect parsers). Pick 2–3 sources that still return 0 filtered
   offers and haven't been addressed yet.
2. For each chosen source, follow the same pattern as stage_2f_browser_first_source:
   a. `parse_offers_browser()` using `parsers.browser.fetch_html_safe()` or direct Playwright.
   b. BeautifulSoup parsing on JS-rendered HTML.
   c. RTX 5070 Ti title guard + accessory rejection.
   d. Graceful empty return on unavailability.
3. Fixture tests per source (minimal HTML snippet, RTX offer extracted, non-RTX rejected).
4. If a source requires login or proves impenetrable after one browser attempt, document in PR
   body and move on — do not let one hard source block the batch.
## Constraints
- Touch only `parsers/<source>.py` files chosen and `tests/test_<source>_browser.py` files.
- Do not change monitor_5070_ti_v_2.py, agent tools, or queue files.
## Validation
`python -m pytest --tb=short -q`
## PR
- Title: `Add browser scraping for dark RTX sources (batch 2)`
- Body: list the 2–3 sources, raw offer counts before/after, and any sources skipped with reason.
