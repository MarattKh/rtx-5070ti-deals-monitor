from parsers import eldorado


FIXTURE_HTML = """
<html>
  <body>
    <div class="product-card">
      <a href="/cat/detail/palit-geforce-rtx-5070-ti-gamingpro/">
        <span class="product-card__title">Palit GeForce RTX 5070 Ti GamingPro 16GB</span>
      </a>
      <span class="product-card__price">101 990 RUB</span>
    </div>
    <div class="product-card">
      <a href="/cat/detail/msi-geforce-rtx-5070-ventus/">
        <span class="product-card__title">MSI GeForce RTX 5070 Ventus 12GB</span>
      </a>
      <span class="product-card__price">79 990 RUB</span>
    </div>
    <div class="product-card">
      <a href="/cat/detail/waterblock-rtx-5070-ti/">
        <span class="product-card__title">Waterblock for GeForce RTX 5070 Ti</span>
      </a>
      <span class="product-card__price">12 990 RUB</span>
    </div>
  </body>
</html>
"""


def test_parse_browser_html_extracts_rtx_5070_ti_offer():
    offers = eldorado.parse_browser_html(FIXTURE_HTML)

    assert len(offers) == 1
    assert offers[0].source == "Eldorado"
    assert offers[0].title == "Palit GeForce RTX 5070 Ti GamingPro 16GB"
    assert offers[0].price == 101990
    assert offers[0].url == "https://www.eldorado.ru/cat/detail/palit-geforce-rtx-5070-ti-gamingpro/"


def test_parse_browser_html_rejects_non_rtx_and_accessory():
    offers = eldorado.parse_browser_html(FIXTURE_HTML)

    titles = [offer.title for offer in offers]
    assert "MSI GeForce RTX 5070 Ventus 12GB" not in titles
    assert "Waterblock for GeForce RTX 5070 Ti" not in titles
