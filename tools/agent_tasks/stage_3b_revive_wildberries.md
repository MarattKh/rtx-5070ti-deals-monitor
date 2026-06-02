# Task: Revive Wildberries RTX 5070 Ti parser (bypass WBAAS or document blocked)

## Context

`parsers/wildberries.py` has a stub `parse_browser_html` that always returns `[]`.
A previous run documented the site as blocked:

> STATUS: blocked — Wildberries returns the WBAAS antibot browser challenge
> to headless Playwright, not product cards — as of 2026-06-02

This task attempts a fresh Playwright fetch with improved browser context and
extended wait, inspects the resulting HTML, and either writes a working parser
or documents the source as permanently blocked.

Source name in ENABLED_SOURCES: `"Wildberries"`
Search URL: `https://www.wildberries.ru/catalog/0/search.aspx?search=rtx+5070+ti`
Parser file: `parsers/wildberries.py`
Browser fixture output: `debug_html/wildberries.html`
Test file to create/update: `tests/test_wildberries_browser.py`

## Goal

Either produce a working `parse_browser_html(html)` that extracts RTX 5070 Ti
offers from Wildberries, OR confirm the site is still blocked and document it
clearly in the PR body with evidence from the live HTML.

## Steps

1. **Fetch live HTML via Playwright (one attempt with improved settings):**
   ```python
   from parsers.browser import fetch_html
   html = fetch_html(
       "https://www.wildberries.ru/catalog/0/search.aspx?search=rtx+5070+ti",
       save_to="debug_html/wildberries.html",
       wait_selectors=[
           "[class*='product-card']",
           "[class*='catalog-page']",
           ".product-card__name",
           "[data-nm-id]",
       ],
       extra_delay_ms=5000,
   )
   ```
   Then inspect `debug_html/wildberries.html`:
   - If it contains "Almost ready", "Checking browser", "WBAAS", or similar anti-bot markers → BLOCKED.
   - If it contains product-card elements with titles and prices → proceed to step 2.

2. **If accessible — identify card selectors and write `parse_browser_html`:**
   - Find the element that holds the product name (try `data-nm-id`, `.product-card__name`,
     `.goods-name`, `[class*="name"]` attributes).
   - Find the price element (try `ins.price__lower-price`, `[class*="price"]`,
     `data-price` attribute).
   - Find the product URL (try `a[href*="/catalog/"]`).
   - Update `parse_browser_html(html: str) -> list[ProductOffer]` to use BeautifulSoup
     with the found selectors. Apply `is_rtx_5070_ti` and `is_accessory_or_invalid` guards
     (import from `monitor_5070_ti_v_2`).
   - Update `parse_offers_browser()` to call `parse_browser_html`.

3. **If blocked — document and exit:**
   - Save the blocking evidence (first 500 chars of `debug_html/wildberries.html`).
   - Add a dated comment to `parsers/wildberries.py`:
     ```python
     # STATUS: blocked — <reason> — as of YYYY-MM-DD
     ```
   - Update `tests/test_wildberries_browser.py` to add a test that confirms `parse_browser_html`
     returns `[]` for the WBAAS challenge HTML.
   - Create the PR with `blocked_reason: WBAAS antibot challenge` in the body.
   - Set status `pr_created_without_merge`. Do NOT mark completed.

4. **Fixture test (`tests/test_wildberries_browser.py`):**
   If the parser works:
   - FIXTURE_HTML: a 2-card snippet from live HTML (real card structure, strip tokens).
   - `test_parse_browser_html_extracts_rtx_5070_ti_offer`: asserts title, price, URL.
   - `test_parse_browser_html_rejects_non_ti_and_accessory`: asserts non-Ti and accessory cards absent.
   - `test_parse_browser_html_returns_empty_for_antibot_challenge`: existing test, must still pass.

5. **Run live check (only if parser works):**
   ```
   python tools/filter_diagnostics.py "Wildberries"
   ```
   Record `Raw offers: N` and `"accepted": N`. Include in PR body.
   If raw == 0: NOT ready — go back to step 2 or document as blocked.

6. **Run the full test suite:**
   ```
   python -m pytest --tb=short -q
   ```
   Must be green. No regression: СДЭК Shopping raw≥3 accepted≥3, Регард raw≥6 accepted≥1, Яндекс accepted≥5.

## Constraints

- Touch only `parsers/wildberries.py` and `tests/test_wildberries_browser.py`.
- Do NOT change `monitor_5070_ti_v_2.py`, queue files, or other parsers.
- One Playwright attempt only — if blocked after one try, document and move on.
- Do NOT use `scrape_search_page` from `parsers/common.py`.
- `debug_html/wildberries.html` is gitignored; do NOT commit it.

## PR policy

- Title: `fix: revive Wildberries RTX 5070 Ti parser` OR `docs: Wildberries permanently blocked by WBAAS`
- Body must include:
  - Live check result: `Raw offers: N`, `Accepted: N` (or "Blocked: <evidence>")
  - Whether WBAAS was bypassed or the site remains inaccessible
- NO auto-merge. Status: `pr_created_without_merge`.
- A parser that passes only the fixture but gives raw==0 on the live site is NOT ready.
