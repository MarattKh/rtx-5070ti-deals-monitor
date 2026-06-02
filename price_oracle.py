from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Sequence

MEDIAN_WINDOW_DAYS_DEFAULT = 30
MEDIAN_MIN_COUNT_DEFAULT = 5

TIER_SUSPICIOUS = "suspicious"
TIER_BUY = "buy"
TIER_AT_MARKET = "at_market"
TIER_ABOVE_MARKET = "above_market"


@dataclass
class MarketMedian:
    value: float
    source: str  # "history" or "current_run"
    window_days: int
    point_count: int
    reliable: bool  # False when fewer than min_count history points → fallback used


def _load_history_prices(
    history_path: Path,
    window_days: int,
    now: datetime,
) -> list[float]:
    cutoff = now - timedelta(days=window_days)
    prices: list[float] = []
    if not history_path.exists():
        return prices
    for line in history_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
            ts = datetime.fromisoformat(record["timestamp"])
            if ts >= cutoff:
                price = float(record["price"])
                if price > 0:
                    prices.append(price)
        except Exception:
            continue
    return prices


def compute_market_median(
    current_prices: Sequence[float],
    history_path: str | Path = "price_history.jsonl",
    window_days: int = MEDIAN_WINDOW_DAYS_DEFAULT,
    min_count: int = MEDIAN_MIN_COUNT_DEFAULT,
    now: datetime | None = None,
) -> MarketMedian | None:
    """Return sliding-window median from price_history.jsonl.

    Falls back to the current-run prices when the history window has fewer
    than *min_count* records, and marks the result as unreliable.
    Returns None when no prices are available at all.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    prices = _load_history_prices(Path(history_path), window_days, now)

    if len(prices) >= min_count:
        return MarketMedian(
            value=median(prices),
            source="history",
            window_days=window_days,
            point_count=len(prices),
            reliable=True,
        )

    valid_current = [p for p in current_prices if p > 0]
    if valid_current:
        return MarketMedian(
            value=median(valid_current),
            source="current_run",
            window_days=0,
            point_count=len(valid_current),
            reliable=False,
        )

    return None


def classify_market_tier(
    price: float,
    market_median: float,
    suspicious_pct: int = 65,
    buy_pct: int = 90,
    at_market_pct: int = 110,
) -> str:
    """Classify price relative to the market median.

    Thresholds are expressed as integer percentages of the median:
      suspicious:    price < suspicious_pct % of median
      buy:           suspicious_pct % <= price <= buy_pct %
      at_market:     buy_pct % < price <= at_market_pct %
      above_market:  price > at_market_pct %
    """
    # Multiply-first avoids float division rounding (e.g. 110_000 / 100_000 * 100 ≈ 110.0000000001)
    p100 = price * 100
    m = market_median
    if p100 < suspicious_pct * m:
        return TIER_SUSPICIOUS
    if p100 <= buy_pct * m:
        return TIER_BUY
    if p100 <= at_market_pct * m:
        return TIER_AT_MARKET
    return TIER_ABOVE_MARKET
