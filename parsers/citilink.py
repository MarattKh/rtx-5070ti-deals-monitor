from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.error import URLError

from models import ProductOffer
from parsers.browser import fetch_html
from parsers.common import _clean_text, _download, build_search_url, parse_rub

SEARCH_URL = build_search_url("https://www.citilink.ru/search/?text={query}")
BASE_URL = "https://www.citilink.ru"

CARD_RE = re.compile(r'(<article[^>]+class="[^"]*product-card[^"]*"[^>]*>.*?</article>)', re.S)
TITLE_RE = re.compile(
    r'class="[^"]*ProductCardHorizontal__title[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    re.S,
)
PRICE_RE = re.compile(
    r'class="[^"]*ProductCardHorizontal__price_current-price[^"]*"[^>]*>(.*?)</',
    re.S,
)
AVAIL_RE = re.compile(
    r'class="[^"]*ProductCardHorizontal__availability[^"]*"[^>]*>(.*?)</',
    re.S,
)

SNIPPET_TITLE_RE = re.compile(
    r'<a[^>]+href="(?P<url>/product/[^"]+)"[^>]+data-meta-name="Snippet__title"[^>]+title="(?P<title>[^"]+)"[^>]*>',
    re.I | re.S,
)
SNIPPET_PRICE_RE = re.compile(r'data-meta-price="(?P<price>\d+)"', re.I)

CITILINK_BLOCK_WARNING = "Citilink access blocked. Manual verification required."


def _parse_legacy_cards(html: str) -> list[dict]:
    cards: list[dict] = []

    for block in CARD_RE.findall(html):
        t = TITLE_RE.search(block)
        p = PRICE_RE.search(block)
        if not t or not p:
            continue

        url = t.group(1)
        title = _clean_text(t.group(2))
        price = parse_rub(_clean_text(p.group(1)))

        if not price or not title:
            continue

        av = AVAIL_RE.search(block)
        availability = _clean_text(av.group(1)) if av else "unknown"

        cards.append(
            {
                "title": title,
                "url": url,
                "price": price,
                "availability": availability,
            }
        )

    return cards


def _find_nearest_price(html: str, title_pos: int) -> float | None:
    window_start = max(0, title_pos - 9000)
    window_end = min(len(html), title_pos + 9000)
    window = html[window_start:window_end]

    matches = list(SNIPPET_PRICE_RE.finditer(window))
    if not matches:
        return None

    relative_title_pos = title_pos - window_start
    nearest = min(matches, key=lambda m: abs(m.start() - relative_title_pos))
    return float(nearest.group("price"))


def _parse_snippet_cards(html: str) -> list[dict]:
    cards: list[dict] = []
    seen_urls: set[str] = set()

    for m in SNIPPET_TITLE_RE.finditer(html):
        url = m.group("url")
        title = _clean_text(m.group("title"))

        if not title or url in seen_urls:
            continue

        price = _find_nearest_price(html, m.start())
        if not price:
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


def parse_cards(html: str) -> list[dict]:
    legacy = _parse_legacy_cards(html)
    if legacy:
        return legacy

    return _parse_snippet_cards(html)


def detect_block_reason(html: str) -> str | None:
    normalized = html.lower()
    if "429 too many requests" in normalized or "too many requests" in normalized:
        return "429 too many requests"
    if (
        "403 forbidden" in normalized
        or "http 403" in normalized
        or "access denied" in normalized
        or "access forbidden" in normalized
        or "security check" in normalized
        or "доступ запрещ" in normalized
        or "доступ огранич" in normalized
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
                source="Ситилинк",
                title=c["title"],
                price=c["price"],
                currency="RUB",
                url=full_url,
                condition="new",
                seller="Ситилинк",
                availability=c["availability"],
                checked_at=now,
                confidence=0.85,
                raw_text=c["title"],
            )
        )

    return offers


def parse_offers_with_status(browser_mode: bool = False) -> dict:
    try:
        html = fetch_html(SEARCH_URL, save_to="debug_html/citilink.html") if browser_mode else _download(SEARCH_URL)
    except URLError as exc:
        code = getattr(exc, "code", None)
        if code in (401, 403, 429):
            reason = {
                401: "401 unauthorized",
                403: "403 forbidden",
                429: "429 too many requests",
            }[code]
            return {
                "offers": [],
                "blocked": True,
                "block_reason": reason,
                "warnings": [CITILINK_BLOCK_WARNING],
                "errors": 1,
            }
        warning = str(exc) or "Citilink download failed."
        return {
            "offers": [],
            "blocked": False,
            "block_reason": None,
            "warnings": [warning],
            "errors": 1,
        }

    block_reason = detect_block_reason(html)
    if block_reason:
        return {
            "offers": [],
            "blocked": True,
            "block_reason": block_reason,
            "warnings": [CITILINK_BLOCK_WARNING],
            "errors": 1,
        }

    return {
        "offers": _build_offers(html),
        "blocked": False,
        "block_reason": None,
        "warnings": [],
        "errors": 0,
    }


def parse_offers(browser_mode: bool = False) -> list[ProductOffer]:
    status = parse_offers_with_status(browser_mode)
    if status["offers"] or browser_mode or status["blocked"] or status["errors"]:
        return status["offers"]

    return parse_offers_with_status(browser_mode=True)["offers"]

