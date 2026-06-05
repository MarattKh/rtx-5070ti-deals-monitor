from __future__ import annotations

import monitor_5070_ti_v_2 as mon
from parsers import kns
from parsers.kns import detect_block_reason, parse_cards


def _make_product(name: str, url: str, price: int) -> str:
    return (
        f'<div itemscope="itemscope" itemtype="http://schema.org/Product">\n'
        f'  <span itemprop="name">{name}</span>\n'
        f'  <div itemprop="offers" itemscope="itemscope" itemtype="http://schema.org/Offer">\n'
        f'    <meta itemprop="url" content="{url}" />\n'
        f'    <meta itemprop="priceCurrency" content="RUB" />\n'
        f'    <meta itemprop="price" content="{price}" />\n'
        f'  </div>\n'
        f'</div>\n'
    )


FIXTURE_HTML = (
    _make_product(
        "Видеокарта MSI nVidia GeForce RTX 5070 Ti 16G Shadow 3X OC",
        "/product/videokarta-msi-nvidia-geforce-rtx-5070-ti-shadow/",
        92098,
    )
    + _make_product(
        "Видеокарта Palit nVidia GeForce RTX 5070 Ti GamingPro-S 16Gb",
        "/product/videokarta-palit-nvidia-geforce-rtx-5070-ti-gamingpro-s/",
        89556,
    )
    + _make_product(
        "Видеокарта MSI nVidia GeForce RTX 5070 12G Gaming Trio OC",
        "/product/videokarta-msi-nvidia-geforce-rtx-5070-gaming-trio/",
        78000,
    )
    + _make_product(
        "Вентилятор охлаждения RTX 5070 Ti (аксессуар)",
        "/product/ventilator-rtx-5070-ti/",
        4990,
    )
)

BLOCKED_HTML = "<html><body><title>429 Too Many Requests</title></body></html>"


def test_parse_cards_extracts_correct_data():
    cards = parse_cards(FIXTURE_HTML)

    assert len(cards) == 4
    assert cards[0]["title"] == "Видеокарта MSI nVidia GeForce RTX 5070 Ti 16G Shadow 3X OC"
    assert cards[0]["price"] == 92098.0
    assert cards[0]["url"] == "/product/videokarta-msi-nvidia-geforce-rtx-5070-ti-shadow/"


def test_parse_cards_returns_empty_for_no_products():
    assert parse_cards("<html></html>") == []


def test_parse_cards_deduplicates_same_url():
    dupe = _make_product("RTX 5070 Ti Card", "/product/dupe/", 90000)
    html = dupe + dupe
    cards = parse_cards(html)
    assert len(cards) == 1


def test_build_offers_source_and_url():
    offers = kns._build_offers(FIXTURE_HTML)

    assert all(o.source == "KNS" for o in offers)
    assert all(o.url.startswith("https://www.kns.ru/") for o in offers)
    assert all(o.currency == "RUB" for o in offers)


def test_filter_passes_5070_ti_and_rejects_others(monkeypatch):
    monkeypatch.setattr(kns, "_download", lambda _: FIXTURE_HTML)

    result = kns.parse_offers_with_status()
    offers = result["offers"]

    from monitor_5070_ti_v_2 import filter_offers
    filtered = filter_offers(offers)

    titles = [o.title for o in filtered]
    assert any("5070 Ti" in t for t in titles)
    assert not any("вентилятор" in t.lower() for t in titles)
    assert not any("5070" in t and "Ti" not in t and "TI" not in t.upper() for t in titles)


def test_detect_block_reason_429():
    assert detect_block_reason(BLOCKED_HTML) == "429 too many requests"


def test_detect_block_reason_none_for_normal_page():
    assert detect_block_reason(FIXTURE_HTML) is None


def test_parse_offers_with_status_blocked_on_http_error(monkeypatch):
    from urllib.error import HTTPError

    def raise_403(_):
        raise HTTPError("url", 403, "Forbidden", hdrs=None, fp=None)

    monkeypatch.setattr(kns, "_download", raise_403)

    result = kns.parse_offers_with_status()

    assert result["blocked"] is True
    assert result["block_reason"] == "403 forbidden"
    assert result["offers"] == []
    assert result["errors"] == 1


def test_parse_offers_with_status_returns_offers(monkeypatch):
    monkeypatch.setattr(kns, "_download", lambda _: FIXTURE_HTML)

    result = kns.parse_offers_with_status()

    assert result["blocked"] is False
    assert result["errors"] == 0
    assert len(result["offers"]) > 0


def test_kns_in_enabled_sources():
    assert "KNS" in [name for name, _ in mon.ENABLED_SOURCES]


def test_kns_module_in_enabled_sources():
    assert dict(mon.ENABLED_SOURCES)["KNS"] is kns
