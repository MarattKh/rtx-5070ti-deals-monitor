from __future__ import annotations

import html as html_lib
import json

import monitor_5070_ti_v_2 as mon
from parsers import xcom_shop
from parsers.xcom_shop import detect_block_reason, parse_cards


def _make_item(name: str, price: int, url: str) -> str:
    dl = html_lib.escape(json.dumps({"id": "1", "name": name, "price": price}, ensure_ascii=False))
    return (
        f'<div class="catalog_item catalog_item--list" data-dl-product="{dl}">\n'
        f'  <a class="catalog_item__image catalog_item__image--list" href="{url}">img</a>\n'
        f'</div>\n'
    )


FIXTURE_HTML = (
    _make_item(
        "Видеокарта PCI-E MSI GeForce RTX 5070 TI SHADOW 3X OC (RTX 5070 Ti 16G SHADOW 3X OC)",
        92413,
        "/msi_rtx_5070_ti_shadow_1202358.html",
    )
    + _make_item(
        "Видеокарта PCI-E Palit GeForce RTX 5070 Ti GamingPro",
        99113,
        "/palit_rtx_5070_ti_gamingpro_1193501.html",
    )
    + _make_item(
        "Вентилятор для GeForce RTX 5070 Ti (аксессуар)",
        4990,
        "/fan_rtx_5070_ti_accessory.html",
    )
    + _make_item(
        "Видеокарта PCI-E Palit GeForce RTX 5070 GAMINGPRO",
        77000,
        "/palit_rtx_5070_gamingpro.html",
    )
)

BLOCKED_HTML = "<html><body>429 Too Many Requests. Security check.</body></html>"


def test_parse_cards_extracts_rtx_5070_ti_items():
    cards = parse_cards(FIXTURE_HTML)

    assert len(cards) == 4
    assert cards[0]["title"] == "Видеокарта PCI-E MSI GeForce RTX 5070 TI SHADOW 3X OC (RTX 5070 Ti 16G SHADOW 3X OC)"
    assert cards[0]["price"] == 92413.0
    assert cards[0]["url"] == "/msi_rtx_5070_ti_shadow_1202358.html"


def test_parse_cards_returns_empty_for_blocked_page():
    assert parse_cards(BLOCKED_HTML) == []


def test_parse_offers_source_and_url():
    offers = xcom_shop._build_offers(FIXTURE_HTML)

    assert all(o.source == "XCOM-SHOP" for o in offers)
    assert all(o.url.startswith("https://www.xcom-shop.ru/") for o in offers)


def test_filter_passes_5070_ti_and_rejects_others(monkeypatch):
    monkeypatch.setattr(xcom_shop, "_download", lambda _: FIXTURE_HTML)

    result = xcom_shop.parse_offers_with_status()
    offers = result["offers"]

    from monitor_5070_ti_v_2 import filter_offers
    filtered = filter_offers(offers)

    titles = [o.title for o in filtered]
    assert any("5070 Ti" in t or "5070 TI" in t for t in titles)
    assert not any("аксессуар" in t.lower() for t in titles)
    assert not any(
        ("5070" in t and "Ti" not in t.upper().replace("TI", "Ti"))
        for t in titles
    )


def test_detect_block_reason_429():
    assert detect_block_reason(BLOCKED_HTML) == "429 too many requests"


def test_detect_block_reason_none_for_normal_page():
    assert detect_block_reason(FIXTURE_HTML) is None


def test_parse_offers_with_status_returns_blocked_on_http_error(monkeypatch):
    from urllib.error import HTTPError

    def raise_403(_):
        raise HTTPError("url", 403, "Forbidden", hdrs=None, fp=None)

    monkeypatch.setattr(xcom_shop, "_download", raise_403)

    result = xcom_shop.parse_offers_with_status()

    assert result["blocked"] is True
    assert result["block_reason"] == "403 forbidden"
    assert result["offers"] == []
    assert result["errors"] == 1


def test_parse_offers_with_status_returns_offers_for_valid_html(monkeypatch):
    monkeypatch.setattr(xcom_shop, "_download", lambda _: FIXTURE_HTML)

    result = xcom_shop.parse_offers_with_status()

    assert result["blocked"] is False
    assert result["errors"] == 0
    assert len(result["offers"]) > 0


def test_xcom_shop_in_enabled_sources():
    source_names = [name for name, _ in mon.ENABLED_SOURCES]
    assert "XCOM-SHOP" in source_names


def test_xcom_shop_module_in_enabled_sources():
    sources = dict(mon.ENABLED_SOURCES)
    assert sources["XCOM-SHOP"] is xcom_shop
