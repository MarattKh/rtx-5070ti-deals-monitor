from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError

from models import ProductOffer
from parsers.common import _clean_text, _download, build_search_url, parse_rub

SEARCH_URL = build_search_url("https://www.regard.ru/catalog/tovar/search?search={query}", plus=True)
BASE_URL = "https://www.regard.ru"

CARD_START_RE = re.compile(r'<div[^>]+class="[^"]*CardMain_wrap[^"]*"[^>]*>', re.S)
URL_RE = re.compile(r'href="(?P<url>/product/[^"]+)"', re.S)
TITLE_RE = re.compile(
    r'<div[^>]+title="(?P<title>[^"]*(?:RTX|GeForce|5070)[^"]*)"[^>]*class="[^"]*CardText_title[^"]*"',
    re.I | re.S,
)
ALT_TITLE_RE = re.compile(r'alt="(?P<title>[^"]*(?:RTX|GeForce|5070)[^"]*)"', re.I | re.S)
PRICE_RE = re.compile(
    r'<span[^>]+class="[^"]*Price_price[^"]*"[^>]*>(?P<price>.*?)</span>',
    re.I | re.S,
)


def _card_blocks(html: str) -> list[str]:
    starts = [m.start() for m in CARD_START_RE.finditer(html)]
    blocks: list[str] = []

    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(html)
        blocks.append(html[start:end])

    return blocks


def _extract_title(block: str) -> str:
    m = TITLE_RE.search(block) or ALT_TITLE_RE.search(block)
    if not m:
        return ""
    return _clean_text(m.group("title"))


def _extract_price(block: str) -> float | None:
    m = PRICE_RE.search(block)
    if not m:
        return None

    price_text = _clean_text(m.group("price"))
    return parse_rub(price_text)


def parse_cards(html: str) -> list[dict]:
    cards: list[dict] = []
    seen_urls: set[str] = set()

    for block in _card_blocks(html):
        url_m = URL_RE.search(block)
        if not url_m:
            continue

        url = url_m.group("url")
        if url in seen_urls:
            continue

        title = _extract_title(block)
        price = _extract_price(block)

        if not title or not price:
            continue

        seen_urls.add(url)

        cards.append(
            {
                "title": title,
                "url": url,
                "price": price,
                "availability": "unknown",
            }
        )

    return cards


def parse_offers() -> list[ProductOffer]:
    try:
        html = _download(SEARCH_URL)
    except (HTTPError, URLError, TimeoutError):
        return []

    now = datetime.now(timezone.utc).isoformat()
    offers: list[ProductOffer] = []

    for c in parse_cards(html):
        full_url = c["url"] if c["url"].startswith("http") else f"{BASE_URL}{c['url']}"

        offers.append(
            ProductOffer(
                source="Регард",
                title=c["title"],
                price=c["price"],
                currency="RUB",
                url=full_url,
                condition="new",
                seller="Регард",
                availability=c.get("availability", "unknown"),
                checked_at=now,
                confidence=0.9,
                raw_text=c["title"],
            )
        )

    return offers
