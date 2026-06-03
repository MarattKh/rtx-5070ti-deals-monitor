from __future__ import annotations

from datetime import datetime, timezone

from models import ProductOffer
from monitor_5070_ti_v_2 import filter_offers
from parsers.citilink import BASE_URL, parse_cards


FIXTURE_HTML = """
<div class="app-catalog-1p7hp34-Flex--StyledFlex-Name--StyledName ezwjdcp0">
  <a href="/product/videokarta-gigabyte-pci-e-gv-n507tgaming-oc-16gd-1-0-nv-rtx5070ti-16gb-2083401/"
     data-meta-name="Snippet__title"
     title="Видеокарта Gigabyte NVIDIA  GeForce RTX 5070TI GV-N507TGAMING OC-16GD 1.0 16ГБ Gaming, GDDR7, OC,  Ret"
     class="app-catalog-n3i2jz-Anchor--Anchor-Anchor--StyledAnchor ejir1360">
    Видеокарта Gigabyte NVIDIA  GeForce RTX 5070TI GV-N507TGAMING OC-16GD 1.0
  </a>
</div>
<div class="app-catalog-1gm1fba-Wrap--StyledWrap e1rrbubb0">
  <span data-meta-name="Snippet__price">
    <span data-meta-price="103000">103 000</span>
  </span>
</div>
<div class="app-catalog-1p7hp34-Flex--StyledFlex-Name--StyledName ezwjdcp0">
  <a href="/product/videokarta-gigabyte-pci-e-5-0-gv-n507twf3ocv2-16gd-nv-rtx5070ti-16gb-2-2139202/"
     data-meta-name="Snippet__title"
     title="Видеокарта Gigabyte NVIDIA  GeForce RTX 5070TI GV-N507TWF3OCV2-16GD 16ГБ Windforce, GDDR7, OC,  Ret"
     class="app-catalog-n3i2jz-Anchor--Anchor-Anchor--StyledAnchor ejir1360">
    Видеокарта Gigabyte NVIDIA  GeForce RTX 5070TI GV-N507TWF3OCV2-16GD
  </a>
</div>
<div class="app-catalog-1gm1fba-Wrap--StyledWrap e1rrbubb0">
  <span data-meta-name="Snippet__price">
    <span data-meta-price="88110">88 110</span>
  </span>
</div>
"""


NON_TI_HTML = """
<div class="app-catalog-1p7hp34-Flex--StyledFlex-Name--StyledName ezwjdcp0">
  <a href="/product/videokarta-msi-nvidia-geforce-rtx-5070-12gb/"
     data-meta-name="Snippet__title"
     title="Видеокарта MSI NVIDIA GeForce RTX 5070 12ГБ"
     class="app-catalog-n3i2jz-Anchor--Anchor-Anchor--StyledAnchor ejir1360">
    Видеокарта MSI NVIDIA GeForce RTX 5070 12ГБ
  </a>
</div>
<div class="app-catalog-1gm1fba-Wrap--StyledWrap e1rrbubb0">
  <span data-meta-name="Snippet__price">
    <span data-meta-price="78000">78 000</span>
  </span>
</div>
"""


def _offer_from_card(card: dict) -> ProductOffer:
    now = datetime.now(timezone.utc).isoformat()
    return ProductOffer(
        source="Ситилинк",
        title=card["title"],
        price=card["price"],
        currency="RUB",
        url=f"{BASE_URL}{card['url']}",
        condition="new",
        seller="Ситилинк",
        availability=card["availability"],
        checked_at=now,
        confidence=0.85,
        raw_text=card["title"],
    )


def test_parse_cards_extracts_rtx_5070_ti_offer():
    cards = parse_cards(FIXTURE_HTML)

    assert len(cards) == 2
    assert cards[0]["title"] == (
        "Видеокарта Gigabyte NVIDIA GeForce RTX 5070TI "
        "GV-N507TGAMING OC-16GD 1.0 16ГБ Gaming, GDDR7, OC, Ret"
    )
    assert cards[0]["price"] == 103000
    assert cards[0]["url"].startswith("/product/")
    assert cards[0]["url"].endswith("/")

    filtered = filter_offers([_offer_from_card(card) for card in cards])
    assert len(filtered) == 2
    assert all("5070" in offer.title and "TI" in offer.title.upper() for offer in filtered)
    assert all("/search" not in offer.url and "?text=" not in offer.url for offer in filtered)


def test_parse_cards_rejects_non_ti_card():
    cards = parse_cards(NON_TI_HTML)
    offers = [_offer_from_card(card) for card in cards]

    assert len(cards) == 1
    assert cards[0]["price"] == 78000
    assert filter_offers(offers) == []


def test_parse_cards_returns_empty_for_antibot_page():
    html = """
    <html>
      <title>429 Too Many Requests</title>
      <body>Security check. Access denied.</body>
    </html>
    """

    assert parse_cards(html) == []
