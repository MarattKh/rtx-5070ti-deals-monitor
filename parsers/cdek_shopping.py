from __future__ import annotations

from datetime import datetime, timezone
import html as html_lib
import re
from urllib.parse import urljoin

from models import ProductOffer
from parsers.common import build_search_url, parse_rub, scrape_search_page

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None

SEARCH_URL = build_search_url("https://cdek.shopping/search/?q={query}")
BASE_URL = "https://cdek.shopping"
SOURCE = "Cdek Shopping"
PRICE_RE = re.compile(r"(\d[\d\s\u00a0]{2,11})\s*(?:\u20bd|\u0440\u0443\u0431|RUB)", re.IGNORECASE)
CARD_RE = re.compile(r"<(?P<tag>[a-z0-9-]+)[^>]*(?:product-card|catalog-card|product-item|search-product)[^>]*>.*?</(?P=tag)>", re.IGNORECASE | re.DOTALL)
HREF_RE = re.compile(r"href=[\"']([^\"']+)[\"']", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
TITLE_RE = re.compile(r"<[^>]*(?:title|name|product-card__title|font-medium)[^>]*>(.*?)</[^>]+>", re.IGNORECASE | re.DOTALL)
UNAVAILABLE_MARKERS = (
    "out of stock",
    "sold out",
    "\u043d\u0435\u0442 \u0432 \u043d\u0430\u043b\u0438\u0447\u0438\u0438",
    "\u043d\u0435\u0442 \u0442\u043e\u0432\u0430\u0440\u0430",
)


def _text(value: str | None) -> str:
    return " ".join((value or "").split())


def _clean_fragment(fragment: str) -> str:
    return _text(html_lib.unescape(TAG_RE.sub(" ", fragment)))


def _attr_haystack(tag) -> str:
    attrs = tag.attrs
    values: list[str] = [tag.name or ""]
    for key in ("class", "data-testid", "data-test-id", "data-qa", "itemtype"):
        value = attrs.get(key, "")
        if isinstance(value, list):
            values.extend(str(part) for part in value)
        else:
            values.append(str(value))
    return " ".join(values).lower()


def _looks_like_card(tag) -> bool:
    haystack = _attr_haystack(tag)
    return any(marker in haystack for marker in ("product-card", "catalog-card", "product-item", "search-product"))


def _looks_like_title(tag) -> bool:
    haystack = _attr_haystack(tag)
    return any(marker in haystack for marker in ("title", "name", "product-card__title"))


def _extract_price(raw_text: str) -> float | None:
    match = PRICE_RE.search(raw_text)
    if match:
        return parse_rub(match.group(1))
    return parse_rub(raw_text)


def _is_unavailable(raw_text: str) -> bool:
    lowered = raw_text.casefold()
    return any(marker in lowered for marker in UNAVAILABLE_MARKERS)


def _build_offer(title: str, price: float | None, href: str, raw_text: str) -> ProductOffer | None:
    from monitor_5070_ti_v_2 import is_accessory_or_invalid, is_relevant_product

    title = _text(title)
    raw_text = _text(raw_text)
    if not title or not price or _is_unavailable(raw_text):
        return None
    if not is_relevant_product(title, raw_text):
        return None
    if is_accessory_or_invalid(title, raw_text):
        return None

    return ProductOffer(
        source=SOURCE,
        title=title,
        price=price,
        currency="RUB",
        url=urljoin(BASE_URL, href or SEARCH_URL),
        condition="new",
        seller=SOURCE,
        availability="unknown",
        checked_at=datetime.now(timezone.utc).isoformat(),
        confidence=0.85,
        raw_text=raw_text or title,
    )


def _title_from_card(card) -> str:
    title_node = card.find(_looks_like_title)
    if title_node:
        title = _text(title_node.get("title") or title_node.get_text(" "))
        if title:
            return title

    titled = card.find(attrs={"title": True})
    if titled:
        return _text(titled["title"])

    link = card.find("a", href=True)
    if link:
        title = _text(link.get("title") or link.get("aria-label") or link.get_text(" "))
        if title:
            return title

    image = card.find("img", alt=True)
    return _text(image["alt"] if image else "")


def _extract_with_beautifulsoup(html: str) -> list[ProductOffer]:
    if BeautifulSoup is None:
        return []

    soup = BeautifulSoup(html, "html.parser")
    offers: list[ProductOffer] = []
    seen_urls: set[str] = set()

    for card in soup.find_all(_looks_like_card):
        link = card.find("a", href=True)
        href = link["href"] if link else SEARCH_URL
        absolute_url = urljoin(BASE_URL, href)
        if absolute_url in seen_urls:
            continue

        raw_text = _text(card.get_text(" "))
        offer = _build_offer(
            title=_title_from_card(card),
            price=_extract_price(raw_text),
            href=href,
            raw_text=raw_text,
        )
        if offer:
            seen_urls.add(absolute_url)
            offers.append(offer)

    return offers


def _extract_with_regex(html: str) -> list[ProductOffer]:
    offers: list[ProductOffer] = []
    seen_urls: set[str] = set()

    for match in CARD_RE.finditer(html):
        card_html = match.group(0)
        href_match = HREF_RE.search(card_html)
        href = href_match.group(1) if href_match else SEARCH_URL
        absolute_url = urljoin(BASE_URL, href)
        if absolute_url in seen_urls:
            continue

        title_match = TITLE_RE.search(card_html)
        title = _clean_fragment(title_match.group(1)) if title_match else _clean_fragment(card_html)
        raw_text = _clean_fragment(card_html)
        offer = _build_offer(title=title, price=_extract_price(raw_text), href=href, raw_text=raw_text)
        if offer:
            seen_urls.add(absolute_url)
            offers.append(offer)

    return offers


def parse_browser_html(html: str) -> list[ProductOffer]:
    if not html:
        return []

    offers = _extract_with_beautifulsoup(html)
    if offers:
        return offers

    return _extract_with_regex(html)


def parse_offers_browser() -> list[ProductOffer]:
    try:
        from parsers.browser import fetch_html_safe
    except ImportError:
        return []

    html = fetch_html_safe(
        SEARCH_URL,
        save_to="debug_html/cdek_shopping.html",
        wait_selectors=["article[class*=\"product-card\"]", "[class*=\"product-card\"]", "[class*=\"catalog-card\"]"],
        extra_delay_ms=2500,
    )
    return parse_browser_html(html)


def parse_offers():
    offers = scrape_search_page(source=SOURCE, url=SEARCH_URL, browser_fallback=False)
    if offers:
        return offers
    return parse_offers_browser()
