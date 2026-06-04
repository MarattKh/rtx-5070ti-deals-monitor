from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse

from models import ProductOffer
from price_oracle import (
    MarketMedian,
    classify_market_tier,
    compute_market_median,
)
from tools.offer_deduplication import deduplicate_offers

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

DEFAULT_CONFIG = {
    "new_good_price": 90_000,
    "new_urgent_buy": 75_000,
    "used_good_price": 65_000,
    "used_urgent_buy": 50_000,
    "median_window_days": 30,
    "median_min_count": 5,
    "suspicious_pct": 65,
    "buy_pct": 90,
    "at_market_pct": 110,
}

PRICE_HISTORY_PATH = Path("price_history.jsonl")

ENABLED_SOURCES: tuple[tuple[str, Any], ...] = (
    ("DNS", dns),
    ("Ситилинк", citilink),
    ("Регард", regard),
    ("М.Видео", mvideo),
    ("Эльдорадо", eldorado),
    ("Wildberries", wildberries),
    ("Мегамаркет", megamarket),
    ("AliExpress", aliexpress),
    ("ComputerUniverse", computeruniverse),
    ("СДЭК Shopping", cdek_shopping),
    ("Ozon", ozon),
    ("Яндекс Маркет", yandex_market),
    ("Avito", avito),
)

STATUS_AWARE_SOURCE_NAMES = {"DNS", "Ситилинк"}
YANDEX_MARKET_OFFER_QUERY_KEYS = {"sku", "offerid", "waremd5"}


def load_config(path: str | Path = "config.json") -> dict[str, int]:
    config = DEFAULT_CONFIG.copy()
    config_path = Path(path)

    if not config_path.exists():
        return config

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            logging.getLogger("config").error("config is not a JSON object: %s", config_path)
            return config

        for key, default_value in DEFAULT_CONFIG.items():
            value = raw.get(key, default_value)
            try:
                config[key] = int(value)
            except (TypeError, ValueError):
                logging.getLogger("config").error("invalid config value for %s: %r", key, value)
                config[key] = default_value

    except Exception as exc:
        logging.getLogger("config").exception("failed to load config %s: %s", config_path, exc)
        return DEFAULT_CONFIG.copy()

    return config


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


_ACCESSORY_RE = re.compile(
    r"\b(?:"
    r"5070\s+super|"
    r"кабель|переходник|кулер|водоблок|waterblock|ноутбук|laptop|компьютер|"
    r"системный\s+блок|gaming\s+pc|"
    r"пк|корпус|держатель|подставка|чехол|"
    r"вентилятор|кронштейн|крепление|термопаста|райзер"
    r")\b"
)


def is_accessory_or_invalid(title: str, raw_text: str) -> bool:
    haystack = normalize_title(f"{title} {raw_text}")
    compact = haystack.replace(" ", "")

    if "5070 ti" not in haystack and "5070ti" not in compact:
        return True

    return bool(_ACCESSORY_RE.search(haystack))


def _is_yandex_market_offer_search_url(item: ProductOffer) -> bool:
    source = item.source.casefold()
    if "yandex market" not in source and "яндекс маркет" not in source:
        return False

    parsed = urlparse(item.url)
    host = parsed.netloc.casefold()
    if host != "market.yandex.ru" and not host.endswith(".market.yandex.ru"):
        return False
    if parsed.path.rstrip("/").casefold() != "/search":
        return False

    query = {key.casefold() for key in parse_qs(parsed.query)}
    return bool(query & YANDEX_MARKET_OFFER_QUERY_KEYS)


def _is_rejected_search_url(item: ProductOffer) -> bool:
    u = item.url.lower()
    if "?q=" not in u and "?text=" not in u and "/search" not in u:
        return False
    return not _is_yandex_market_offer_search_url(item)


def filter_offers(offers: Iterable[ProductOffer], config: dict[str, int] | None = None) -> list[ProductOffer]:
    if config is None:
        config = load_config()
    out: list[ProductOffer] = []
    for item in offers:
        if item.price <= 0:
            continue
        if item.currency.upper() != "RUB":
            continue
        if _is_rejected_search_url(item):
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


def classify_signal(item: ProductOffer, config: dict[str, int] | None = None) -> str | None:
    if config is None:
        config = load_config()

    c = item.condition.lower()
    if c == "new":
        if item.price <= config["new_urgent_buy"]:
            return "urgent_buy"
        if item.price <= config["new_good_price"]:
            return "good_price"
    if c == "used":
        if item.price <= config["used_urgent_buy"]:
            return "urgent_buy"
        if item.price <= config["used_good_price"]:
            return "good_price"
    return None


def get_signal_label(item: ProductOffer, config: dict[str, int] | None = None) -> str:
    signal = classify_signal(item, config)
    if signal == "urgent_buy":
        return "URGENT_BUY"
    if signal == "good_price":
        return "GOOD_PRICE"
    return "NORMAL"


def get_market_tier(
    offer: ProductOffer,
    market_median: MarketMedian | None,
    config: dict[str, int] | None = None,
) -> str:
    if config is None:
        config = load_config()
    if market_median is None:
        return "unknown"
    return classify_market_tier(
        offer.price,
        market_median.value,
        config["suspicious_pct"],
        config["buy_pct"],
        config["at_market_pct"],
    )


def build_price_history_record(
    offer: ProductOffer,
    timestamp: str,
    config: dict[str, int] | None = None,
) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "source": offer.source,
        "title": offer.title,
        "price": offer.price,
        "currency": offer.currency,
        "url": offer.url,
        "condition": offer.condition,
        "availability": offer.availability,
        "signal": get_signal_label(offer, config),
    }


def append_price_history(
    offers: list[ProductOffer],
    path: str | Path = PRICE_HISTORY_PATH,
    config: dict[str, int] | None = None,
    timestamp: str | None = None,
) -> None:
    if config is None:
        config = load_config()
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()

    history_path = Path(path)
    with history_path.open("a", encoding="utf-8") as f:
        for offer in offers:
            record = build_price_history_record(offer, timestamp, config)
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def render_markdown(offers: list[ProductOffer], config: dict[str, int] | None = None) -> str:
    if config is None:
        config = load_config()
    lines = [
        "# RTX 5070 Ti offers",
        "",
        "| Source | Title | Price | Condition | Availability | Signal | URL |",
        "|---|---|---:|---|---|---|---|",
    ]
    for o in offers:
        lines.append(
            f"| {o.source} | {o.title.replace('|', '/')} | {o.price:.0f} {o.currency} | {o.condition} | {o.availability} | {get_signal_label(o, config)} | {o.url} |"
        )
    return "\n".join(lines) + "\n"


def _warnings_list(stat: dict[str, Any]) -> list[str]:
    warnings = stat.get("warnings", [])
    if isinstance(warnings, list):
        return [str(x) for x in warnings if x]
    if warnings:
        return [str(warnings)]
    return []


def _markdown_cell(value: Any) -> str:
    return str(value).replace("|", "/") if value is not None else ""


def classify_source_stat(stat: dict[str, Any]) -> str:
    """Classify one source stats record from the daily monitor run."""
    if stat.get("error"):
        return "error"
    if stat.get("blocked") is True:
        return "unavailable"
    if int(stat.get("filtered_count") or 0) <= 0:
        return "no_filtered_offers"
    return "ok"


def summarize_source_stat(stat: dict[str, Any]) -> dict[str, Any]:
    """Return the compact review summary for one source stats record."""
    classification = classify_source_stat(stat)
    raw_count = int(stat.get("raw_count") or 0)
    filtered_count = int(stat.get("filtered_count") or 0)

    if classification == "error":
        reason = str(stat.get("error"))
    elif classification == "unavailable":
        reason = f"blocked: {stat.get('block_reason') or 'unknown'}"
    elif classification == "no_filtered_offers":
        reason = "raw offers did not pass filters" if raw_count else "no offers after parsing"
    else:
        reason = "ok"

    return {
        "source": str(stat.get("source") or "unknown"),
        "classification": classification,
        "raw_count": raw_count,
        "filtered_count": filtered_count,
        "reason": reason,
        "warnings": _warnings_list(stat),
    }


def summarize_source_stats(source_stats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [summarize_source_stat(stat) for stat in source_stats]


def _format_source_summary_text(stat: dict[str, Any]) -> str:
    summary = summarize_source_stat(stat)
    warnings = "; ".join(summary["warnings"]) if summary["warnings"] else "none"
    return (
        f"{summary['source']}: {summary['classification']}; "
        f"raw {summary['raw_count']}; filtered {summary['filtered_count']}; "
        f"reason: {summary['reason']}; warnings: {warnings}"
    )


def _format_source_summary_markdown_row(stat: dict[str, Any]) -> str:
    summary = summarize_source_stat(stat)
    warnings = "; ".join(summary["warnings"]) if summary["warnings"] else "none"
    return (
        f"| {_markdown_cell(summary['source'])} | {summary['classification']} | "
        f"{summary['raw_count']} | {summary['filtered_count']} | "
        f"{_markdown_cell(summary['reason'])} | {_markdown_cell(warnings)} |"
    )


def _tier_order(tier: str) -> int:
    return {"buy": 0, "suspicious": 1, "at_market": 2, "above_market": 3}.get(tier, 4)


def render_results_markdown(
    offers: list[ProductOffer],
    source_stats: list[dict[str, Any]],
    config: dict[str, int] | None = None,
    market_median: MarketMedian | None = None,
) -> str:
    if config is None:
        config = load_config()
    checked_at = datetime.now(timezone.utc).isoformat()
    min_price = f"{min(o.price for o in offers):.0f} RUB" if offers else "n/a"

    tier_list = [(o, get_market_tier(o, market_median, config)) for o in offers]
    tier_counts = {t: sum(1 for _, v in tier_list if v == t) for t in ("suspicious", "buy", "at_market", "above_market", "unknown")}

    lines = [
        "# RTX 5070 Ti offers",
        "",
        "## Summary",
        "",
        f"- Checked at: {checked_at}",
        f"- Total offers: {len(offers)}",
        f"- Min price: {min_price}",
        f"- buy: {tier_counts['buy']}",
        f"- at_market: {tier_counts['at_market']}",
        f"- above_market: {tier_counts['above_market']}",
        f"- suspicious: {tier_counts['suspicious']}",
        f"- best offer: {offers[0].price:.0f} {offers[0].currency} | {offers[0].source} | {offers[0].title} | {offers[0].url}" if offers else "- best offer: n/a",
        "",
    ]

    if market_median is not None:
        reliability = "reliable" if market_median.reliable else "low confidence (fallback to current run)"
        lines.extend([
            "## Market median",
            "",
            f"- Median: {market_median.value:.0f} RUB",
            f"- Window: {market_median.window_days} days" if market_median.window_days else "- Window: current run only",
            f"- Points: {market_median.point_count}",
            f"- Source: {market_median.source} ({reliability})",
            "",
        ])
    else:
        lines.extend(["## Market median", "", "- n/a (no price data)", "", ])

    lines.extend([
        "## Config",
        "",
        f"- new_good_price: {config['new_good_price']}",
        f"- new_urgent_buy: {config['new_urgent_buy']}",
        f"- used_good_price: {config['used_good_price']}",
        f"- used_urgent_buy: {config['used_urgent_buy']}",
        f"- median_window_days: {config['median_window_days']}",
        f"- suspicious_pct: {config['suspicious_pct']}",
        f"- buy_pct: {config['buy_pct']}",
        f"- at_market_pct: {config['at_market_pct']}",
        "",
        "## Source summary",
        "",
        "| Source | Classification | Raw offers | Filtered offers | Reason | Warnings |",
        "|---|---|---:|---:|---|---|",
    ])

    for stat in source_stats:
        lines.append(_format_source_summary_markdown_row(stat))

    lines.append("")

    offer_table_header = [
        "| Source | Title | Price | Condition | Availability | Tier | URL |",
        "|---|---|---:|---|---|---|---|",
    ]

    tier_labels = [("buy", "## Buy"), ("at_market", "## At market"), ("above_market", "## Above market"), ("suspicious", "## Suspicious")]
    for tier_key, heading in tier_labels:
        tier_offers = [o for o, t in tier_list if t == tier_key]
        lines.append(f"{heading} ({len(tier_offers)})")
        lines.append("")
        if tier_offers:
            lines.extend(offer_table_header)
            for o in tier_offers:
                lines.append(
                    f"| {o.source} | {o.title.replace('|', '/')} | {o.price:.0f} {o.currency} | {o.condition} | {o.availability} | {tier_key} | {o.url} |"
                )
        else:
            lines.append("(none)")
        lines.append("")

    unknown_offers = [o for o, t in tier_list if t == "unknown"]
    if unknown_offers:
        lines.append(f"## Unknown tier ({len(unknown_offers)})")
        lines.append("")
        lines.extend(offer_table_header)
        for o in unknown_offers:
            lines.append(
                f"| {o.source} | {o.title.replace('|', '/')} | {o.price:.0f} {o.currency} | {o.condition} | {o.availability} | unknown | {o.url} |"
            )
        lines.append("")

    return "\n".join(lines) + "\n"


def save_reports(
    offers: list[ProductOffer],
    source_stats: list[dict[str, Any]] | None = None,
    config: dict[str, int] | None = None,
    market_median: MarketMedian | None = None,
) -> None:
    if source_stats is None:
        source_stats = []
    if config is None:
        config = load_config()

    Path("results.json").write_text(
        json.dumps([asdict(x) for x in offers], ensure_ascii=False, indent=2), encoding="utf-8"
    )

    with open("results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(offers[0]).keys()) if offers else [
            "source", "title", "price", "currency", "url", "condition", "seller", "availability", "checked_at", "confidence", "raw_text"
        ])
        w.writeheader()
        for x in offers:
            w.writerow(asdict(x))

    Path("results.md").write_text(render_results_markdown(offers, source_stats, config, market_median), encoding="utf-8")

    urgent = [o for o in offers if classify_signal(o) == "urgent_buy"]
    Path("urgent_deals.md").write_text(render_markdown(urgent, config), encoding="utf-8")

    prompt = (
        "Проанализируй список предложений RTX 5070 Ti, выдели аномально дешевые, "
        "проверь возможные риски продавца и предложи стратегию покупки."
    )
    Path("latest_ai_prompt.md").write_text(prompt + "\n", encoding="utf-8")

    try:
        append_price_history(offers, config=config)
    except Exception as exc:
        logging.getLogger("price_history").exception("failed to append price history: %s", exc)


def _telegram_signal_offers(
    offers: list[ProductOffer],
    market_median: MarketMedian | None,
    config: dict[str, int] | None = None,
) -> list[ProductOffer]:
    if config is None:
        config = load_config()
    buy = [o for o in offers if get_market_tier(o, market_median, config) == "buy"]
    buy.sort(key=lambda o: o.price)
    return buy


def _append_source_summary(lines: list[str], source_stats: list[dict[str, Any]], heading: str = "Source summary:") -> None:
    lines.append(heading)
    if source_stats:
        for stat in source_stats:
            lines.append(_format_source_summary_text(stat))
    else:
        lines.append("n/a")


def build_telegram_signal_text(
    offers: list[ProductOffer],
    source_stats: list[dict[str, Any]] | None = None,
    config: dict[str, int] | None = None,
    market_median: MarketMedian | None = None,
) -> str | None:
    if source_stats is None:
        source_stats = []
    if config is None:
        config = load_config()

    buy_offers = _telegram_signal_offers(offers, market_median, config)
    suspicious_offers = sorted(
        [o for o in offers if get_market_tier(o, market_median, config) == "suspicious"],
        key=lambda o: o.price,
    )

    if not buy_offers and not suspicious_offers:
        return None

    median_str = f"{market_median.value:.0f} RUB" if market_median else "n/a"
    lines = ["⚡ RTX 5070 Ti мониторинг", "", f"Медиана рынка: {median_str}", ""]

    if buy_offers:
        lines.append(f"Сигналы к покупке (≤{config['buy_pct']}% медианы):")
        for idx, offer in enumerate(buy_offers[:10], start=1):
            lines.extend([
                f"{idx}. buy — {offer.price:.0f} RUB — {offer.source}",
                offer.title,
                offer.url,
                "",
            ])

    if suspicious_offers:
        lines.append("⚠️ Очень дёшево — проверить, возможен скам:")
        for idx, offer in enumerate(suspicious_offers[:5], start=1):
            lines.extend([
                f"{idx}. suspicious — {offer.price:.0f} RUB — {offer.source}",
                offer.title,
                offer.url,
                "",
            ])

    _append_source_summary(lines, source_stats)
    lines.append("")
    lines.append(f"Всего buy-сигналов: {len(buy_offers)}")
    return "\n".join(lines)[:4000]


def build_telegram_daily_report_text(
    offers: list[ProductOffer],
    source_stats: list[dict[str, Any]] | None = None,
    config: dict[str, int] | None = None,
    market_median: MarketMedian | None = None,
) -> str:
    if source_stats is None:
        source_stats = []
    if config is None:
        config = load_config()

    buy_offers = _telegram_signal_offers(offers, market_median, config)
    suspicious_offers = sorted(
        [o for o in offers if get_market_tier(o, market_median, config) == "suspicious"],
        key=lambda o: o.price,
    )
    at_market = [o for o in offers if get_market_tier(o, market_median, config) == "at_market"]
    above_market = [o for o in offers if get_market_tier(o, market_median, config) == "above_market"]

    median_str = f"{market_median.value:.0f} RUB" if market_median else "n/a"
    lines = [
        "📊 RTX 5070 Ti daily report",
        "",
        f"Медиана рынка: {median_str}",
        f"- buy (≤{config['buy_pct']}%): {len(buy_offers)}",
        f"- at_market (≤{config['at_market_pct']}%): {len(at_market)}",
        f"- above_market: {len(above_market)}",
        f"- suspicious (<{config['suspicious_pct']}%): {len(suspicious_offers)}",
        "",
    ]

    if buy_offers:
        lines.append("Лучшие buy-офферы:")
        for idx, offer in enumerate(buy_offers[:5], start=1):
            lines.extend([
                f"{idx}. {offer.price:.0f} RUB — {offer.source}",
                offer.title,
                offer.url,
                "",
            ])
    else:
        lines.extend(["Buy-сигналов нет", ""])

    if suspicious_offers:
        lines.append("⚠️ Suspicious — проверить, возможен скам:")
        for offer in suspicious_offers[:3]:
            lines.extend([
                f"{offer.price:.0f} RUB — {offer.source}",
                offer.title,
                offer.url,
                "",
            ])

    if offers:
        best = min(offers, key=lambda o: o.price)
        best_tier = get_market_tier(best, market_median, config)
        lines.extend([
            "Лучшая цена:",
            f"{best.price:.0f} {best.currency} [{best_tier}] — {best.source}",
            best.title,
            best.url,
            "",
        ])
    else:
        lines.extend(["Лучшая цена: n/a", ""])

    _append_source_summary(lines, source_stats, heading="Source health:")
    lines.append("")
    lines.append(f"Всего офферов: {len(offers)}")
    return "\n".join(lines)[:4000]


def notify_telegram(
    offers: list[ProductOffer],
    source_stats: list[dict[str, Any]] | None = None,
    daily_report: bool = False,
    config: dict[str, int] | None = None,
    market_median: MarketMedian | None = None,
) -> None:
    if source_stats is None:
        source_stats = []
    if config is None:
        config = load_config()

    token = os.getenv("AGENT_NOTIFY_TELEGRAM_BOT_TOKEN") or os.getenv("TG_BOT_TOKEN")
    chat_id = os.getenv("AGENT_NOTIFY_TELEGRAM_CHAT_ID") or os.getenv("TG_CHAT_ID")
    if not token or not chat_id:
        logging.getLogger("telegram").warning(
            "Telegram skipped: AGENT_NOTIFY_TELEGRAM_BOT_TOKEN / AGENT_NOTIFY_TELEGRAM_CHAT_ID not set"
        )
        return

    try:
        import requests

        if daily_report:
            text = build_telegram_daily_report_text(offers, source_stats, config, market_median)
        else:
            text = build_telegram_signal_text(offers, source_stats, config, market_median)
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


def run_source_with_status(name: str, fn) -> tuple[dict[str, Any], str]:
    logger = logging.getLogger(name)
    try:
        result = fn()
        if isinstance(result, dict):
            return result, ""
        return {"offers": result}, ""
    except Exception as exc:
        logger.exception("source failed: %s", exc)
        return {"offers": [], "blocked": False, "block_reason": None, "warnings": [], "errors": 1}, str(exc)


BROWSER_FALLBACK_NO_OFFERS_WARNING = "Browser fallback produced no offers."


def apply_browser_fallback_if_blocked(
    name: str,
    module: Any,
    status: dict[str, Any],
    error: str,
    browser_already_enabled: bool,
) -> tuple[dict[str, Any], str]:
    if browser_already_enabled or not status.get("blocked"):
        return status, error

    fallback_status, fallback_error = run_source_with_status(
        name,
        lambda m=module: m.parse_offers_with_status(browser_mode=True),
    )
    if fallback_status.get("offers"):
        return fallback_status, fallback_error

    warnings = list(status.get("warnings") or [])
    warnings.append(BROWSER_FALLBACK_NO_OFFERS_WARNING)
    warnings.extend(fallback_status.get("warnings") or [])
    if fallback_error:
        warnings.append(f"Browser fallback failed: {fallback_error}")

    merged_status = dict(status)
    merged_status["warnings"] = warnings
    return merged_status, error


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", action="store_true", help="Use Playwright browser mode for DNS and Ситилинк")
    parser.add_argument("--daily-report", action="store_true", help="Send Telegram daily report even without buy signals")
    args = parser.parse_args()

    configure_logging()
    config = load_config()
    collected: list[ProductOffer] = []
    source_stats: list[dict[str, Any]] = []

    for name, module in ENABLED_SOURCES:
        status: dict[str, Any] = {}
        if name in STATUS_AWARE_SOURCE_NAMES and hasattr(module, "parse_offers_with_status"):
            status, error = run_source_with_status(name, lambda m=module: m.parse_offers_with_status(browser_mode=args.browser))
            status, error = apply_browser_fallback_if_blocked(name, module, status, error, args.browser)
            source_offers = list(status.get("offers", []))
        elif name in STATUS_AWARE_SOURCE_NAMES:
            source_offers, error = run_source(name, lambda m=module: m.parse_offers(browser_mode=args.browser))
        else:
            source_offers, error = run_source(name, module)

        collected.extend(source_offers)

        filtered_count = len(filter_offers(source_offers, config))
        source_stats.append(
            {
                "source": name,
                "raw_count": len(source_offers),
                "filtered_count": filtered_count,
                "error": error,
                "blocked": bool(status.get("blocked", False)),
                "block_reason": status.get("block_reason"),
                "warnings": status.get("warnings", []),
            }
        )

    filtered = deduplicate_offers(filter_offers(collected, config))
    market_median = compute_market_median(
        [o.price for o in filtered],
        window_days=config["median_window_days"],
        min_count=config["median_min_count"],
    )
    save_reports(filtered, source_stats, config, market_median)
    notify_telegram(filtered, source_stats, daily_report=args.daily_report, config=config, market_median=market_median)

    print("Source summary:")
    for stat in source_stats:
        print(_format_source_summary_text(stat))

    print(f"Total offers after filter: {len(filtered)}")


if __name__ == "__main__":
    main()
