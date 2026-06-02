from urllib.error import URLError

from parsers import browser


def test_check_playwright_installed_returns_bool():
    assert isinstance(browser.check_playwright_installed(), bool)


def test_fetch_html_safe_returns_empty_on_import_error(monkeypatch):
    def raise_import_error(*args, **kwargs):
        raise ImportError("missing playwright")

    monkeypatch.setattr(browser, "fetch_html", raise_import_error)
    assert browser.fetch_html_safe("https://example.com") == ""


def test_fetch_html_safe_returns_empty_on_timeout(monkeypatch):
    def raise_timeout(*args, **kwargs):
        raise URLError("timeout")

    monkeypatch.setattr(browser, "fetch_html", raise_timeout)
    assert browser.fetch_html_safe("https://example.com") == ""
