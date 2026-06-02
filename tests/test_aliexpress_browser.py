from parsers import aliexpress


APP_SHELL_HTML = """
<html>
  <head><title>rtx 5070 ti on AliExpress</title></head>
  <body>
    <script>window.__INITIAL_STATE__ = {"login_login_titleLogin":"login","verify":"session"}</script>
    <div class="SnowSearchProductFeed"></div>
  </body>
</html>
"""


def test_parse_browser_html_returns_empty_for_app_shell_without_cards():
    assert aliexpress.parse_browser_html(APP_SHELL_HTML) == []