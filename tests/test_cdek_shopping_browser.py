from parsers import cdek_shopping


FIXTURE_HTML = """
<html>
  <body>
    <article class="product-card flex">
      <a href="/p/123/gigabyte-geforce-rtx-5070-ti-aero-oc-16gb-white" class="text-inherit absolute"></a>
      <a href="/p/123/gigabyte-geforce-rtx-5070-ti-aero-oc-16gb-white" class="text-inherit">
        <h3 class="text-sm font-medium" title="Gigabyte GeForce RTX 5070 Ti AERO OC 16GB White">
          Gigabyte GeForce RTX 5070 Ti AERO OC 16GB White
        </h3>
      </a>
      <div class="product-card-price"><p>118 601 RUB</p></div>
    </article>
    <article class="product-card flex">
      <a href="/p/456/gigabyte-geforce-rtx-5070-windforce-16g">
        <h3 class="text-sm font-medium" title="Gigabyte GeForce RTX 5070 WINDFORCE 16G">
          Gigabyte GeForce RTX 5070 WINDFORCE 16G
        </h3>
      </a>
      <div class="product-card-price"><p>76 990 RUB</p></div>
    </article>
    <article class="product-card flex">
      <a href="/p/789/waterblock-rtx-5070-ti">
        <h3 class="text-sm font-medium" title="Waterblock for GeForce RTX 5070 Ti">
          Waterblock for GeForce RTX 5070 Ti
        </h3>
      </a>
      <div class="product-card-price"><p>12 990 RUB</p></div>
    </article>
  </body>
</html>
"""


def test_parse_browser_html_extracts_rtx_5070_ti_offer():
    offers = cdek_shopping.parse_browser_html(FIXTURE_HTML)

    assert len(offers) == 1
    assert offers[0].source == "Cdek Shopping"
    assert offers[0].title == "Gigabyte GeForce RTX 5070 Ti AERO OC 16GB White"
    assert offers[0].price == 118601
    assert offers[0].url == "https://cdek.shopping/p/123/gigabyte-geforce-rtx-5070-ti-aero-oc-16gb-white"


def test_parse_browser_html_rejects_non_rtx_and_accessory():
    offers = cdek_shopping.parse_browser_html(FIXTURE_HTML)

    titles = [offer.title for offer in offers]
    assert "Gigabyte GeForce RTX 5070 WINDFORCE 16G" not in titles
    assert "Waterblock for GeForce RTX 5070 Ti" not in titles