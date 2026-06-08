from __future__ import annotations

import html as html_lib
import re
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.parse import quote, quote_plus, urljoin
from urllib.request import Request, urlopen

from models import ProductOffer
from target_config import get_query

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
PRICE_RE = re.compile(r"(\d[\d\s\u00a0]{2,9})\s?(₽|руб|RUB)", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
HREF_RE = re.compile(r"href=[\"']([^\"']+)[\"']", re.IGNORECASE)


def parse_rub(value: str) -> float | None:
    digits = re.sub(r"[^\d]", "", value)
    return float(digits) if digits else None


def build_search_url(template: str, query: str | None = None, *, plus: bool = False) -> str:
    """Build a source search URL from a ``{query}`` template and the target query.

    *plus* selects ``+`` form encoding (``quote_plus``) for hosts that use it
    instead of ``%20`` (``quote``). With the default "rtx 5070 ti" query this
    reproduces each source's original hard-coded URL byte-for-byte.
    """
    if query is None:
        query = get_query()
    encoded = quote_plus(query) if plus else quote(query)
    return template.format(query=encoded)


def _download(url: str) -> str:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=6) as r:  # nosec B310
        return r.read().decode("utf-8", errors="ignore")


def _clean_text(fragment: str) -> str:
    plain = TAG_RE.sub(" ", fragment)
    plain = html_lib.unescape(plain)
    return " ".join(plain.split())


def _is_search_url(url: str) -> bool:
    u = url.lower()
    return "?q=" in u or "?text=" in u or "/search" in u


def _debug_file_name(source: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", source.lower()).strip("_")
    return safe or "source"


def _extract_product_offers_from_html(source: str, search_url: str, page: str, seller: str = "") -> list[ProductOffer]:
    now = datetime.now(timezone.utc).isoformat()
    offers: list[ProductOffer] = []

    for m in PRICE_RE.finditer(page):
        price = parse_rub(m.group(1))
        if not price:
            continue
        start = max(0, m.start() - 1200)
        end = min(len(page), m.end() + 1200)
        chunk_html = page[start:end]

        href_match = HREF_RE.search(chunk_html)
        if not href_match:
            continue
        card_url = urljoin(search_url, href_match.group(1).strip())
        if _is_search_url(card_url):
            continue

        title = _clean_text(chunk_html)
        if len(title) < 5:
            continue

        lowered = title.lower()
        condition = "used" if any(x in lowered for x in ["б/у", "used"]) else "new"
        availability = "in_stock" if any(x in lowered for x in ["в наличии", "доставка", "купить"]) else "unknown"

        offers.append(
            ProductOffer(
                source=source,
                title=title[:220],
                price=price,
                currency="RUB",
                url=card_url,
                condition=condition,
                seller=seller or source,
                availability=availability,
                checked_at=now,
                confidence=0.55,
                raw_text=title[:1000],
            )
        )
        if len(offers) >= 20:
            break

    return offers


def extract_product_offers(source: str, search_url: str, seller: str = "", browser_fallback: bool = True) -> list[ProductOffer]:
    try:
        page = _download(search_url)
    except URLError:
        page = ""

    offers = _extract_product_offers_from_html(source, search_url, page, seller) if page else []
    if offers or not browser_fallback:
        return offers

    try:
        from parsers.browser import fetch_html

        browser_page = fetch_html(search_url, save_to=f"debug_html/{_debug_file_name(source)}.html")
    except Exception:
        return offers

    return _extract_product_offers_from_html(source, search_url, browser_page, seller)


def scrape_search_page(source: str, url: str, seller: str = "", browser_fallback: bool = True) -> list[ProductOffer]:
    return extract_product_offers(source=source, search_url=url, seller=seller, browser_fallback=browser_fallback)
