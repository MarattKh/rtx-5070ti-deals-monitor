from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import json
from typing import Iterable

from models import ProductOffer
from monitor_5070_ti_v_2 import ENABLED_SOURCES, is_accessory_or_invalid, is_rtx_5070_ti, load_config


def reject_reason(offer: ProductOffer, config: dict[str, int] | None = None) -> str | None:
    if config is None:
        config = load_config()
    if offer.price <= 0:
        return "invalid_price"
    if offer.currency.upper() != "RUB":
        return "non_rub_currency"
    url = offer.url.lower()
    if "?q=" in url or "?text=" in url or "/search" in url:
        return "search_url"
    if not is_rtx_5070_ti(offer.title, offer.raw_text):
        return "not_rtx_5070_ti"
    if is_accessory_or_invalid(offer.title, offer.raw_text):
        return "accessory_or_invalid"
    return None


def summarize_rejections(offers: Iterable[ProductOffer], config: dict[str, int] | None = None) -> dict[str, int]:
    if config is None:
        config = load_config()
    reasons: Counter[str] = Counter()
    for offer in offers:
        reason = reject_reason(offer, config)
        if reason:
            reasons[reason] += 1
        else:
            reasons["accepted"] += 1
    return dict(reasons)


def _load_source(source_name: str):
    normalized = source_name.casefold()
    for name, module in ENABLED_SOURCES:
        if name.casefold() == normalized:
            return name, module
    raise SystemExit(f"Unknown source: {source_name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="Source name from ENABLED_SOURCES, for example: Яндекс Маркет")
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()

    name, module = _load_source(args.source)
    offers = list(module.parse_offers())
    config = load_config()
    print(f"Source: {name}")
    print(f"Raw offers: {len(offers)}")
    print("Reasons:", json.dumps(summarize_rejections(offers, config), ensure_ascii=False, sort_keys=True))
    for offer in offers[: args.limit]:
        row = asdict(offer)
        row["reject_reason"] = reject_reason(offer, config)
        row["title"] = row["title"][:220]
        row["raw_text"] = row["raw_text"][:500]
        print(json.dumps(row, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
