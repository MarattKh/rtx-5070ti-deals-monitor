from __future__ import annotations

import argparse
import csv
import json
import logging
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from models import ProductOffer

from parsers import (
    aliexpress,
    avito,
    cdek_shopping,
    computeruniverse,
    dns,
    eldorado,
    mvideo,
    megamarket,
    ozon,
    regard,
    citilink,
    wildberries,
    yandex_market,
)

MAX_PRICE_RUB = 130_000



def configure_logging() -> None:
    logging.basicConfig(
        filename="monitor.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )


def normalize_title(text: str) -> str:
    return " ".join(text.lower().replace("-", " ").split())


def is_rtx_5070_ti(title: str, raw_text: str) -> bool:
    haystack = normalize_title(f"{title} {raw_text}")
    compact = haystack.replace(" ", "")
    return "5070ti" in compact or ("5070" in haystack and "ti" in haystack)


def is_accessory_or_invalid(title: str, raw_text: str) -> bool:
    haystack = normalize_title(f"{title} {raw_text}")
    compact = haystack.replace(" ", "")

    bad_keywords = [
        "5070 super",
        "кабель",
        "переходник",
        "кулер",
        "водоблок",
        "waterblock",
        "ноутбук",
        "laptop",
        "компьютер",
        "системный блок",
        "gaming pc",
        "pc",
        "пк",
        "корпус",
        "держатель",
        "подставка",
        "чехол",
        "fan",
    ]

    if "5070 ti" not in haystack and "5070ti" not in compact:
        return True

    return any(keyword in haystack for keyword in bad_keywords)

def filter_offers(offers: Iterable[ProductOffer]) -> list[ProductOffer]:
    out: list[ProductOffer] = []
    for item in offers:
        if item.price <= 0:
            continue
        if item.currency.upper() != "RUB":
            continue
        if item.price > MAX_PRICE_RUB:
            continue
        u = item.url.lower()
        if "?q=" in u or "?text=" in u or "/search" in u:
            continue
        if not is_rtx_5070_ti(item.title, item.raw_text):
            continue
        if is_accessory_or_invalid(item.title, item.raw_text):
            continue
        norm = normalize_title(item.title + " " + item.raw_text)
        if "5070 ti" not in norm and "5070ti" not in norm.replace(" ", ""):
            continue
        out.append(item)
    out.sort(key=lambda x: x.price)
    return out


def classify_signal(item: ProductOffer) -> str | None:
    c = item.condition.lower()
    if c == "new":
        if item.price <= 75_000:
            return "urgent_buy"
        if item.price <= 90_000:
            return "good_price"
    if c == "used":
        if item.price <= 50_000:
            return "urgent_buy"
        if item.price <= 65_000:
            return "good_price"
    return None


def get_signal_label(item: ProductOffer) -> str:
    signal = classify_signal(item)
    if signal == "urgent_buy":
        return "URGENT_BUY"
    if signal == "good_price":
        return "GOOD_PRICE"
    return "NORMAL"


def render_markdown(offers: list[ProductOffer]) -> str:
    lines = [
        "# RTX 5070 Ti offers",
        "",
        "| Source | Title | Price | Condition | Availability | Signal | URL |",
        "|---|---|---:|---|---|---|---|",
    ]
    for o in offers:
        lines.append(
            f"| {o.source} | {o.title.replace('|', '/')} | {o.price:.0f} {o.currency} | {o.condition} | {o.availability} | {get_signal_label(o)} | {o.url} |"
        )
    return "\n".join(lines) + "\n"


def render_results_markdown(offers: list[ProductOffer], source_stats: list[dict[str, str | int]]) -> str:
    checked_at = datetime.now(timezone.utc).isoformat()
    min_price = f"{min(o.price for o in offers):.0f} RUB" if offers else "n/a"
    urgent_count = sum(1 for o in offers if get_signal_label(o) == "URGENT_BUY")
    good_price_count = sum(1 for o in offers if get_signal_label(o) == "GOOD_PRICE")
    normal_count = sum(1 for o in offers if get_signal_label(o) == "NORMAL")

    lines = [
        "# RTX 5070 Ti offers",
        "",
        "## Summary",
        "",
        f"- Checked at: {checked_at}",
        f"- Total offers after filter: {len(offers)}",
        f"- Min price: {min_price}",
                f"- urgent_buy count: {urgent_count}",
        f"- good_price count: {good_price_count}",
        f"- normal count: {normal_count}",
                f"- best offer: {offers[0].price:.0f} {offers[0].currency} | {offers[0].source} | {offers[0].title} | {offers[0].url}" if offers else "- best offer: n/a",
        "",
        "## Best offers",
        "",
    ]

    best_offers = [o for o in offers if get_signal_label(o) in {"URGENT_BUY", "GOOD_PRICE"}]
    if best_offers:
        lines.extend(
            [
                "| Source | Title | Price | Condition | Availability | Signal | URL |",
                "|---|---|---:|---|---|---|---|",
            ]
        )
        for o in best_offers:
            lines.append(
                f"| {o.source} | {o.title.replace('|', '/')} | {o.price:.0f} {o.currency} | {o.condition} | {o.availability} | {get_signal_label(o)} | {o.url} |"
            )
    else:
        lines.append("No urgent/good-price offers found.")

    lines.extend(
        [
            "",
            "## Source summary",
            "",
            "| Source | Raw count | Filtered count | Error |",
            "|---|---:|---:|---|",
        ]
    )

    for stat in source_stats:
        lines.append(
            f"| {stat['source']} | {stat['raw_count']} | {stat['filtered_count']} | {stat['error']} |"
        )

    lines.extend(
        [
            "",
            "## Offers",
"",
"| Source | Title | Price | Condition | Availability | Signal | URL |",
"|---|---|---:|---|---|---|---|",
        ]
    )

    for o in offers:
        lines.append(
            f"| {o.source} | {o.title.replace('|', '/')} | {o.price:.0f} {o.currency} | {o.condition} | {o.availability} | {get_signal_label(o)} | {o.url} |"
        )

    return "\n".join(lines) + "\n"


def save_reports(offers: list[ProductOffer], source_stats: list[dict[str, str | int]] | None = None) -> None:
    if source_stats is None:
        source_stats = []

    Path("results.json").write_text(
        json.dumps([asdict(x) for x in offers], ensure_ascii=False, indent=2), encoding="utf-8"
    )

    with open("results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(offers[0]).keys()) if offers else [
            "source","title","price","currency","url","condition","seller","availability","checked_at","confidence","raw_text"
        ])
        w.writeheader()
        for x in offers:
            w.writerow(asdict(x))

    Path("results.md").write_text(render_results_markdown(offers, source_stats), encoding="utf-8")

    urgent = [o for o in offers if classify_signal(o) == "urgent_buy"]
    Path("urgent_deals.md").write_text(render_markdown(urgent), encoding="utf-8")

    prompt = (
        "Проанализируй список предложений RTX 5070 Ti, выдели аномально дешевые, "
        "проверь возможные риски продавца и предложи стратегию покупки."
    )
    Path("latest_ai_prompt.md").write_text(prompt + "\n", encoding="utf-8")


def _telegram_signal_offers(offers: list[ProductOffer]) -> list[ProductOffer]:
    priority = {"urgent_buy": 0, "good_price": 1}
    interesting = [o for o in offers if classify_signal(o) in {"urgent_buy", "good_price"}]
    interesting.sort(key=lambda o: (priority[classify_signal(o) or "good_price"], o.price))
    return interesting


def _append_source_summary(lines: list[str], source_stats: list[dict[str, str | int]]) -> None:
    lines.append("Source summary:")
    if source_stats:
        for stat in source_stats:
            lines.append(f"{stat['source']}: raw {stat['raw_count']} / filtered {stat['filtered_count']}")
    else:
        lines.append("n/a")


def build_telegram_signal_text(offers: list[ProductOffer], source_stats: list[dict[str, str | int]] | None = None) -> str | None:
    if source_stats is None:
        source_stats = []

    interesting = _telegram_signal_offers(offers)
    if not interesting:
        return None

    top_items = interesting[:10]
    lines = ["⚡ RTX 5070 Ti мониторинг", "", "Best signals:"]
    for idx, offer in enumerate(top_items, start=1):
        lines.extend(
            [
                f"{idx}. {get_signal_label(offer)} — {offer.price:.0f} RUB — {offer.source}",
                offer.title,
                offer.url,
                "",
            ]
        )

    _append_source_summary(lines, source_stats)
    lines.append("")
    lines.append(f"Total signals: {len(interesting)}")
    return "\n".join(lines)[:4000]


def build_telegram_daily_report_text(offers: list[ProductOffer], source_stats: list[dict[str, str | int]] | None = None) -> str:
    if source_stats is None:
        source_stats = []

    signals = _telegram_signal_offers(offers)
    lines = ["📊 RTX 5070 Ti daily report", "", f"Signals: {len(signals)}"]

    if signals:
        lines.extend(["", "Best signals:"])
        for idx, offer in enumerate(signals[:10], start=1):
            lines.extend(
                [
                    f"{idx}. {get_signal_label(offer)} — {offer.price:.0f} RUB — {offer.source}",
                    offer.title,
                    offer.url,
                    "",
                ]
            )

    if offers:
        best = offers[0]
        lines.extend(
            [
                "Best price:",
                f"{best.price:.0f} {best.currency} — {best.source}",
                best.title,
                best.url,
                "",
            ]
        )
    else:
        lines.extend(["", "Best price: n/a", ""])

    _append_source_summary(lines, source_stats)
    lines.append("")
    lines.append(f"Total offers: {len(offers)}")
    return "\n".join(lines)[:4000]


def notify_telegram(
    offers: list[ProductOffer],
    source_stats: list[dict[str, str | int]] | None = None,
    daily_report: bool = False,
) -> None:
    if source_stats is None:
        source_stats = []

    token = os.getenv("TG_BOT_TOKEN")
    chat_id = os.getenv("TG_CHAT_ID")
    if not token or not chat_id:
        return

    try:
        import requests

        if daily_report:
            text = build_telegram_daily_report_text(offers, source_stats)
        else:
            text = build_telegram_signal_text(offers, source_stats)
            if not text:
                return

        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text[:4000]},
            timeout=15,
        )
    except Exception as exc:
        logging.getLogger("telegram").exception("telegram error: %s", exc)


def run_source(name: str, fn) -> tuple[list[ProductOffer], str]:
    logger = logging.getLogger(name)
    try:
        if callable(fn):
            return fn(), ""
        return fn.parse_offers(), ""
    except Exception as exc:
        logger.exception("source failed: %s", exc)
        return [], str(exc)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", action="store_true", help="Use Playwright browser mode for DNS and Ситилинк")
    parser.add_argument("--daily-report", action="store_true", help="Send Telegram daily report even without buy signals")
    args = parser.parse_args()

    configure_logging()
    sources = {
        "DNS": dns,
        "Ситилинк": citilink,
        "Регард": regard,
    }
    collected: list[ProductOffer] = []
    source_stats: list[dict[str, str | int]] = []

    for name, module in sources.items():
        if module in (dns, citilink):
            source_offers, error = run_source(name, lambda m=module: m.parse_offers(browser_mode=args.browser))
        else:
            source_offers, error = run_source(name, module)

        collected.extend(source_offers)

        filtered_count = len(filter_offers(source_offers))
        source_stats.append(
            {
                "source": name,
                "raw_count": len(source_offers),
                "filtered_count": filtered_count,
                "error": error,
            }
        )

    filtered = filter_offers(collected)
    save_reports(filtered, source_stats)
    notify_telegram(filtered, source_stats, daily_report=args.daily_report)

    print("Source summary:")
    for stat in source_stats:
        error_suffix = f" (error: {stat['error']})" if stat["error"] else ""
        print(f"{stat['source']}: raw {stat['raw_count']} / filtered {stat['filtered_count']}{error_suffix}")

    print(f"Total offers after filter: {len(filtered)}")


if __name__ == "__main__":
    main()
