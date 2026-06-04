from __future__ import annotations

import html as html_lib
import json
import re
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError

from models import ProductOffer
from parsers.common import _clean_text, _download, parse_rub

CATALOG_URL = (
    "https://www.xcom-shop.ru/catalog/komplektyyuschie_dlya_pk_i_noytbykov/"
    "videokarty/filter/graficheskiy-processor=nvidia-geforce-rtx-5070-ti/"
)
BASE_URL = "https://www.xcom-shop.ru"

# Primary: parse structured data-dl-product JSON attributes.
# Note: XCOM injects schema.org JSON-LD for Organization only (no Product/ItemList),
# so we use data-dl-product as the structured-data path instead.
DL_PRODUCT_RE = re.compile(r'data-dl-product="([^"]+)"')
ITEM_URL_RE = re.compile(
    r'class="catalog_item__image catalog_item__image--list"\s+href="([^"]+)"'
)

XCOM_BLOCK_WARNING = "XCOM-SHOP access blocked. Manual verification required."


def parse_cards(html: str) -> list[dict]:
    products = DL_PRODUCT_RE.findall(html)
    urls = ITEM_URL_RE.findall(html)

    cards: list[dict] = []
    seen_urls: set[str] = set()

    for raw_json, url in zip(products, urls):
        if url in seen_urls:
            continue

        try:
            data = json.loads(html_lib.unescape(raw_json))
        except (json.JSONDecodeError, ValueError):
            continue

        name = _clean_text(data.get("name", ""))
        price_raw = data.get("price")
        try:
            price = float(price_raw)
        except (TypeError, ValueError):
            continue

        if not name or not price:
            continue

        seen_urls.add(url)
        cards.append({"title": name, "price": price, "url": url})

    return cards


def _build_offers(html: str) -> list[ProductOffer]:
    now = datetime.now(timezone.utc).isoformat()
    offers: list[ProductOffer] = []

    for c in parse_cards(html):
        full_url = c["url"] if c["url"].startswith("http") else f"{BASE_URL}{c['url']}"
        offers.append(
            ProductOffer(
                source="XCOM-SHOP",
                title=c["title"],
                price=c["price"],
                currency="RUB",
                url=full_url,
                condition="new",
                seller="XCOM-SHOP",
                availability="in_stock",
                checked_at=now,
                confidence=0.9,
                raw_text=c["title"],
            )
        )

    return offers


def detect_block_reason(html: str) -> str | None:
    normalized = html.lower()
    if "429 too many requests" in normalized or "too many requests" in normalized:
        return "429 too many requests"
    if (
        "403 forbidden" in normalized
        or "access denied" in normalized
        or "доступ запрещ" in normalized
        or "доступ огранич" in normalized
    ):
        return "403 forbidden"
    return None


def parse_offers_with_status(browser_mode: bool = False) -> dict:
    try:
        html = _download(CATALOG_URL)
    except HTTPError as exc:
        if exc.code in (401, 403, 429):
            reason = {401: "401 unauthorized", 403: "403 forbidden", 429: "429 too many requests"}[exc.code]
            return {"offers": [], "blocked": True, "block_reason": reason, "warnings": [XCOM_BLOCK_WARNING], "errors": 1}
        return {"offers": [], "blocked": False, "block_reason": None, "warnings": [str(exc)], "errors": 1}
    except (URLError, TimeoutError) as exc:
        return {"offers": [], "blocked": False, "block_reason": None, "warnings": [str(exc)], "errors": 1}

    offers = _build_offers(html)
    if offers:
        return {"offers": offers, "blocked": False, "block_reason": None, "warnings": [], "errors": 0}

    # No products found — check if it's a block page (js bundles contain false-positive phrases,
    # so we only run block detection when there are no catalog items at all)
    block_reason = detect_block_reason(html)
    if block_reason:
        return {"offers": [], "blocked": True, "block_reason": block_reason, "warnings": [XCOM_BLOCK_WARNING], "errors": 1}

    return {"offers": [], "blocked": False, "block_reason": None, "warnings": [], "errors": 0}


def parse_offers(browser_mode: bool = False) -> list[ProductOffer]:
    return parse_offers_with_status(browser_mode)["offers"]
