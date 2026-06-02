from parsers import mvideo


FIXTURE_HTML = """
<html>
  <body>
    <mvid-product-card>
      <a href="/products/gigabyte-geforce-rtx-5070-ti-windforce-16g-1234567">
        <span class="product-title">Видеокарта Gigabyte GeForce RTX 5070 Ti WINDFORCE 16G</span>
      </a>
      <span class="price__main">99 990 ₽</span>
    </mvid-product-card>
    <mvid-product-card>
      <a href="/products/gigabyte-geforce-rtx-5070-windforce-16g-7654321">
        <span class="product-title">Видеокарта Gigabyte GeForce RTX 5070 WINDFORCE 16G</span>
      </a>
      <span class="price__main">79 990 ₽</span>
    </mvid-product-card>
  </body>
</html>
"""


def test_parse_browser_html_extracts_rtx_5070_ti_offer():
    offers = mvideo.parse_browser_html(FIXTURE_HTML)

    assert len(offers) == 1
    assert offers[0].source == "М.Видео"
    assert offers[0].title == "Видеокарта Gigabyte GeForce RTX 5070 Ti WINDFORCE 16G"
    assert offers[0].price == 99990
    assert offers[0].url == "https://www.mvideo.ru/products/gigabyte-geforce-rtx-5070-ti-windforce-16g-1234567"


def test_parse_browser_html_rejects_non_rtx_5070_ti_title():
    offers = mvideo.parse_browser_html(FIXTURE_HTML)

    assert all("RTX 5070 WINDFORCE" not in offer.title for offer in offers)
