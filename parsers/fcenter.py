from __future__ import annotations

import html as html_lib
import re
import ssl
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from models import ProductOffer
from parsers.common import _clean_text
from target_config import get_source_filter

_FILTER = get_source_filter("Ф-Центр")
CATALOG_URL = f"https://fcenter.ru/product/type/7?param={_FILTER}" if _FILTER else ""
BASE_URL = "https://fcenter.ru"

_NOT_CONFIGURED = {
    "offers": [], "blocked": False, "block_reason": None,
    "warnings": ["Источник не настроен для данного товара"], "errors": 0,
}

# Full Chrome UA required — fcenter.ru rejects short/truncated user-agents
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

FCENTER_BLOCK_WARNING = "Ф-Центр access blocked. Manual verification required."

ITEM_RE = re.compile(
    r'class="pic-table-item col_12"(.*?)(?=class="pic-table-item col_12"|$)',
    re.S,
)
LINK_RE = re.compile(
    r'<a\s+class="goods-link"\s+href="(/product/goods/\d+[^"]+)"\s+title="([^"]+)"',
    re.S,
)
PRICE_RE = re.compile(r'class="do-price">\s*([\d\s ]+)<sup', re.S)


def _download_fcenter(url: str) -> str:
    # fcenter.ru has a self-signed / hostname-mismatched SSL cert
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=15, context=ctx) as r:  # nosec B310
        return r.read().decode("utf-8", errors="ignore")


def parse_cards(html: str) -> list[dict]:
    cards: list[dict] = []
    seen_urls: set[str] = set()

    for m in ITEM_RE.finditer(html):
        block = m.group(1)
        link = LINK_RE.search(block)
        price_m = PRICE_RE.search(block)

        if not link or not price_m:
            continue

        url = link.group(1)
        if url in seen_urls:
            continue

        title = _clean_text(html_lib.unescape(link.group(2)))
        price_raw = re.sub(r"[^\d]", "", price_m.group(1))
        try:
            price = float(price_raw)
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
                source="Ф-Центр",
                title=c["title"],
                price=c["price"],
                currency="RUB",
                url=full_url,
                condition="new",
                seller="Ф-Центр",
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
        html = _download_fcenter(CATALOG_URL)
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
                "warnings": [FCENTER_BLOCK_WARNING],
                "errors": 1,
            }
        return {
            "offers": [],
            "blocked": False,
            "block_reason": None,
            "warnings": [str(exc)],
            "errors": 1,
        }
    except (URLError, TimeoutError, OSError) as exc:
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
            "warnings": [FCENTER_BLOCK_WARNING],
            "errors": 1,
        }

    return {"offers": [], "blocked": False, "block_reason": None, "warnings": [], "errors": 0}


def parse_offers(browser_mode: bool = False) -> list[ProductOffer]:
    return parse_offers_with_status(browser_mode)["offers"]
