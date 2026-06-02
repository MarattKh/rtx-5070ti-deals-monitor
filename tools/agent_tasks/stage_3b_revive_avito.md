# Task: Build dedicated Avito RTX 5070 Ti parser (Yandex Market pattern)

## Context

`parsers/avito.py` currently delegates entirely to the generic
`scrape_search_page` from `parsers/common.py`. Avito is a Russian classified-
ads platform with JS-heavy rendering, login walls on some flows, and
potential anti-bot protection. A dedicated parser using Playwright + DOM-aware
selectors is required to reliably extract RTX 5070 Ti listings.

Source name in ENABLED_SOURCES: `"Avito"`
Search URL: `https://www.avito.ru/rossiya/tovary_dlya_kompyutera?q=rtx+5070+ti`
Parser file: `parsers/avito.py`
Browser fixture output: `debug_html/avito.html`
Test file to create: `tests/test_avito_browser.py`

## Goal

Replace the generic fallback with a proper `parse_cards(html)` based on the
real DOM selectors from the live Playwright page, plus fixture tests and a
live check result.

## Steps

1. **Fetch live HTML via Playwright:**
   ```python
   from parsers.browser import fetch_html
   html = fetch_html(
       "https://www.avito.ru/rossiya/tovary_dlya_kompyutera?q=rtx+5070+ti",
       save_to="debug_html/avito.html",
       wait_selectors=[
           "[data-marker='item']",
           "[class*='iva-item']",
           "[class*='item-root']",
       ],
       extra_delay_ms=4000,
   )
   ```
   Avito may redirect to a region page or require cookie consent. If the HTML
   contains "robot", "captcha", "403", or shows 0 product elements, document
   it in the PR body and set status `pr_created_without_merge` with note
   "live returns 0 — anti-bot or login wall". Do NOT retry more than once.

2. **Inspect `debug_html/avito.html` and identify selectors:**
   - Item container: look for `data-marker="item"` or `class` containing `iva-item`.
   - Title: look for `data-marker="item-title"` or `itemprop="name"` or
     `class` containing `title` within each item.
   - Price: look for `data-marker="item-price"` or `class` containing `price`
     or `itemprop="price"`.
   - URL: `<a href="/...">` inside the item container; prefix with `https://www.avito.ru`.
   - Condition: check if "б/у" or "б.у." appears in the title or description
     (set `condition="used"` if yes, else `condition="new"`).

3. **Rewrite `parsers/avito.py` following the Yandex Market pattern:**
   ```python
   from __future__ import annotations
   import re
   from datetime import datetime, timezone
   from models import ProductOffer
   from parsers.common import _clean_text, parse_rub

   BASE_URL = "https://www.avito.ru"
   SEARCH_URL = "https://www.avito.ru/rossiya/tovary_dlya_kompyutera?q=rtx+5070+ti"

   # Regex patterns derived from real DOM — fill in from live HTML inspection
   _CARD_RE = re.compile(r'...', re.S)     # item boundary marker
   _TITLE_RE = re.compile(r'...', re.S)    # title extractor
   _URL_RE = re.compile(r'...', re.S)      # href extractor
   _PRICE_RE = re.compile(r'...', re.S)    # price extractor

   def parse_cards(html: str) -> list[dict]:
       ...

   def parse_offers() -> list[ProductOffer]:
       try:
           from parsers.browser import fetch_html
           html = fetch_html(SEARCH_URL, save_to="debug_html/avito.html",
                             wait_selectors=["[data-marker='item']"],
                             extra_delay_ms=4000)
       except Exception:
           return []
       now = datetime.now(timezone.utc).isoformat()
       return [ProductOffer(source="Avito", ...) for c in parse_cards(html)]
   ```
   - `confidence=0.8`.
   - `currency="RUB"`.
   - Set `condition` based on presence of "б/у"/"б.у." in title.
   - Apply `is_rtx_5070_ti` and `is_accessory_or_invalid` guards inside `parse_cards`
     (import from `monitor_5070_ti_v_2`), or rely on `filter_offers` in the monitor pipeline.
   - Avito listings vary widely — accept only listings with a non-zero price and a non-empty title.

4. **Create `tests/test_avito_browser.py`:**
   - FIXTURE_HTML: a 3-card snippet mimicking real Avito DOM structure
     (one valid RTX 5070 Ti new, one RTX 5070 Ti б/у, one non-Ti GPU or accessory).
   - `test_parse_cards_extracts_new_rtx_5070_ti_offer`: asserts title, price, condition=="new".
   - `test_parse_cards_extracts_used_rtx_5070_ti_offer`: asserts condition=="used" for б/у listing.
   - `test_parse_cards_rejects_non_ti_gpu`: asserts non-Ti GPU is absent.
   - `test_parse_cards_returns_empty_on_blank_html`: `parse_cards("")` returns `[]`.

5. **Run live check:**
   ```
   python tools/filter_diagnostics.py "Avito"
   ```
   Record `Raw offers: N` and `"accepted": N`. Include in PR body.
   If raw == 0: NOT ready — check for anti-bot or login wall and document it.

6. **Run the full test suite:**
   ```
   python -m pytest --tb=short -q
   ```
   Must be green. No regression: СДЭК Shopping raw≥3 accepted≥3, Регард raw≥6 accepted≥1, Яндекс accepted≥5.

## Constraints

- Touch only `parsers/avito.py` and `tests/test_avito_browser.py`.
- Do NOT change `monitor_5070_ti_v_2.py`, queue files, or other parsers.
- Remove the `scrape_search_page` call — replace with dedicated `parse_cards` + Playwright fetch.
- `debug_html/avito.html` is gitignored; do NOT commit it.
- Avito shows used-market listings — handle `condition="used"` properly.

## PR policy

- Title: `feat: dedicated Avito RTX 5070 Ti parser`
- Body must include:
  - Live check result: `Raw offers: N`, `Accepted: N`
  - Whether used/new listings were found
  - Any anti-bot or login-wall evidence if raw == 0
- NO auto-merge. Status: `pr_created_without_merge`.
- A parser that passes only the fixture but gives raw==0 on the live site is NOT ready.
