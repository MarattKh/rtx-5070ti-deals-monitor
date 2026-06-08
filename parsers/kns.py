from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError

from models import ProductOffer
from parsers.common import _clean_text, _download
from target_config import get_source_filter

_FILTER = get_source_filter("KNS")
CATALOG_URL = (
    "https://www.kns.ru/catalog/komplektuyuschie/videokarty/"
    f"_graficheskij-protsessor_{_FILTER}/"
    if _FILTER else ""
)
BASE_URL = "https://www.kns.ru"

_NOT_CONFIGURED = {
    "offers": [], "blocked": False, "block_reason": None,
    "warnings": ["Источник не настроен для данного товара"], "errors": 0,
}

# KNS uses schema.org microdata (not JSON-LD): Product itemscope with
# itemprop=name/url/price meta tags inside each card block.
PRODUCT_RE = re.compile(
    r'itemtype="http://schema\.org/Product"(.*?)(?=itemtype="http://schema\.org/Product"|</body>|$)',
    re.S,
)
NAME_RE = re.compile(r'itemprop="name">([^<]+)<')
URL_RE = re.compile(r'<meta itemprop="url" content="([^"]+)"')
PRICE_RE = re.compile(r'<meta itemprop="price" content="([^"]+)"')

KNS_BLOCK_WARNING = "KNS access blocked. Manual verification required."


def parse_cards(html: str) -> list[dict]:
    cards: list[dict] = []
    seen_urls: set[str] = set()

    for m in PRODUCT_RE.finditer(html):
        block = m.group(1)
        name_m = NAME_RE.search(block)
        url_m = URL_RE.search(block)
        price_m = PRICE_RE.search(block)

        if not (name_m and url_m and price_m):
            continue

        url = url_m.group(1).strip()
        if url in seen_urls:
            continue

        title = _clean_text(name_m.group(1))
        try:
            price = float(price_m.group(1).strip())
        except ValueError:
            continue

        if not title or not price:
            continue

        seen_urls.add(url)
        cards.append({"title": title, "price": price, "url": url})

    return cards


def detect_block_reason(html: str) -> str | None:
    normalized = html.lower()
    if "429 too many requests" in normalized or "<title>429" in normalized:
        return "429 too many requests"
    if "403 forbidden" in normalized or "access denied" in normalized:
        return "403 forbidden"
    return None


def _build_offers(html: str) -> list[ProductOffer]:
    now = datetime.now(timezone.utc).isoformat()
    offers: list[ProductOffer] = []

    for c in parse_cards(html):
        full_url = c["url"] if c["url"].startswith("http") else f"{BASE_URL}{c['url']}"
        offers.append(
            ProductOffer(
                source="KNS",
                title=c["title"],
                price=c["price"],
                currency="RUB",
                url=full_url,
                condition="new",
                seller="KNS",
                availability="in_stock",
                checked_at=now,
                confidence=0.9,
                raw_text=c["title"],
            )
        )

    return offers


def parse_offers_with_status(browser_mode: bool = False) -> dict:
    if not CATALOG_URL:
        return _NOT_CONFIGURED
    try:
        html = _download(CATALOG_URL)
    except HTTPError as exc:
        if exc.code in (401, 403, 429):
            reason = {
                401: "401 unauthorized",
                403: "403 forbidden",
                429: "429 too many requests",
            }[exc.code]
            return {
                "offers": [],
                "blocked": True,
                "block_reason": reason,
                "warnings": [KNS_BLOCK_WARNING],
                "errors": 1,
            }
        return {
            "offers": [],
            "blocked": False,
            "block_reason": None,
            "warnings": [str(exc)],
            "errors": 1,
        }
    except (URLError, TimeoutError) as exc:
        return {
            "offers": [],
            "blocked": False,
            "block_reason": None,
            "warnings": [str(exc)],
            "errors": 1,
        }

    offers = _build_offers(html)
    if offers:
        return {"offers": offers, "blocked": False, "block_reason": None, "warnings": [], "errors": 0}

    block_reason = detect_block_reason(html)
    if block_reason:
        return {
            "offers": [],
            "blocked": True,
            "block_reason": block_reason,
            "warnings": [KNS_BLOCK_WARNING],
            "errors": 1,
        }

    return {"offers": [], "blocked": False, "block_reason": None, "warnings": [], "errors": 0}


def parse_offers(browser_mode: bool = False) -> list[ProductOffer]:
    return parse_offers_with_status(browser_mode)["offers"]
