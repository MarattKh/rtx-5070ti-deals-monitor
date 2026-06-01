# Task: Add browser scraping for one dark RTX source (proof-of-concept)
## Context
Most sources use `parsers/common.py::extract_product_offers` which already tries browser fallback.
However the generic HTML extractor may fail on JS-rendered pages (searches, pagination, dynamic
price rendering). This task picks ONE confirmed-dark source and writes a proper browser-based parser
for it. DNS and Ситилинк already have dedicated Playwright parsers — do not re-do them.
## Goal
Select the simplest dark source that returns 0 filtered offers, write a minimal dedicated browser
parser for it, and add tests. This is proof-of-concept for the batch approach that follows.
## Steps
1. Run `python monitor_5070_ti_v_2.py --browser 2>&1` (or equivalent) and look at source stats.
   Pick ONE source with `raw_count == 0` or `blocked: true` that is NOT DNS or Ситилинк.
   Prefer a source with a publicly accessible search/category page (no login wall).
   Good candidates: М.Видео, Эльдорадо, Wildberries, Ozon, Мегамаркет (check which returns 0).
2. Write `parsers/<source_module>.py::parse_offers_browser() -> list[ProductOffer]` that:
   a. Uses `parsers.browser.fetch_html_safe()` (from stage_2f_browser_helper, already in main) or
      direct Playwright if `fetch_html_safe` is not yet in main — fall back to importing directly.
   b. Parses the JS-rendered HTML with BeautifulSoup to extract title + price.
   c. Applies `_is_rtx_5070_ti(title)` and `_is_accessory_or_invalid(title)` guards (import from
      monitor_5070_ti_v_2 or reuse existing parser helpers).
   d. Returns [] gracefully if the page is unavailable or parsing yields nothing.
3. Wire it in: if the source already calls `scrape_search_page`, check whether adding
   `parse_offers_browser()` and calling it from `parse_offers()` or `parse_offers_with_status()`
   improves results, or create a thin wrapper.
4. Add a fixture-based offline test in `tests/test_<source>_browser.py`:
   - A minimal HTML snippet that mimics the JS-rendered page structure.
   - Assert that at least one RTX 5070 Ti offer is extracted from the fixture.
   - Assert that a non-RTX title in the fixture is rejected.
## Constraints
- Touch only `parsers/<chosen_source>.py` and `tests/test_<chosen_source>_browser.py`.
- Do not change monitor_5070_ti_v_2.py, agent tools, or queue files.
- If the chosen source requires authentication or anti-bot bypass that Playwright can't handle in
  headless mode, document that in the PR body and mark the source as `blocked_requires_login`.
  Do NOT spend more than one retry attempt on any single source — pick another if blocked.
## Validation
`python -m pytest --tb=short -q`
## PR
- Title: `Add browser scraping for [source name] RTX source`
- Body: which source was chosen and why, what the raw offer count became, any caveats.
