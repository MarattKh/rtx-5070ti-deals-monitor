from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parsers import dns


def print_html_diagnostics(path: Path) -> None:
    print(f"html path: {path}")
    print(f"html exists: {path.exists()}")

    if not path.exists():
        return

    html = path.read_text(encoding="utf-8", errors="replace")
    diagnostics = dns.diagnose_html(html)

    print(f"html size: {diagnostics['html_size']}")
    print(f"contains RTX: {diagnostics['contains_rtx']}")
    print(f"contains 5070: {diagnostics['contains_5070']}")
    print(f"contains catalog-product: {diagnostics['contains_catalog_product']}")
    print(f"contains product link: {diagnostics['contains_product_link']}")
    print(f"contains qrator: {diagnostics['contains_qrator']}")
    print(f"contains captcha keywords: {diagnostics['contains_captcha']}")
    print(f"contains empty keywords: {diagnostics['contains_empty']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", action="store_true", help="Use Playwright browser mode for DNS")
    args = parser.parse_args()

    result = dns.parse_offers_with_status(browser_mode=args.browser)
    offers = result.get("offers", [])

    print(f"blocked: {result.get('blocked')}")
    print(f"block_reason: {result.get('block_reason')}")
    print(f"errors: {result.get('errors')}")
    print(f"warnings: {result.get('warnings')}")
    print(f"offers count: {len(offers)}")

    if args.browser:
        print_html_diagnostics(ROOT / "debug_html" / "dns.html")

    for idx, offer in enumerate(offers[:5], start=1):
        print(f"{idx}. {offer.price:.0f} {offer.currency} | {offer.title} | {offer.url}")


if __name__ == "__main__":
    main()