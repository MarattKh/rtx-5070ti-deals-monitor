from __future__ import annotations

import monitor_5070_ti_v_2 as mon
from parsers import nix
from parsers.nix import detect_block_reason, parse_cards


# ---------------------------------------------------------------------------
# Fixture HTML helpers
# ---------------------------------------------------------------------------

def _make_product_row(
    good_id: str,
    url_path: str,
    title_html: str,
) -> str:
    """Build a minimal listing anchor as seen on nix.ru."""
    return (
        f"<span id='good_name_1' class=\"search-result-name\">"
        f"<a class='t' href='{url_path}' title='Подробнее' >"
        f"{title_html}"
        f"</a></span>"
        f"onclick='openGoodOffers({{\"good_id\":\"{good_id}\","
        f"\"order_number\":1,\"city_id\":1721,\"shop_price\":0}})'>"
    )


# Two real 5070 Ti products (Gigabyte + Palit), one 5060 Ti, one 5080
FIXTURE_LISTING = (
    _make_product_row(
        "869674",
        "/autocatalog/gigabyte/video/16Gb-GIGABYTE-GV-N507TGAMING-OC-16GD-GeForce-RTX5070Ti_869674.html",
        "GIGABYTE Gaming GV-N507TGAMING OC-16GD 1.0 &lt; GeForce<sup>&reg;</sup> RTX 5070 Ti &gt;",
    )
    + _make_product_row(
        "871398",
        "/autocatalog/palit/16Gb-Palit-GamingPro-OC-NE7507TS19T2-GB2031A-GeForce-RTX5070Ti_871398.html",
        "Palit GamingPro OC NE7507TS19T2-GB2031A &lt; GeForce<sup>&reg;</sup> RTX 5070 Ti &gt;",
    )
    + _make_product_row(
        "111111",
        "/autocatalog/asus/GeForce-RTX5060Ti_111111.html",
        "ASUS DUAL RTX 5060 Ti 16G",
    )
    + _make_product_row(
        "222222",
        "/autocatalog/msi/GeForce-RTX5080_222222.html",
        "MSI RTX 5080 16G SUPRIM X",
    )
)

BLOCKED_HTML = "<html><body><h1>429 Too Many Requests</h1></body></html>"

# Mock goodOffers response HTML (returned inside JSON string by the real API)
MOCK_OFFERS_HTML = (
    "<td class='price-offer-basket tar'>"
    "<a class='n' title='Положить в корзину' href='#'>+216</a>"
    "</td>"
    "<td class='price-offer-basket tar'>"
    "<a class='n' title='Положить в корзину' href='#'>115 440</a>"
    "</td>"
    "<td class='price-offer-basket tar'>"
    "<a class='n' title='Положить в корзину' href='#'>113 990</a>"
    "</td>"
)

NO_PRICE_OFFERS_HTML = (
    "<td class='price-offer-basket tar'>"
    "<a class='n' title='Положить в корзину' href='#'>+216</a>"
    "</td>"
)


# ---------------------------------------------------------------------------
# parse_cards tests
# ---------------------------------------------------------------------------

def test_parse_cards_finds_5070_ti_products():
    cards = parse_cards(FIXTURE_LISTING)
    ids = {c["good_id"] for c in cards}
    assert "869674" in ids
    assert "871398" in ids


def test_parse_cards_excludes_non_5070_ti():
    """5060 Ti and 5080 must NOT be in the result."""
    cards = parse_cards(FIXTURE_LISTING)
    ids = {c["good_id"] for c in cards}
    assert "111111" not in ids  # 5060 Ti
    assert "222222" not in ids  # 5080


def test_parse_cards_returns_empty_for_no_products():
    assert parse_cards("<html></html>") == []


def test_parse_cards_deduplicates_same_good_id():
    dupe = FIXTURE_LISTING + _make_product_row(
        "869674",
        "/autocatalog/gigabyte/video/GeForce-RTX5070Ti_869674.html",
        "GIGABYTE Gaming duplicate",
    )
    cards = parse_cards(dupe)
    ids = [c["good_id"] for c in cards]
    assert ids.count("869674") == 1


def test_parse_cards_full_url_in_card():
    cards = parse_cards(FIXTURE_LISTING)
    gig = next(c for c in cards if c["good_id"] == "869674")
    assert gig["url"].startswith("/autocatalog/")
    assert "5070Ti" in gig["url"]


# ---------------------------------------------------------------------------
# _fetch_min_price tests  (mocked)
# ---------------------------------------------------------------------------

def test_fetch_min_price_returns_minimum(monkeypatch):
    import json

    def mock_fetch(url, *, method="GET", body=None):
        return json.dumps(MOCK_OFFERS_HTML).encode("utf-8")

    monkeypatch.setattr(nix, "_fetch", mock_fetch)
    price = nix._fetch_min_price("869674")
    assert price == 113990.0


def test_fetch_min_price_returns_none_when_no_store_price(monkeypatch):
    import json

    def mock_fetch(url, *, method="GET", body=None):
        return json.dumps(NO_PRICE_OFFERS_HTML).encode("utf-8")

    monkeypatch.setattr(nix, "_fetch", mock_fetch)
    price = nix._fetch_min_price("869674")
    assert price is None


def test_fetch_min_price_ignores_delivery_surcharges(monkeypatch):
    """Entries starting with '+' are delivery costs, not product prices."""
    import json

    surcharge_only = (
        "<a class='n' title='Положить в корзину' href='#'>+500</a>"
        "<a class='n' title='Положить в корзину' href='#'>+1200</a>"
    )
    monkeypatch.setattr(nix, "_fetch", lambda *a, **k: json.dumps(surcharge_only).encode())
    assert nix._fetch_min_price("123") is None


# ---------------------------------------------------------------------------
# detect_block_reason tests
# ---------------------------------------------------------------------------

def test_detect_block_reason_429():
    assert detect_block_reason(BLOCKED_HTML) == "429 too many requests"


def test_detect_block_reason_none_for_normal_page():
    assert detect_block_reason(FIXTURE_LISTING) is None


# ---------------------------------------------------------------------------
# parse_offers_with_status tests  (full integration, mocked network)
# ---------------------------------------------------------------------------

def _mock_fetch_factory(listing_html: str, price: float | None = 115440.0):
    """Return a _fetch mock that serves listing HTML and stubbed price data."""
    import json

    if price is not None:
        price_str = f"{int(price):,}".replace(",", " ")
        offers_html = f"<a class='n' title='Положить в корзину' href='#'>{price_str}</a>"
    else:
        offers_html = "<td>нет в наличии</td>"

    def mock_fetch(url, *, method="GET", body=None):
        if method == "POST":
            return json.dumps(offers_html).encode("utf-8")
        raw = listing_html.encode("windows-1251", errors="ignore")
        return raw

    return mock_fetch


def test_parse_offers_with_status_returns_offers(monkeypatch):
    monkeypatch.setattr(nix, "_fetch", _mock_fetch_factory(FIXTURE_LISTING, 115440.0))
    result = nix.parse_offers_with_status()
    assert result["blocked"] is False
    assert result["errors"] == 0
    assert len(result["offers"]) >= 1
    assert all(o.source == "НИКС" for o in result["offers"])
    assert all(o.currency == "RUB" for o in result["offers"])
    assert all(o.url.startswith("https://www.nix.ru/") for o in result["offers"])


def test_parse_offers_with_status_blocked_on_403(monkeypatch):
    from urllib.error import HTTPError

    def raise_403(url, *, method="GET", body=None):
        raise HTTPError(url, 403, "Forbidden", hdrs=None, fp=None)

    monkeypatch.setattr(nix, "_fetch", raise_403)
    result = nix.parse_offers_with_status()
    assert result["blocked"] is True
    assert result["block_reason"] == "403 forbidden"
    assert result["offers"] == []
    assert result["errors"] == 1


def test_parse_offers_with_status_empty_when_no_prices(monkeypatch):
    monkeypatch.setattr(nix, "_fetch", _mock_fetch_factory(FIXTURE_LISTING, None))
    result = nix.parse_offers_with_status()
    assert result["blocked"] is False
    assert result["errors"] == 0
    # All offers skipped because prices unavailable
    assert result["offers"] == []


# ---------------------------------------------------------------------------
# Filter integration test
# ---------------------------------------------------------------------------

def test_filter_passes_5070_ti_nix_offer(monkeypatch):
    """Offers with RTX 5070 Ti in the title must pass filter_offers."""
    from monitor_5070_ti_v_2 import filter_offers
    from models import ProductOffer
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    offer = ProductOffer(
        source="НИКС",
        title="GIGABYTE Gaming GV-N507TGAMING OC-16GD 1.0 < GeForce RTX 5070 Ti > (16 ГБ)",
        price=115440.0,
        currency="RUB",
        url="https://www.nix.ru/autocatalog/gigabyte/video/GeForce-RTX5070Ti_869674.html",
        condition="new",
        seller="НИКС",
        availability="in_stock",
        checked_at=now,
        confidence=0.9,
        raw_text="GIGABYTE Gaming GV-N507TGAMING OC-16GD 1.0 < GeForce RTX 5070 Ti > (16 ГБ)",
    )
    assert len(filter_offers([offer])) == 1


def test_filter_rejects_5080_nix_offer():
    """RTX 5080 offers must be rejected."""
    from monitor_5070_ti_v_2 import filter_offers
    from models import ProductOffer
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    offer = ProductOffer(
        source="НИКС",
        title="MSI RTX 5080 16G SUPRIM X (16 ГБ, GDDR7)",
        price=175000.0,
        currency="RUB",
        url="https://www.nix.ru/autocatalog/msi/GeForce-RTX5080_222222.html",
        condition="new",
        seller="НИКС",
        availability="in_stock",
        checked_at=now,
        confidence=0.9,
        raw_text="MSI RTX 5080 16G SUPRIM X (16 ГБ, GDDR7)",
    )
    assert len(filter_offers([offer])) == 0


# ---------------------------------------------------------------------------
# Part-code tests: Palit NE7507T (observed in rejected НИКС offers)
# ---------------------------------------------------------------------------

def test_is_rtx_5070_ti_accepts_palit_ne7507ts():
    """NE7507TS19T2 must be accepted via ne7507t part-code."""
    assert mon.is_rtx_5070_ti(
        "Palit NE7507TS19T2-GB2031A (16 ГБ, GDDR7, 256 бит, PCI Express)",
        "Palit NE7507TS19T2-GB2031A (16 ГБ, GDDR7, 256 бит, PCI Express)",
    )


def test_is_rtx_5070_ti_accepts_palit_ne7507t0():
    """NE7507T019T2 must be accepted via ne7507t part-code."""
    assert mon.is_rtx_5070_ti(
        "Palit NE7507T019T2-GB2031A (16 ГБ, GDDR7, 256 бит, PCI Express)",
        "Palit NE7507T019T2-GB2031A (16 ГБ, GDDR7, 256 бит, PCI Express)",
    )


def test_is_rtx_5070_ti_rejects_hypothetical_palit_non_ti():
    """A hypothetical Palit RTX 5070 (non-Ti) code ne75070 must NOT match."""
    assert not mon.is_rtx_5070_ti(
        "Palit NE75070019T2-XY1234 (12 ГБ, GDDR7)",
        "Palit NE75070019T2-XY1234 (12 ГБ, GDDR7)",
    )


# ---------------------------------------------------------------------------
# ENABLED_SOURCES membership tests
# ---------------------------------------------------------------------------

def test_nix_in_enabled_sources():
    assert "НИКС" in [name for name, _ in mon.ENABLED_SOURCES]


def test_nix_module_in_enabled_sources():
    assert dict(mon.ENABLED_SOURCES)["НИКС"] is nix
