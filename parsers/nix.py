from __future__ import annotations

import gzip
import html as html_lib
import re
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from models import ProductOffer
from parsers.common import _clean_text
from target_config import get_source_filter

LISTING_URL = (
    "https://www.nix.ru/price/price_list.html?section=video_cards_all"
)
OFFERS_API_URL = "https://www.nix.ru/scripts/action.php/FastSearch/goodOffers"
BASE_URL = "https://www.nix.ru"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_FILTER = get_source_filter("НИКС")

# Anchors like:  href='/autocatalog/.../GeForce-RTX5070Ti_NNNNNN.html' title='...' >TITLE</a>
# The token (e.g. "5070Ti") is the product-specific fragment in the URL path.
_PRODUCT_RE = re.compile(
    rf"href='(/autocatalog/[^']+{re.escape(_FILTER)}_(\d+)\.html)' title='[^']*' >(.*?)</a>",
    re.S,
) if _FILTER else None

_NOT_CONFIGURED = {
    "offers": [], "blocked": False, "block_reason": None,
    "warnings": ["Источник не настроен для данного товара"], "errors": 0,
}

# Price links: <a class='n' title='Положить в корзину' ...>PRICE</a>
# Excludes delivery-surcharge entries that start with '+' (e.g. '+216').
_BASKET_PRICE_RE = re.compile(
    r"title='Положить в корзину'[^>]*>([^<]+)</a>"
)

NIX_BLOCK_WARNING = "НИКС access blocked. Manual verification required."


def _fetch(url: str, *, method: str = "GET", body: bytes | None = None) -> bytes:
    headers: dict[str, str] = {"User-Agent": _UA}
    if method == "POST":
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["X-Requested-With"] = "XMLHttpRequest"
        headers["Referer"] = LISTING_URL
    req = Request(url, data=body, headers=headers, method=method)
    with urlopen(req, timeout=12) as r:  # nosec B310
        raw = r.read()
    return gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw


def _fetch_min_price(good_id: str) -> float | None:
    """Return the minimum in-store price for one product, or None if unavailable."""
    body = urlencode(
        {
            "good_id": good_id,
            "order_number": "1",
            "city_id": "1721",
            "shop_price": "0",
            "test_id": "",
            "price_gb": "false",
            "param_col": "0",
        }
    ).encode()
    try:
        raw = _fetch(OFFERS_API_URL, method="POST", body=body)
    except (HTTPError, URLError, TimeoutError):
        return None

    import json as _json

    try:
        offers_html: str = _json.loads(raw.decode("utf-8", errors="ignore"))
    except Exception:
        offers_html = raw.decode("utf-8", errors="ignore")

    prices: list[int] = []
    for m in _BASKET_PRICE_RE.finditer(offers_html):
        text = m.group(1).strip()
        if text.startswith("+"):
            continue  # delivery surcharge, not product price
        digits = re.sub(r"[^\d]", "", text)
        if digits:
            prices.append(int(digits))

    return float(min(prices)) if prices else None


def parse_cards(listing_html: str) -> list[dict]:
    """Extract product cards (without prices) from the listing HTML."""
    if _PRODUCT_RE is None:
        return []
    cards: list[dict] = []
    seen_ids: set[str] = set()

    for m in _PRODUCT_RE.finditer(listing_html):
        url_path = m.group(1)
        good_id = m.group(2)
        raw_title = m.group(3)

        if good_id in seen_ids:
            continue
        seen_ids.add(good_id)

        title = _clean_text(
            html_lib.unescape(re.sub(r"<[^>]+>", "", raw_title))
        )
        if not title:
            continue

        cards.append({"good_id": good_id, "title": title, "url": url_path})

    return cards


def _fetch_listing() -> str:
    raw = _fetch(LISTING_URL)
    return raw.decode("windows-1251", errors="ignore")


def detect_block_reason(html: str) -> str | None:
    low = html.lower()
    if "429 too many requests" in low or "too many requests" in low:
        return "429 too many requests"
    if (
        "403 forbidden" in low
        or "доступ запрещ" in low
        or "доступ огранич" in low
        or "access denied" in low
    ):
        return "403 forbidden"
    return None


def _build_offers(cards: list[dict]) -> list[ProductOffer]:
    now = datetime.now(timezone.utc).isoformat()
    offers: list[ProductOffer] = []

    for card in cards:
        price = _fetch_min_price(card["good_id"])
        if price is None:
            continue  # product not available / no price

        full_url = BASE_URL + card["url"]
        offers.append(
            ProductOffer(
                source="НИКС",
                title=card["title"],
                price=price,
                currency="RUB",
                url=full_url,
                condition="new",
                seller="НИКС",
                availability="in_stock",
                checked_at=now,
                confidence=0.9,
                raw_text=card["title"],
            )
        )

    return offers


def parse_offers_with_status(browser_mode: bool = False) -> dict:
    if not _FILTER:
        return _NOT_CONFIGURED
    try:
        listing_html = _fetch_listing()
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
                "warnings": [NIX_BLOCK_WARNING],
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

    cards = parse_cards(listing_html)
    if not cards:
        block_reason = detect_block_reason(listing_html)
        if block_reason:
            return {
                "offers": [],
                "blocked": True,
                "block_reason": block_reason,
                "warnings": [NIX_BLOCK_WARNING],
                "errors": 1,
            }
        return {
            "offers": [],
            "blocked": False,
            "block_reason": None,
            "warnings": [],
            "errors": 0,
        }

    offers = _build_offers(cards)
    return {
        "offers": offers,
        "blocked": False,
        "block_reason": None,
        "warnings": [],
        "errors": 0,
    }


def parse_offers(browser_mode: bool = False) -> list[ProductOffer]:
    return parse_offers_with_status(browser_mode)["offers"]
