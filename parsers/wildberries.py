from __future__ import annotations

from parsers.common import scrape_search_page

SEARCH_URL = "https://www.wildberries.ru/catalog/0/search.aspx?search=rtx%205070%20ti"
SOURCE = "Wildberries"


# STATUS: blocked — Wildberries returns the WBAAS antibot browser challenge to headless Playwright, not product cards — as of 2026-06-02

def parse_browser_html(html: str) -> list:
    return []


def parse_offers_browser() -> list:
    try:
        from parsers.browser import fetch_html_safe
    except ImportError:
        return []

    html = fetch_html_safe(
        SEARCH_URL,
        save_to="debug_html/wildberries.html",
        wait_selectors=["[class*=\"product-card\"]", "[class*=\"catalog-page\"]"],
        extra_delay_ms=2500,
    )
    return parse_browser_html(html)


def parse_offers():
    offers = scrape_search_page(source=SOURCE, url=SEARCH_URL, browser_fallback=False)
    if offers:
        return offers
    return parse_offers_browser()
