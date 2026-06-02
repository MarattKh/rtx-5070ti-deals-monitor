# Task: Revive Citilink RTX 5070 Ti parser (live DOM check + fixture test)

## Context

`parsers/citilink.py` already has a dedicated parser with `parse_cards`,
`_parse_snippet_cards`, and `parse_offers_with_status(browser_mode=True)`.
The selectors target `data-meta-name="Snippet__title"` and
`data-meta-price="<N>"` attributes from the Playwright-rendered page.
The live site may have rotated its HTML structure or anti-bot state since
these selectors were written. The task is to verify the parser against
the current live DOM and update selectors if stale.

Source name in ENABLED_SOURCES: `"Ситилинк"`
Search URL: `https://www.citilink.ru/search/?text=rtx%205070%20ti`
Parser file: `parsers/citilink.py`
Browser fixture output: `debug_html/citilink.html`
Existing fixture: `tests/fixtures/citilink_search.html`
Test file to create/update: `tests/test_citilink_browser.py`

## Goal

Ensure `parse_cards(html)` correctly extracts RTX 5070 Ti cards from the
current live Playwright HTML, with at least one real title, correct price,
and valid product URL. Produce a fixture-based test and a live check result.

## Steps

1. **Fetch live HTML via Playwright:**
   ```python
   from parsers.browser import fetch_html
   html = fetch_html(
       "https://www.citilink.ru/search/?text=rtx%205070%20ti",
       save_to="debug_html/citilink.html",
       wait_selectors=['[data-meta-name="Snippet__title"]', '.product-card'],
       extra_delay_ms=2000,
   )
   ```
   If the site is blocked (HTTP 403/429 or anti-bot page):
   - Call `detect_block_reason(html)` — it should return a non-None string.
   - Do NOT retry indefinitely. Try once with `extra_delay_ms=4000`. If still blocked, document it in the PR body and set status `pr_created_without_merge` with note "live returns 0 — blocked".
   - Do NOT mark the task `completed`; leave it open for manual review.

2. **Inspect the live HTML and identify card selectors:**
   - Look for `data-meta-name="Snippet__title"` attributes — these are the current Citilink snippet cards.
   - Look for `data-meta-price="<digits>"` for price.
   - If these are missing, search for alternative patterns: `class` substrings like `product-card`, `ProductCard`, `catalog-item`.
   - Pick the selector that yields the most complete (title + price + URL) cards.

3. **Update `parse_cards` if needed:**
   - If the existing `SNIPPET_TITLE_RE` / `SNIPPET_PRICE_RE` patterns match the live HTML → no change needed.
   - If stale: update the regex constants and `_parse_snippet_cards` or `_parse_legacy_cards` accordingly.
   - Keep both `_parse_legacy_cards` (fallback) and `_parse_snippet_cards` (primary).
   - Do NOT touch `parse_offers_with_status` signature or `detect_block_reason` logic.

4. **Create `tests/test_citilink_browser.py`** with:
   - A FIXTURE_HTML snippet that mimics the current live card structure (copy 1–2 real cards from `debug_html/citilink.html`, strip PII/tokens).
   - `test_parse_cards_extracts_rtx_5070_ti_offer`: asserts a valid RTX 5070 Ti title and price are extracted.
   - `test_parse_cards_rejects_non_ti_card`: asserts a non-Ti product (e.g., RTX 5070 without "Ti") is rejected by `filter_offers`.
   - `test_parse_cards_returns_empty_for_antibot_page`: asserts empty result on a blocked HTML snippet.

5. **Run live check:**
   ```
   python tools/filter_diagnostics.py "Ситилинк"
   ```
   Record `Raw offers: N` and `"accepted": N` from the output. Include these numbers verbatim in the PR body.
   If raw == 0: the parser is NOT ready. See step 1 blocked-site policy.

6. **Run the full test suite:**
   ```
   python -m pytest --tb=short -q
   ```
   Must be green. No regression: СДЭК Shopping raw≥3 accepted≥3, Регард raw≥6 accepted≥1, Яндекс accepted≥5.

## Constraints

- Touch only `parsers/citilink.py` and `tests/test_citilink_browser.py`.
- Do NOT change `monitor_5070_ti_v_2.py`, queue files, or other parsers.
- Do NOT use `scrape_search_page` from `parsers/common.py` — keep the dedicated parser.
- `debug_html/citilink.html` is gitignored; do NOT commit it.

## PR policy

- Title: `fix: revive Citilink RTX 5070 Ti parser with live DOM selectors`
- Body must include:
  - Live check result: `Raw offers: N`, `Accepted: N`
  - Whether selectors were updated or confirmed unchanged
  - Any block reason if the site was inaccessible
- NO auto-merge. Status: `pr_created_without_merge`.
- A parser that passes only the fixture but gives raw==0 on the live site is NOT ready.
