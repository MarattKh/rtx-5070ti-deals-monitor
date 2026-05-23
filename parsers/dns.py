from __future__ import annotations

import html as html_module
import re
from datetime import datetime, timezone
from urllib.error import URLError

from models import ProductOffer
from parsers.browser import fetch_html
from parsers.common import _download, _clean_text, parse_rub

CARD_RE = re.compile(r'(<div[^>]+class="[^"]*catalog-product[^"]*"[^>]*>.*?</div>\s*</div>)', re.S)
TITLE_RE = re.compile(r'class="[^"]*catalog-product__name[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
PRICE_RE = re.compile(r'class="[^"]*product-buy__price[^"]*"[^>]*>(.*?)</', re.S)
AVAIL_RE = re.compile(r'class="[^"]*(?:order-avail-wrap|product-buy__avail)[^"]*"[^>]*>(.*?)</', re.S)

PRODUCT_LINK_RE = re.compile(r'<a[^>]+href="([^"]*/product/[^"]+)"[^>]*>(.*?)</a>', re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>", re.S)
PRICE_AROUND_RE = re.compile(r"(\d[\d\s\u00a0]{3,})\s*(?:₽|руб)", re.I)

DNS_BLOCK_WARNING = "DNS access forbidden. Manual verification required."
DNS_QRATOR_WARNING = "DNS browser HTML looks like Qrator anti-bot challenge. Manual verification required."
DNS_NO_CARDS_WARNING = "DNS browser HTML contains no parsed product cards. Possible parser mismatch, empty state, or anti-bot page."
DNS_EMPTY_WARNING = "DNS search returned empty result page."


def _plain_text(html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = TAG_RE.sub(" ", text)
    return _clean_text(html_module.unescape(text))


def _strip_tags(value: str) -> str:
    return _clean_text(html_module.unescape(TAG_RE.sub(" ", value)))


def diagnose_html(html: str) -> dict:
    normalized = html.lower()
    text = _plain_text(html).lower()

    captcha_keywords = (
        "captcha",
        "robot",
        "verify",
        "verification",
        "challenge",
        "провер",
        "капч",
        "бот",
    )
    empty_keywords = (
        "ничего не найдено",
        "ничего не найден",
        "не найдено",
        "empty",
        "no results",
    )

    is_qrator = "__qrator" in normalized or "qauth" in normalized or "/__qrator/" in normalized
    has_captcha = is_qrator or any(keyword in normalized or keyword in text for keyword in captcha_keywords)
    has_empty = any(keyword in text for keyword in empty_keywords)

    return {
        "html_size": len(html),
        "contains_rtx": "rtx" in normalized,
        "contains_5070": "5070" in normalized,
        "contains_catalog_product": "catalog-product" in normalized,
        "contains_product_link": "/product/" in normalized,
        "contains_qrator": is_qrator,
        "contains_captcha": has_captcha,
        "contains_empty": has_empty,
    }


def parse_cards(html: str) -> list[dict]:
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
        cards.append({"title": title, "url": url, "price": price, "availability": availability})

    if cards:
        return cards

    seen_urls: set[str] = set()
    for match in PRODUCT_LINK_RE.finditer(html):
        url = html_module.unescape(match.group(1))
        if url in seen_urls or "/search" in url or "/catalog" in url:
            continue

        raw_title = _strip_tags(match.group(2))
        if not raw_title:
            continue

        title_lower = raw_title.lower()
        if "5070" not in title_lower or "ti" not in title_lower:
            continue

        start = max(0, match.start() - 2500)
        end = min(len(html), match.end() + 2500)
        nearby = html[start:end]
        price_match = PRICE_AROUND_RE.search(_plain_text(nearby))
        price = parse_rub(price_match.group(0)) if price_match else None
        if not price:
            continue

        seen_urls.add(url)
        cards.append(
            {
                "title": raw_title,
                "url": url,
                "price": price,
                "availability": "unknown",
            }
        )

    return cards


def detect_block_reason(html: str) -> str | None:
    normalized = html.lower()
    if (
        "403 forbidden" in normalized
        or "403 error" in normalized
        or "http 403" in normalized
        or "access to www.dns-shop.ru is forbidden" in normalized
        or "доступ к сайту запрещен" in normalized
    ):
        return "403 forbidden"
    return None


def _problem_warnings(html: str, browser_mode: bool) -> tuple[list[str], int]:
    diagnostics = diagnose_html(html)

    if diagnostics["contains_qrator"]:
        return [DNS_QRATOR_WARNING], 1

    if diagnostics["contains_captcha"]:
        return ["DNS browser HTML looks like captcha/anti-bot page. Manual verification required."], 1

    if diagnostics["contains_empty"]:
        return [DNS_EMPTY_WARNING], 1

    if browser_mode:
        return [DNS_NO_CARDS_WARNING], 1

    return [], 0


def _build_offers(html: str) -> list[ProductOffer]:
    now = datetime.now(timezone.utc).isoformat()
    offers: list[ProductOffer] = []
    for c in parse_cards(html):
        full_url = c["url"] if c["url"].startswith("http") else f"https://www.dns-shop.ru{c['url']}"
        offers.append(
            ProductOffer(
                "DNS",
                c["title"],
                c["price"],
                "RUB",
                full_url,
                "new",
                "DNS",
                c["availability"],
                now,
                0.85,
                c["title"],
            )
        )
    return offers


def parse_offers_with_status(browser_mode: bool = False) -> dict:
    search_url = "https://www.dns-shop.ru/search/?q=rtx+5070+ti"
    try:
        if browser_mode:
            html = fetch_html(
                search_url,
                save_to="debug_html/dns.html",
                wait_selectors=[
                    ".catalog-product",
                    "[data-role='catalog-product']",
                    ".product-card",
                    ".catalog-products",
                ],
                extra_delay_ms=1500,
                screenshot_to="debug_html/dns.png",
            )
        else:
            html = _download(search_url)
    except URLError as exc:
        code = getattr(exc, "code", None)
        if code in (401, 403):
            return {
                "offers": [],
                "blocked": True,
                "block_reason": "401 unauthorized" if code == 401 else "403 forbidden",
                "warnings": [DNS_BLOCK_WARNING],
                "errors": 1,
            }
        warning = str(exc) or "DNS download failed."
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
            "warnings": [DNS_BLOCK_WARNING],
            "errors": 1,
        }

    offers = _build_offers(html)
    warnings, errors = ([], 0) if offers else _problem_warnings(html, browser_mode)

    return {
        "offers": offers,
        "blocked": False,
        "block_reason": None,
        "warnings": warnings,
        "errors": errors,
    }


def parse_offers(browser_mode: bool = False) -> list[ProductOffer]:
    return parse_offers_with_status(browser_mode)["offers"]