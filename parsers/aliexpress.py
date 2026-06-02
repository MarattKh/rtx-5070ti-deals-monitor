from __future__ import annotations

from parsers.common import scrape_search_page

SEARCH_URL = "https://aliexpress.ru/wholesale?SearchText=rtx+5070+ti"
SOURCE = "Aliexpress"


# STATUS: blocked — AliExpress serves a hydrated app shell with session verification and no stable product card HTML to parse — as of 2026-06-02

def parse_browser_html(html: str) -> list:
    return []


def parse_offers_browser() -> list:
    try:
        from parsers.browser import fetch_html_safe
    except ImportError:
        return []

    html = fetch_html_safe(
        SEARCH_URL,
        save_to="debug_html/aliexpress.html",
        wait_selectors=["[class*=\"SnowSearchProductFeed\"]", "[class*=\"product\"]"],
        extra_delay_ms=2500,
    )
    return parse_browser_html(html)


def parse_offers():
    offers = scrape_search_page(source=SOURCE, url=SEARCH_URL, browser_fallback=False)
    if offers:
        return offers
    return parse_offers_browser()
