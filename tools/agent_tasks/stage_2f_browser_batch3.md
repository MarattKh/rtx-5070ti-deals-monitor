# Task: Add browser scraping for dark RTX sources — batch 3 (remaining sources)
## Context
After batches 1 and 2, some dark sources will still return 0 filtered offers. This task handles
the remaining ones (up to 3 sources). Same pattern as the previous batches.
## Goal
Write browser parsers for the remaining dark sources not yet covered by earlier browser tasks.
## Steps
1. Check source stats. Pick up to 3 remaining sources that still return 0 filtered offers and
   have not been addressed by earlier browser tasks (stage_2f_browser_first_source or batch2).
2. For each, follow the same pattern: `parse_offers_browser()`, BeautifulSoup parsing, title
   guards, graceful fallback, fixture test.
3. For sources that remain genuinely inaccessible (hard login, heavy Cloudflare, etc.), add a
   structured comment in the parser noting `# STATUS: blocked — <reason> — as of YYYY-MM-DD`.
4. After all sources are addressed, run the monitor end-to-end and log how many sources now
   return >0 filtered offers vs. how many remain dark.
## Constraints
- Touch only `parsers/<source>.py` files chosen and `tests/test_<source>_browser.py` files.
- Do not change monitor_5070_ti_v_2.py, agent tools, or queue files.
## Validation
`python -m pytest --tb=short -q`
## PR
- Title: `Add browser scraping for remaining RTX sources (batch 3)`
- Body: list sources handled, sources still dark with reason, before/after offer counts.
