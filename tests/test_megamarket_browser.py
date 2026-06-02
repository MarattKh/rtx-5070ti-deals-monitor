from parsers import megamarket


FIXTURE_HTML = """
<html>
  <body>
    <article class="catalog-item">
      <a href="/catalog/details/msi-geforce-rtx-5070-ti-gaming-trio-100/">
        <span class="catalog-item-title">MSI GeForce RTX 5070 Ti Gaming Trio 16GB</span>
      </a>
      <span class="catalog-item-price">104 500 RUB</span>
    </article>
    <article class="catalog-item">
      <a href="/catalog/details/msi-geforce-rtx-5070-gaming-trio-200/">
        <span class="catalog-item-title">MSI GeForce RTX 5070 Gaming Trio 12GB</span>
      </a>
      <span class="catalog-item-price">82 500 RUB</span>
    </article>
    <article class="catalog-item">
      <a href="/catalog/details/waterblock-for-rtx-5070-ti-300/">
        <span class="catalog-item-title">Waterblock for RTX 5070 Ti</span>
      </a>
      <span class="catalog-item-price">2 900 RUB</span>
    </article>
  </body>
</html>
"""


def test_parse_browser_html_extracts_rtx_5070_ti_offer():
    offers = megamarket.parse_browser_html(FIXTURE_HTML)

    assert len(offers) == 1
    assert offers[0].source == "Megamarket"
    assert offers[0].title == "MSI GeForce RTX 5070 Ti Gaming Trio 16GB"
    assert offers[0].price == 104500
    assert offers[0].url == "https://megamarket.ru/catalog/details/msi-geforce-rtx-5070-ti-gaming-trio-100/"


def test_parse_browser_html_rejects_non_rtx_and_accessory():
    offers = megamarket.parse_browser_html(FIXTURE_HTML)

    titles = [offer.title for offer in offers]
    assert "MSI GeForce RTX 5070 Gaming Trio 12GB" not in titles
    assert "Waterblock for RTX 5070 Ti" not in titles

