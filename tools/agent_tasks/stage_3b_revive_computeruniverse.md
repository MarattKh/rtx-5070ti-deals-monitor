# Task: Build dedicated ComputerUniverse RTX 5070 Ti parser (Yandex Market pattern)

## Context

`parsers/computeruniverse.py` currently delegates entirely to the generic
`scrape_search_page` from `parsers/common.py`. The generic extractor has
low confidence (0.55), may miss JS-rendered price nodes, and does not use
DOM-aware selectors. This task replaces it with a dedicated `parse_cards`
+ `parse_offers` parser following the Yandex Market pattern.

Source name in ENABLED_SOURCES: `"ComputerUniverse"`
Search URL: `https://www.computeruniverse.net/en/search?query=rtx%205070%20ti`
Parser file: `parsers/computeruniverse.py`
Browser fixture output: `debug_html/computeruniverse.html`
Test file to create: `tests/test_computeruniverse_browser.py`

## Goal

Replace the generic fallback with a proper `parse_cards(html)` based on the
real DOM selectors from the live Playwright page, plus fixture tests.

## Steps

1. **Fetch live HTML via Playwright:**
   ```python
   from parsers.browser import fetch_html
   html = fetch_html(
       "https://www.computeruniverse.net/en/search?query=rtx%205070%20ti",
       save_to="debug_html/computeruniverse.html",
       wait_selectors=[
           "[class*='product']",
           "[class*='item']",
           "[class*='card']",
       ],
       extra_delay_ms=3000,
   )
   ```
   If the page is blocked or returns 0 product elements: try once more with
   `extra_delay_ms=6000`. If still empty, document in PR and set status
   `pr_created_without_merge` with note "live returns 0 — investigate manually".

2. **Inspect `debug_html/computeruniverse.html` and identify selectors:**
   - Product title: look for `class` attributes containing `product-name`,
     `product-title`, `item-name`, `name`, or `h3`/`h2` heading tags near price.
   - Price: look for `class` containing `price`, `price-value`, `amount`.
   - Product URL: look for `<a href="/en/p/...">` or similar product page paths.
   - Use the 3–5 most consistent patterns across multiple cards.

3. **Rewrite `parsers/computeruniverse.py` following the Yandex Market pattern:**
   ```python
   from __future__ import annotations
   import re
   from datetime import datetime, timezone
   from models import ProductOffer
   from parsers.common import _clean_text, parse_rub

   BASE_URL = "https://www.computeruniverse.net"
   SEARCH_URL = "https://www.computeruniverse.net/en/search?query=rtx%205070%20ti"

   # Regex patterns derived from real DOM — fill in from live HTML inspection
   _CARD_RE = re.compile(r'...', re.S)     # card boundary marker
   _TITLE_RE = re.compile(r'...', re.S)    # title extractor
   _URL_RE = re.compile(r'...', re.S)      # href extractor
   _PRICE_RE = re.compile(r'...', re.S)    # price extractor

   def parse_cards(html: str) -> list[dict]:
       ...

   def parse_offers() -> list[ProductOffer]:
       try:
           from parsers.browser import fetch_html
           html = fetch_html(SEARCH_URL, save_to="debug_html/computeruniverse.html")
       except Exception:
           return []
       now = datetime.now(timezone.utc).isoformat()
       return [ProductOffer(source="ComputerUniverse", ...) for c in parse_cards(html)]
   ```
   - `confidence=0.8` (not 0.55 as with the generic path).
   - `currency="RUB"` (or `"EUR"` if the site shows EUR — use whatever the live page shows).
   - Apply `is_rtx_5070_ti` and `is_accessory_or_invalid` guards inside `parse_cards`
     (import from `monitor_5070_ti_v_2`), or rely on `filter_offers` in the monitor pipeline.

4. **Create `tests/test_computeruniverse_browser.py`:**
   - FIXTURE_HTML: a snippet with 2–3 cards mimicking the real DOM structure
     (one valid RTX 5070 Ti, one RTX 5070 without "Ti", one accessory or unrelated).
   - `test_parse_cards_extracts_rtx_5070_ti_offer`: asserts the title and price of the valid offer.
   - `test_parse_cards_rejects_non_ti_offer`: asserts RTX 5070 (no Ti) is absent or price-only.
   - `test_parse_cards_returns_empty_on_blank_html`: `parse_cards("")` returns `[]`.

5. **Run live check:**
   ```
   python tools/filter_diagnostics.py "ComputerUniverse"
   ```
   Record `Raw offers: N` and `"accepted": N`. Include in PR body.
   If raw == 0 after both parser and browser fallback: NOT ready.

6. **Run the full test suite:**
   ```
   python -m pytest --tb=short -q
   ```
   Must be green. No regression: СДЭК Shopping raw≥3 accepted≥3, Регард raw≥6 accepted≥1, Яндекс accepted≥5.

## Constraints

- Touch only `parsers/computeruniverse.py` and `tests/test_computeruniverse_browser.py`.
- Do NOT change `monitor_5070_ti_v_2.py`, queue files, or other parsers.
- Remove the `scrape_search_page` call entirely — replace with dedicated `parse_cards` + Playwright fetch.
- `debug_html/computeruniverse.html` is gitignored; do NOT commit it.

## PR policy

- Title: `feat: dedicated ComputerUniverse RTX 5070 Ti parser`
- Body must include:
  - Live check result: `Raw offers: N`, `Accepted: N`
  - Selectors used (brief description or regex pattern)
  - Currency found on live site (RUB or EUR)
- NO auto-merge. Status: `pr_created_without_merge`.
- A parser that passes only the fixture but gives raw==0 on the live site is NOT ready.
