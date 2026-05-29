from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from models import ProductOffer

_TRACKING_QUERY_KEYS = {"yclid", "gclid", "fbclid"}


def normalize_offer_url(url: str) -> str:
    """Return a stable URL key for offer deduplication."""
    raw = (url or "").strip()
    if not raw:
        return ""

    parts = urlsplit(raw)
    if not parts.scheme and not parts.netloc:
        return raw.rstrip("/")

    query_items = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_QUERY_KEYS
    ]
    query = urlencode(sorted(query_items), doseq=True)
    path = parts.path.rstrip("/") or parts.path
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def normalize_offer_text(text: str) -> str:
    return " ".join((text or "").casefold().replace("-", " ").split())


def offer_dedup_key(offer: ProductOffer) -> tuple[str, ...]:
    normalized_url = normalize_offer_url(offer.url)
    if normalized_url:
        return ("url", normalized_url)
    return (
        "fallback",
        normalize_offer_text(offer.source),
        normalize_offer_text(offer.title),
        str(int(round(float(offer.price)))),
        normalize_offer_text(offer.condition),
    )


def deduplicate_offers(offers: list[ProductOffer]) -> list[ProductOffer]:
    """Deduplicate filtered offers, keeping the cheapest row for each stable key."""
    by_key: dict[tuple[str, ...], ProductOffer] = {}
    for offer in offers:
        key = offer_dedup_key(offer)
        current = by_key.get(key)
        if current is None or (offer.price, offer.source, offer.title, offer.url) < (
            current.price,
            current.source,
            current.title,
            current.url,
        ):
            by_key[key] = offer

    return sorted(by_key.values(), key=lambda offer: (offer.price, offer.source, offer.title, offer.url))
