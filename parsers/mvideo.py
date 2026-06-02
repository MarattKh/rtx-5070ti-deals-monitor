from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser
import re
from urllib.parse import urljoin

from models import ProductOffer
from parsers.common import parse_rub, scrape_search_page

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - exercised by the stdlib fallback tests
    BeautifulSoup = None

SEARCH_URL = "https://www.mvideo.ru/product-list-page?q=rtx%205070%20ti"
BASE_URL = "https://www.mvideo.ru"
SOURCE = "М.Видео"
PRICE_RE = re.compile(r"(\d[\d\s\u00a0]{2,9})\s*(?:₽|руб|RUB)", re.IGNORECASE)


def _text(value: str | None) -> str:
    return " ".join((value or "").split())


def _looks_like_card(attrs: dict[str, str], tag: str = "") -> bool:
    haystack = " ".join(
        [
            tag,
            attrs.get("class", ""),
            attrs.get("data-testid", ""),
            attrs.get("data-test-id", ""),
            attrs.get("itemtype", ""),
        ]
    ).lower()
    return "product-card" in haystack or tag.lower() == "mvid-product-card"


def _looks_like_title(attrs: dict[str, str]) -> bool:
    haystack = " ".join(
        [
            attrs.get("class", ""),
            attrs.get("data-testid", ""),
            attrs.get("data-test-id", ""),
            attrs.get("itemprop", ""),
        ]
    ).lower()
    return "title" in haystack or "name" in haystack


def _build_offer(title: str, price: float, url: str, raw_text: str) -> ProductOffer | None:
    from monitor_5070_ti_v_2 import is_accessory_or_invalid, is_rtx_5070_ti
    title = _text(title)
    raw_text = _text(raw_text)
    if not title or not price:
        return None
    if not is_rtx_5070_ti(title, raw_text):
        return None
    if is_accessory_or_invalid(title, raw_text):
        return None

    return ProductOffer(
        source=SOURCE,
        title=title,
        price=price,
        currency="RUB",
        url=urljoin(BASE_URL, url or SEARCH_URL),
        condition="new",
        seller=SOURCE,
        availability="unknown",
        checked_at=datetime.now(timezone.utc).isoformat(),
        confidence=0.85,
        raw_text=raw_text or title,
    )


def _extract_price(raw_text: str) -> float | None:
    match = PRICE_RE.search(raw_text)
    if match:
        return parse_rub(match.group(1))
    return parse_rub(raw_text)


def _extract_offer_from_text(title: str, href: str, raw_text: str) -> ProductOffer | None:
    price = _extract_price(raw_text)
    if price is None:
        return None
    return _build_offer(title=title, price=price, url=href, raw_text=raw_text)


def _extract_with_beautifulsoup(html: str) -> list[ProductOffer]:
    if BeautifulSoup is None:
        return []

    soup = BeautifulSoup(html, "html.parser")
    offers: list[ProductOffer] = []
    seen_urls: set[str] = set()

    for card in soup.find_all(lambda tag: _looks_like_card(tag.attrs, tag.name)):
        link = card.find("a", href=True)
        href = link["href"] if link else SEARCH_URL
        if href in seen_urls:
            continue

        title_node = card.find(lambda tag: _looks_like_title(tag.attrs))
        title = ""
        if title_node:
            title = _text(title_node.get("title") or title_node.get_text(" "))
        if not title and link:
            title = _text(link.get("title") or link.get("aria-label") or link.get_text(" "))
        if not title:
            image = card.find("img", alt=True)
            title = _text(image["alt"] if image else "")

        raw_text = _text(card.get_text(" "))
        offer = _extract_offer_from_text(title=title, href=href, raw_text=raw_text)
        if offer:
            seen_urls.add(href)
            offers.append(offer)

    return offers


class _MvideoCardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[dict[str, str]] = []
        self._card_depth = 0
        self._title_depth = 0
        self._current: dict[str, str | list[str]] | None = None

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {key: value or "" for key, value in attrs_list}
        if self._current is None and _looks_like_card(attrs, tag):
            self._current = {"href": "", "title": "", "text": []}
            self._card_depth = 1
        elif self._current is not None:
            self._card_depth += 1

        if self._current is None:
            return

        href = attrs.get("href", "")
        if tag == "a" and href and not self._current["href"]:
            self._current["href"] = href

        attr_title = _text(attrs.get("title") or attrs.get("aria-label") or attrs.get("alt"))
        if attr_title and not self._current["title"]:
            self._current["title"] = attr_title

        if _looks_like_title(attrs):
            self._title_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return

        if self._title_depth:
            self._title_depth -= 1

        self._card_depth -= 1
        if self._card_depth <= 0:
            self.cards.append(
                {
                    "href": str(self._current["href"]),
                    "title": str(self._current["title"]),
                    "text": _text(" ".join(self._current["text"])),
                }
            )
            self._current = None

    def handle_data(self, data: str) -> None:
        if self._current is None:
            return
        clean = _text(data)
        if not clean:
            return
        self._current["text"].append(clean)
        if self._title_depth and not self._current["title"]:
            self._current["title"] = clean


def _extract_with_htmlparser(html: str) -> list[ProductOffer]:
    parser = _MvideoCardParser()
    parser.feed(html)

    offers: list[ProductOffer] = []
    seen_urls: set[str] = set()
    for card in parser.cards:
        href = card["href"] or SEARCH_URL
        if href in seen_urls:
            continue

        offer = _extract_offer_from_text(title=card["title"], href=href, raw_text=card["text"])
        if offer:
            seen_urls.add(href)
            offers.append(offer)

    return offers


def parse_browser_html(html: str) -> list[ProductOffer]:
    if not html:
        return []

    offers = _extract_with_beautifulsoup(html)
    if offers:
        return offers

    return _extract_with_htmlparser(html)


def parse_offers_browser() -> list[ProductOffer]:
    try:
        from parsers.browser import fetch_html_safe
    except ImportError:
        return []

    html = fetch_html_safe(
        SEARCH_URL,
        save_to="debug_html/mvideo.html",
        wait_selectors=["mvid-product-card", "[class*='product-card']"],
        extra_delay_ms=2500,
    )
    return parse_browser_html(html)


def parse_offers():
    offers = scrape_search_page(source=SOURCE, url=SEARCH_URL, browser_fallback=False)
    if offers:
        return offers
    return parse_offers_browser()
