from __future__ import annotations

import monitor_5070_ti_v_2 as mon
from parsers import positronica
from parsers.positronica import detect_block_reason, parse_cards


def _make_item(title: str, url: str, price_str: str | None) -> str:
    """Build a minimal catalog__item block as seen on positronica.ru."""
    price_span = (
        f'\n        <span class="product__price product__price_current">{price_str}</span>'
        if price_str
        else ""
    )
    return (
        f'<div class="catalog__item" data-entity="item" data-id="1234567">\n'
        f'  <a class="swiper-container product__link-slider" href="{url}" title="{title}">img</a>\n'
        f'  <div class="product__price-block">{price_span}\n'
        f'  </div>\n'
        f'</div>\n'
    )


# Two in-stock 5070 Ti cards, one out-of-stock 5070 Ti, one 5060 Ti, one accessory
FIXTURE_HTML = (
    "<!-- items-container -->\n"
    + _make_item(
        "Видеокарта MSI RTX 5070 TI 16G SHADOW 3X 16ГБ, RET",
        "/product/videokarta-msi-rtx-5070-ti-shadow-3x-2121297/",
        "92\xa0490\xa0&#8381;",
    )
    + _make_item(
        "Видеокарта Gigabyte GV-N507TWF3OC-16GD 1.0 16ГБ, RET (gv-n507twf3oc-16gd)",
        "/product/videokarta-gigabyte-gv-n507twf3oc-16gd-2083406/",
        "110\xa0490\xa0&#8381;",
    )
    + _make_item(
        "Видеокарта Asus PROART-RTX5070TI-O16G 16ГБ, RET",
        "/product/videokarta-asus-proart-rtx5070ti-o16g-2135258/",
        None,  # out of stock — no price
    )
    + _make_item(
        "Видеокарта Asus DUAL-RTX5060TI-O16G-EVO 16ГБ, BULK",
        "/product/videokarta-asus-dual-rtx5060ti-o16g-evo-2162892/",
        "69\xa0790\xa0&#8381;",
    )
    + _make_item(
        "Вентилятор охлаждения для RTX 5070 Ti (аксессуар)",
        "/product/ventilyator-dlya-rtx5070ti-9999/",
        "4\xa0990\xa0&#8381;",
    )
    + "<!-- items-container -->\n"
)

BLOCKED_HTML = "<html><body><title>429 Too Many Requests</title></body></html>"


def test_parse_cards_extracts_in_stock_items():
    cards = parse_cards(FIXTURE_HTML)

    # Only items WITH a price span should appear (out-of-stock skipped)
    assert len(cards) == 4
    assert cards[0]["title"] == "Видеокарта MSI RTX 5070 TI 16G SHADOW 3X 16ГБ, RET"
    assert cards[0]["price"] == 92490.0
    assert cards[0]["url"] == "/product/videokarta-msi-rtx-5070-ti-shadow-3x-2121297/"


def test_parse_cards_returns_empty_for_no_products():
    assert parse_cards("<html></html>") == []


def test_parse_cards_skips_out_of_stock():
    """Items without a price span (out-of-stock) must not appear."""
    cards = parse_cards(FIXTURE_HTML)
    urls = [c["url"] for c in cards]
    assert "/product/videokarta-asus-proart-rtx5070ti-o16g-2135258/" not in urls


def test_parse_cards_deduplicates_same_url():
    dupe_block = _make_item(
        "Видеокарта MSI RTX 5070 TI Dupe",
        "/product/videokarta-dupe-1/",
        "90\xa0000\xa0&#8381;",
    )
    html = "<!-- items-container -->\n" + dupe_block + dupe_block + "<!-- items-container -->\n"
    cards = parse_cards(html)
    assert len(cards) == 1


def test_build_offers_source_url_currency():
    offers = positronica._build_offers(FIXTURE_HTML)

    assert all(o.source == "Позитроника" for o in offers)
    assert all(o.url.startswith("https://www.positronica.ru/") for o in offers)
    assert all(o.currency == "RUB" for o in offers)


def test_filter_passes_5070_ti_and_rejects_others(monkeypatch):
    monkeypatch.setattr(positronica, "_download", lambda _: FIXTURE_HTML)

    result = positronica.parse_offers_with_status()
    offers = result["offers"]

    from monitor_5070_ti_v_2 import filter_offers
    filtered = filter_offers(offers)

    titles = [o.title for o in filtered]
    assert any("5070 Ti" in t or "5070 TI" in t.upper() for t in titles)
    assert not any("вентилятор" in t.lower() for t in titles)
    assert not any("5060" in t for t in titles)


def test_detect_block_reason_429():
    assert detect_block_reason(BLOCKED_HTML) == "429 too many requests"


def test_detect_block_reason_none_for_normal_page():
    assert detect_block_reason(FIXTURE_HTML) is None


def test_parse_offers_with_status_returns_offers(monkeypatch):
    monkeypatch.setattr(positronica, "_download", lambda _: FIXTURE_HTML)

    result = positronica.parse_offers_with_status()

    assert result["blocked"] is False
    assert result["errors"] == 0
    assert len(result["offers"]) > 0


def test_parse_offers_with_status_blocked_on_http_error(monkeypatch):
    from urllib.error import HTTPError

    def raise_403(_):
        raise HTTPError("url", 403, "Forbidden", hdrs=None, fp=None)

    monkeypatch.setattr(positronica, "_download", raise_403)

    result = positronica.parse_offers_with_status()

    assert result["blocked"] is True
    assert result["block_reason"] == "403 forbidden"
    assert result["offers"] == []
    assert result["errors"] == 1


def test_positronica_in_enabled_sources():
    assert "Позитроника" in [name for name, _ in mon.ENABLED_SOURCES]


def test_positronica_module_in_enabled_sources():
    assert dict(mon.ENABLED_SOURCES)["Позитроника"] is positronica


# ── Part-code recognition tests ──────────────────────────────────────────────

def test_is_relevant_product_accepts_gigabyte_n507t():
    """GV-N507T… must be accepted via OEM part-code (compact contains 'n507t')."""
    assert mon.is_relevant_product(
        "Видеокарта Gigabyte GV-N507TEAGLEOC ICE-16GD 16ГБ, RET",
        "Видеокарта Gigabyte GV-N507TEAGLEOC ICE-16GD 16ГБ, RET",
    )


def test_is_relevant_product_rejects_gigabyte_n5070_non_ti():
    """GV-N5070… (no T suffix) must NOT be accepted — that's the non-Ti 5070."""
    assert not mon.is_relevant_product(
        "Видеокарта Gigabyte GV-N5070EAGLE-16GD 16ГБ",
        "Видеокарта Gigabyte GV-N5070EAGLE-16GD 16ГБ",
    )


def test_is_relevant_product_rejects_5060_ti():
    """RTX 5060 Ti cards must never pass as 5070 Ti."""
    assert not mon.is_relevant_product(
        "Видеокарта Asus DUAL-RTX5060TI-O16G-EVO 16ГБ",
        "Видеокарта Asus DUAL-RTX5060TI-O16G-EVO 16ГБ",
    )


def test_is_relevant_product_rejects_5080():
    assert not mon.is_relevant_product(
        "Видеокарта MSI RTX 5080 16G VENTUS 3X",
        "Видеокарта MSI RTX 5080 16G VENTUS 3X",
    )


def test_is_relevant_product_rejects_5090():
    assert not mon.is_relevant_product(
        "Видеокарта ASUS ROG STRIX RTX 5090 32G",
        "Видеокарта ASUS ROG STRIX RTX 5090 32G",
    )


def test_filter_passes_gigabyte_n507t_offer(monkeypatch):
    """A card with GV-N507T… in the title must survive filter_offers."""
    from monitor_5070_ti_v_2 import filter_offers
    from models import ProductOffer
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    offer = ProductOffer(
        source="Позитроника",
        title="Видеокарта Gigabyte GV-N507TWINGOC ICE-16GD 16ГБ, RET",
        price=110_490.0,
        currency="RUB",
        url="https://www.positronica.ru/product/videokarta-gigabyte-gv-n507t-16gd/",
        condition="new",
        seller="Позитроника",
        availability="in_stock",
        checked_at=now,
        confidence=0.9,
        raw_text="Видеокарта Gigabyte GV-N507TWINGOC ICE-16GD 16ГБ, RET",
    )
    filtered = filter_offers([offer])
    assert len(filtered) == 1


def test_filter_rejects_5070_non_ti_offer():
    """A non-Ti RTX 5070 offer must be rejected even if price/source are valid."""
    from monitor_5070_ti_v_2 import filter_offers
    from models import ProductOffer
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    offer = ProductOffer(
        source="Позитроника",
        title="Видеокарта Gigabyte GV-N5070EAGLE OC 12ГБ, RET",
        price=75_000.0,
        currency="RUB",
        url="https://www.positronica.ru/product/videokarta-gigabyte-gv-n5070eagle/",
        condition="new",
        seller="Позитроника",
        availability="in_stock",
        checked_at=now,
        confidence=0.9,
        raw_text="Видеокарта Gigabyte GV-N5070EAGLE OC 12ГБ, RET",
    )
    filtered = filter_offers([offer])
    assert len(filtered) == 0
