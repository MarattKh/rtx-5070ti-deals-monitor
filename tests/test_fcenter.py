from __future__ import annotations

import html as html_lib

import monitor_5070_ti_v_2 as mon
from parsers import fcenter
from parsers.fcenter import detect_block_reason, parse_cards


def _make_card(title: str, url: str, price_str: str) -> str:
    esc = html_lib.escape(title)
    return (
        f'<div class="pic-table-item col_12">\n'
        f'  <a class="goods-link" href="{url}" title="{esc}">{esc}</a>\n'
        f'  <div class="do-price">\n'
        f'  {price_str}<sup class="kop"><noindex>00 </noindex></sup>'
        f'  <span class="rublik">p</span>\n'
        f'  </div>\n'
        f'</div>\n'
    )


FIXTURE_HTML = (
    _make_card(
        'Видеокарта GIGABYTE "GeForce RTX 5070 Ti MASTER 16G" GV-N507TAORUS M-16GD',
        "/product/goods/163790-Videokarta_GIGABYTE_GeForce_RTX_5070_Ti_MASTER_16G",
        "132 759",
    )
    + _make_card(
        'Видеокарта MSI "GeForce RTX 5070 Ti 16G SHADOW 3X OC"',
        "/product/goods/163767-Videokarta_MSI_GeForce_RTX_5070_Ti_Shadow",
        "99 410",
    )
    + _make_card(
        'Видеокарта MSI "GeForce RTX 5070 12G GAMING TRIO OC"',
        "/product/goods/163772-Videokarta_MSI_GeForce_RTX_5070_Trio",
        "77 000",
    )
    + _make_card(
        "Вентилятор для GeForce RTX 5070 Ti",
        "/product/goods/111111-Fan_RTX5070Ti",
        "4 990",
    )
)

BLOCKED_HTML = "<html><body><title>429 Too Many Requests</title></body></html>"


def test_parse_cards_extracts_correct_data():
    cards = parse_cards(FIXTURE_HTML)

    assert len(cards) == 4
    assert cards[0]["title"] == 'Видеокарта GIGABYTE "GeForce RTX 5070 Ti MASTER 16G" GV-N507TAORUS M-16GD'
    assert cards[0]["price"] == 132759.0
    assert cards[0]["url"].startswith("/product/goods/163790")


def test_parse_cards_returns_empty_for_blocked_page():
    assert parse_cards(BLOCKED_HTML) == []


def test_build_offers_source_and_url():
    offers = fcenter._build_offers(FIXTURE_HTML)

    assert all(o.source == "Ф-Центр" for o in offers)
    assert all(o.url.startswith("https://fcenter.ru/") for o in offers)
    assert all(o.currency == "RUB" for o in offers)


def test_filter_passes_5070_ti_and_rejects_others(monkeypatch):
    monkeypatch.setattr(fcenter, "_download_fcenter", lambda _: FIXTURE_HTML)

    result = fcenter.parse_offers_with_status()
    offers = result["offers"]

    from monitor_5070_ti_v_2 import filter_offers
    filtered = filter_offers(offers)

    titles = [o.title for o in filtered]
    assert any("5070 Ti" in t or "5070 TI" in t.upper() for t in titles)
    assert not any("вентилятор" in t.lower() for t in titles)
    assert not any(
        "5070" in t and "Ti" not in t and "TI" not in t.upper()
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

    monkeypatch.setattr(fcenter, "_download_fcenter", raise_403)

    result = fcenter.parse_offers_with_status()

    assert result["blocked"] is True
    assert result["block_reason"] == "403 forbidden"
    assert result["offers"] == []
    assert result["errors"] == 1


def test_parse_offers_with_status_returns_offers_for_valid_html(monkeypatch):
    monkeypatch.setattr(fcenter, "_download_fcenter", lambda _: FIXTURE_HTML)

    result = fcenter.parse_offers_with_status()

    assert result["blocked"] is False
    assert result["errors"] == 0
    assert len(result["offers"]) > 0


def test_fcenter_in_enabled_sources():
    source_names = [name for name, _ in mon.ENABLED_SOURCES]
    assert "Ф-Центр" in source_names


def test_fcenter_module_in_enabled_sources():
    sources = dict(mon.ENABLED_SOURCES)
    assert sources["Ф-Центр"] is fcenter
