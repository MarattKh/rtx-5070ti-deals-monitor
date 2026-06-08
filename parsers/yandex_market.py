from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urljoin

from models import ProductOffer
from parsers.common import _clean_text, build_search_url, parse_rub

BASE_URL = "https://market.yandex.ru"
SEARCH_URL = build_search_url("https://market.yandex.ru/search?text={query}")

_CARD_RE = re.compile(r'data-auto="searchOrganic"')
_TITLE_RE = re.compile(r'data-auto="snippet-title"[^>]*?title="([^"]+)"', re.S)
_URL_RE = re.compile(r'href="(/card/[^"?&]+)', re.S)
_PRICE_RE = re.compile(
    r'data-auto="snippet-price-current"[^>]*>.*?<span[^>]*>([^<]+)</span>',
    re.S,
)


def parse_cards(html: str) -> list[dict]:
    cards: list[dict] = []
    seen: set[str] = set()

    positions = [m.start() for m in _CARD_RE.finditer(html)]
    for i, start in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(html)
        block = html[start:end]

        title_m = _TITLE_RE.search(block)
        if not title_m:
            continue
        title = _clean_text(title_m.group(1))
        if not title:
            continue

        url_m = _URL_RE.search(block)
        if not url_m:
            continue
        url = urljoin(BASE_URL, url_m.group(1))
        if url in seen:
            continue

        price_m = _PRICE_RE.search(block)
        if not price_m:
            continue
        price = parse_rub(price_m.group(1))
        if not price:
            continue

        seen.add(url)
        cards.append({"title": title, "url": url, "price": price})

    return cards


def parse_offers() -> list[ProductOffer]:
    try:
        from parsers.browser import fetch_html

        html = fetch_html(SEARCH_URL, save_to="debug_html/yandex_market.html")
    except Exception:
        return []

    now = datetime.now(timezone.utc).isoformat()
    return [
        ProductOffer(
            source="Яндекс Маркет",
            title=c["title"],
            price=c["price"],
            currency="RUB",
            url=c["url"],
            condition="new",
            seller="Яндекс Маркет",
            availability="unknown",
            checked_at=now,
            confidence=0.8,
            raw_text=c["title"],
        )
        for c in parse_cards(html)
    ]
