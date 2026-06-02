from parsers import ozon


FIXTURE_HTML = """
<html>
  <body>
    <div class="tile-root">
      <a href="/product/gigabyte-geforce-rtx-5070-ti-windforce-16g-123/">
        <span class="tile-hover-target">Gigabyte GeForce RTX 5070 Ti WINDFORCE 16G</span>
      </a>
      <span class="price">99 490 RUB</span>
    </div>
    <div class="tile-root">
      <a href="/product/gigabyte-geforce-rtx-5070-windforce-16g-456/">
        <span class="tile-hover-target">Gigabyte GeForce RTX 5070 WINDFORCE 16G</span>
      </a>
      <span class="price">76 990 RUB</span>
    </div>
    <div class="tile-root">
      <a href="/product/ventilator-rtx-5070-ti-789/">
        <span class="tile-hover-target">Вентилятор для GeForce RTX 5070 Ti</span>
      </a>
      <span class="price">4 990 RUB</span>
    </div>
  </body>
</html>
"""


def test_parse_browser_html_extracts_rtx_5070_ti_offer():
    offers = ozon.parse_browser_html(FIXTURE_HTML)

    assert len(offers) == 1
    assert offers[0].source == "Ozon"
    assert offers[0].title == "Gigabyte GeForce RTX 5070 Ti WINDFORCE 16G"
    assert offers[0].price == 99490
    assert offers[0].url == "https://www.ozon.ru/product/gigabyte-geforce-rtx-5070-ti-windforce-16g-123/"


def test_parse_browser_html_rejects_non_rtx_and_accessory():
    offers = ozon.parse_browser_html(FIXTURE_HTML)

    titles = [offer.title for offer in offers]
    assert "Gigabyte GeForce RTX 5070 WINDFORCE 16G" not in titles
    assert "Вентилятор для GeForce RTX 5070 Ti" not in titles

