# Task: Add Playwright check and safe browser fetch helper
## Context
`parsers/browser.py` already has `fetch_html()` using Playwright. `parsers/common.py` already calls
it as a fallback via `extract_product_offers`. However if Playwright or Chromium is not installed,
`fetch_html()` raises URLError which may propagate unexpectedly. Future browser-based parsers need
a checked entry point and a guaranteed-safe wrapper.
Note: there is a local branch `agent/stage-2c-generic-browser-scraper` that massively deleted project
files — do NOT merge or cherry-pick from it.
## Goal
Add two helpers to `parsers/browser.py` and tests for them. Do not change existing `fetch_html()`.
## Steps
1. Add `check_playwright_installed() -> bool` to `parsers/browser.py`. It should try importing
   `playwright.sync_api` and return True/False without raising.
2. Add `fetch_html_safe(url: str, **kwargs) -> str` that calls `fetch_html(url, **kwargs)` and catches
   ALL exceptions (URLError, PlaywrightTimeoutError, OSError, ImportError, Exception). On any
   exception: log a warning with source url and short error string, return `""`.
3. Add `install_playwright_if_missing() -> bool` that:
   - returns True immediately if `check_playwright_installed()` is True
   - otherwise runs `python -m playwright install chromium` via subprocess, captures output,
     returns True on success, False on failure (with logged warning).
## Tests
Create `tests/test_browser_helper.py`:
- `test_check_playwright_installed_returns_bool` — returns bool (not raises).
- `test_fetch_html_safe_returns_empty_on_import_error` — monkeypatch `parsers.browser.fetch_html`
  to raise ImportError; assert `fetch_html_safe("https://example.com")` returns `""`.
- `test_fetch_html_safe_returns_empty_on_timeout` — monkeypatch to raise URLError("timeout");
  assert returns `""`.
## Constraints
- Touch only `parsers/browser.py` and `tests/test_browser_helper.py`. Nothing else.
- Do NOT install Playwright/Chromium as a side-effect of importing the module.
## Validation
`python -m pytest --tb=short -q`
## PR
- Title: `Add Playwright check and safe browser fetch helper`
- Body: describe the three new helpers and the guaranteed-safe wrapper semantics.
