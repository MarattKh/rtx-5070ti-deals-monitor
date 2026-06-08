from __future__ import annotations

import html as html_lib
import re
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from models import ProductOffer
from parsers.common import _clean_text
from target_config import get_source_filter

_FILTER = get_source_filter("Позитроника")
CATALOG_URL = (
    f"https://www.positronica.ru/catalog/videokarty/?set_filter=y&{_FILTER}=Y"
    if _FILTER else ""
)
BASE_URL = "https://www.positronica.ru"

_NOT_CONFIGURED = {
    "offers": [], "blocked": False, "block_reason": None,
    "warnings": ["Источник не настроен для данного товара"], "errors": 0,
}

# Full browser UA — positronica.ru behaves differently for truncated agents
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Positronica is a Bitrix CMS shop. No schema.org Product microdata/JSON-LD is
# present in the catalog listing; we parse HTML directly.
#
# Layout: items are in <div class="catalog__item" data-id="N">…</div> blocks
# bounded by <!-- items-container --> comments on each side. Within each block:
#   • product URL + title live in the first  href="/product/…" title="…"  anchor
#   • price lives in  <span class="product__price[…]">131 790 ₽</span>
#   • out-of-stock items have no product__price span → skipped
ITEM_RE = re.compile(
    r'<div[^>]+class="catalog__item"[^>]+data-id="\d+"[^>]*>(.*?)'
    r'(?=<div[^>]+class="catalog__item"|<!-- items-container -->)',
    re.S,
)
LINK_RE = re.compile(r'href="(/product/[^"]+)"[^>]+title="([^"]+)"')
PRICE_RE = re.compile(r'class="product__price[^"]*"[^>]*>([^<]+)</span>')

POSITRONICA_BLOCK_WARNING = "Позитроника access blocked. Manual verification required."


def _download(url: str) -> str:
    req = Request(url, headers={"User-Agent": _UA})
    with urlopen(req, timeout=10) as r:  # nosec B310
        return r.read().decode("utf-8", errors="ignore")


def parse_cards(html: str) -> list[dict]:
    cards: list[dict] = []
    seen_urls: set[str] = set()

    for m in ITEM_RE.finditer(html):
        block = m.group(1)
        link_m = LINK_RE.search(block)
        price_m = PRICE_RE.search(block)

        if not (link_m and price_m):
            continue

        url = link_m.group(1).strip()
        if url in seen_urls:
            continue

        title = _clean_text(html_lib.unescape(link_m.group(2)))
        price_raw = html_lib.unescape(price_m.group(1))
        digits = re.sub(r"[^\d]", "", price_raw)
        try:
            price = float(digits)
        except ValueError:
            continue

        if not title or not price:
            continue

        seen_urls.add(url)
        cards.append({"title": title, "price": price, "url": url})

    return cards


def detect_block_reason(html: str) -> str | None:
    normalized = html.lower()
    if "429 too many requests" in normalized or "too many requests" in normalized:
        return "429 too many requests"
    if (
        "403 forbidden" in normalized
        or "доступ запрещ" in normalized
        or "доступ огранич" in normalized
        or "access denied" in normalized
    ):
        return "403 forbidden"
    return None


def _build_offers(html: str) -> list[ProductOffer]:
    now = datetime.now(timezone.utc).isoformat()
    offers: list[ProductOffer] = []

    for c in parse_cards(html):
        full_url = c["url"] if c["url"].startswith("http") else f"{BASE_URL}{c['url']}"
        offers.append(
            ProductOffer(
                source="Позитроника",
                title=c["title"],
                price=c["price"],
                currency="RUB",
                url=full_url,
                condition="new",
                seller="Позитроника",
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
                "warnings": [POSITRONICA_BLOCK_WARNING],
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
            "warnings": [POSITRONICA_BLOCK_WARNING],
            "errors": 1,
        }

    return {"offers": [], "blocked": False, "block_reason": None, "warnings": [], "errors": 0}


def parse_offers(browser_mode: bool = False) -> list[ProductOffer]:
    return parse_offers_with_status(browser_mode)["offers"]
