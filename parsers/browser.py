from __future__ import annotations

from pathlib import Path
from urllib.error import URLError


def fetch_html(
    url: str,
    timeout_ms: int = 30000,
    save_to: str | None = None,
    wait_selectors: list[str] | None = None,
    extra_delay_ms: int = 0,
    screenshot_to: str | None = None,
) -> str:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise URLError(
            "Playwright is not available. Run: "
            "python -m pip install -r requirements.txt && python -m playwright install chromium"
        ) from exc

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=7000)
            except PlaywrightTimeoutError:
                pass

            if wait_selectors:
                for selector in wait_selectors:
                    try:
                        page.wait_for_selector(selector, timeout=3000)
                        break
                    except PlaywrightTimeoutError:
                        continue

            if extra_delay_ms > 0:
                page.wait_for_timeout(extra_delay_ms)

            html = page.content()

            if save_to:
                target = Path(save_to)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(html, encoding="utf-8")

            if screenshot_to:
                screenshot_target = Path(screenshot_to)
                screenshot_target.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(screenshot_target), full_page=True)

            return html
        finally:
            page.close()
            context.close()
            browser.close()