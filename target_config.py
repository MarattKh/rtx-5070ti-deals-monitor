"""Single source of truth for the monitored product.

``target.json`` generalises everything that used to be hard-coded as
"RTX 5070 Ti" in the monitor logic — the search query, the human-readable
label, the price-history product id and the relevance ruleset. Only the five
filtered-source URLs (XCOM, KNS, Ф-Центр, Позитроника, НИКС) stay in code for
now (phase 2b).

The defaults below reproduce the original RTX 5070 Ti behaviour byte-for-byte,
so the monitor keeps working even if ``target.json`` is missing (e.g. tests
that ``chdir`` into a temp dir).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

# Relevance ruleset notes (kept here since JSON cannot carry comments):
#
# match_any clauses (any one match = relevant):
#   {"all_tokens": [...]}  — every token is a substring of the normalised title
#   {"compact": "..."}     — substring of the space-stripped normalised title
#   {"part_codes": [...]}  — OEM codes that unambiguously identify the product,
#                            checked against the compact form. Extend only with
#                            codes seen in real rejected offers.
#     n507t    — Gigabyte GV-N507T…  (N=NVIDIA, 507=5070, T=Ti; non-Ti = n5070)
#     ne7507t  — Palit NE7507T…      (non-Ti would be ne75070)
#
# exclude_patterns — product-specific regexes that reject look-alikes (e.g. the
# RTX 5070 *Super*). Universal, product-neutral accessory filtering (cables,
# brackets, water blocks, laptops…) stays in code, not here.
DEFAULT_TARGET: dict[str, Any] = {
    "product_id": "rtx_5070_ti",
    "label": "RTX 5070 Ti",
    "query": "rtx 5070 ti",
    "relevance": {
        "match_any": [
            {"all_tokens": ["5070", "ti"]},
            {"compact": "5070ti"},
            {"part_codes": ["n507t", "ne7507t"]},
        ],
        "exclude_patterns": ["5070\\s+super"],
    },
    # Product-specific filter tokens for the five filtered-URL sources.
    # Each value is the minimal fragment that differs per product:
    #   XCOM-SHOP / KNS — GPU slug in the catalog filter path
    #   Ф-Центр         — numeric param= value
    #   Позитроника      — Bitrix arrFilter_… key name (value is always =Y)
    #   НИКС             — token that appears in product URL paths (5070Ti)
    # Empty string → parser skips the source with "not configured" status.
    "source_filters": {
        "XCOM-SHOP": "nvidia-geforce-rtx-5070-ti",
        "KNS": "nvidia-geforce-rtx-5070-ti",
        "Ф-Центр": "46060",
        "Позитроника": "arrFilter_121681_2580419962",
        "НИКС": "5070Ti",
    },
}

TARGET_PATH = Path("target.json")


def load_target(path: str | Path = TARGET_PATH) -> dict[str, Any]:
    """Return the target definition, falling back to :data:`DEFAULT_TARGET`.

    Mirrors ``load_config``: a missing or malformed file degrades gracefully to
    the built-in defaults instead of raising.
    """
    target = json.loads(json.dumps(DEFAULT_TARGET))  # deep copy
    target_path = Path(path)

    if not target_path.exists():
        return target

    try:
        raw = json.loads(target_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            logging.getLogger("target").error("target is not a JSON object: %s", target_path)
            return target

        for key, default_value in DEFAULT_TARGET.items():
            value = raw.get(key, default_value)
            if key in ("relevance", "source_filters") and not isinstance(value, dict):
                logging.getLogger("target").error("invalid %s in %s: %r", key, target_path, value)
                value = default_value
            target[key] = value
    except Exception as exc:
        logging.getLogger("target").exception("failed to load target %s: %s", target_path, exc)
        return json.loads(json.dumps(DEFAULT_TARGET))

    return target


def get_query(path: str | Path = TARGET_PATH) -> str:
    """Search query string for building source URLs."""
    return str(load_target(path)["query"])


def get_source_filter(name: str, path: str | Path = TARGET_PATH) -> str:
    """Return the product-specific filter value for a named source.

    Returns an empty string when the source has no entry in ``source_filters``
    (meaning the source is not configured for the current target). Parsers
    treat an empty return value as a skip signal — they return a
    ``warnings=["Источник не настроен для данного товара"]`` status dict
    instead of fetching the catalog.
    """
    filters = load_target(path).get("source_filters", {})
    if not isinstance(filters, dict):
        return ""
    return str(filters.get(name, ""))
