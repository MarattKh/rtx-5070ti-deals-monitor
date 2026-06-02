from parsers import wildberries


BLOCKED_HTML = """
<html>
  <head><title>Almost ready...</title></head>
  <body>
    <div id="wait_msg"><p class="wait_msg">Checking browser</p></div>
  </body>
</html>
"""


def test_parse_browser_html_returns_empty_for_antibot_challenge():
    assert wildberries.parse_browser_html(BLOCKED_HTML) == []