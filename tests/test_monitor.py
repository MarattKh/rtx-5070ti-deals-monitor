from pathlib import Path
from urllib.error import HTTPError

import pytest

from monitor_5070_ti_v_2 import filter_offers, get_signal_label
from models import ProductOffer
from parsers.citilink import parse_cards as parse_citilink_cards
from parsers.dns import parse_cards as parse_dns_cards
from parsers.regard import parse_cards as parse_regard_cards
from parsers.yandex_market import parse_cards as parse_yandex_cards


def mk_offer(title: str, raw: str = "", price: float = 100000, url: str = "https://example.com/product/1", source: str = "DNS") -> ProductOffer:
    return ProductOffer(source, title, price, "RUB", url, "new", source, "in_stock", "2026-01-01T00:00:00+00:00", 0.9, raw)


def set_enabled_sources(monkeypatch, mon, sources):
    monkeypatch.setattr(mon, "ENABLED_SOURCES", tuple(sources))


def test_accepts_rtx_5070_ti():
    offers = filter_offers([mk_offer("NVIDIA GeForce RTX 5070 Ti")])
    assert len(offers) == 1


def test_accepts_rtx5070ti_without_spaces():
    offers = filter_offers([mk_offer("MSI RTX5070Ti Gaming")])
    assert len(offers) == 1


def test_rejects_rtx_5070_without_ti():
    offers = filter_offers([mk_offer("NVIDIA GeForce RTX 5070")])
    assert offers == []


def test_rejects_laptop():
    offers = filter_offers([mk_offer("RTX 5070 Ti laptop")])
    assert offers == []


def test_rejects_desktop_pc():
    offers = filter_offers([mk_offer("Gaming PC RTX 5070 Ti")])
    assert offers == []


def test_rejects_waterblock():
    offers = filter_offers([mk_offer("Waterblock for RTX 5070 Ti")])
    assert offers == []


# --- accessory filter: positive cases (PCI-E / FAN descriptors must pass) ---

def test_accepts_gpu_with_pcie_in_title():
    offers = filter_offers([mk_offer("Видеокарта Gigabyte PCI-E 5.0 RTX5070TI 16Gb")])
    assert len(offers) == 1


def test_accepts_gpu_with_pcie16_in_title():
    offers = filter_offers([mk_offer("Видеокарта PCIE16 RTX5070TI 16GB RTX 5070 Ti 16G OC MSI")])
    assert len(offers) == 1


def test_accepts_gpu_with_3fan_in_title():
    offers = filter_offers([mk_offer("Видеокарта MSI RTX5070Ti GAMING TRIO OC 16GB 3FAN RTL")])
    assert len(offers) == 1


def test_accepts_gpu_with_4fan_in_title():
    offers = filter_offers([mk_offer("RTX 5070 Ti OC 16GB 4FAN Edition")])
    assert len(offers) == 1


def test_accepts_gpu_with_triple_fan_in_title():
    offers = filter_offers([mk_offer("RTX 5070 Ti Triple Fan 16GB OC")])
    assert len(offers) == 1


def test_accepts_gpu_with_dual_fan_in_title():
    offers = filter_offers([mk_offer("RTX 5070 Ti Dual Fan Gaming OC")])
    assert len(offers) == 1


# --- accessory filter: negative cases (accessories must stay rejected) ---

def test_rejects_waterblock_with_model():
    offers = filter_offers([mk_offer("Водоблок для RTX 5070 Ti")])
    assert offers == []


def test_rejects_cable_riser():
    offers = filter_offers([mk_offer("Кабель PCI-E райзер для RTX 5070 Ti")])
    assert offers == []


def test_rejects_bracket():
    offers = filter_offers([mk_offer("Кронштейн крепления видеокарты RTX 5070 Ti")])
    assert offers == []


def test_rejects_standalone_fan():
    offers = filter_offers([mk_offer("Вентилятор 120мм для корпуса ПК")])
    assert offers == []


def test_rejects_thermal_paste():
    offers = filter_offers([mk_offer("Термопаста Arctic для RTX 5070 Ti")])
    assert offers == []


def test_rejects_power_adapter():
    offers = filter_offers([mk_offer("Переходник 12VHPWR для RTX 5070 Ti")])
    assert offers == []


def test_rejects_riser_cable():
    offers = filter_offers([mk_offer("Райзер PCI-E 16x для RTX 5070 Ti")])
    assert offers == []


def test_reports_are_created(tmp_path, monkeypatch):
    import monitor_5070_ti_v_2 as mon

    monkeypatch.chdir(tmp_path)
    mon.save_reports([mk_offer("RTX 5070 Ti Ventus", price=89000)], [{"source": "DNS", "raw_count": 1, "filtered_count": 1, "error": ""}])

    assert Path("results.json").exists()
    assert Path("results.csv").exists()
    assert Path("results.md").exists()
    assert Path("urgent_deals.md").exists()
    assert Path("latest_ai_prompt.md").exists()


def test_append_price_history_writes_jsonl_records(tmp_path):
    import json
    import monitor_5070_ti_v_2 as mon

    history_path = tmp_path / "price_history.jsonl"
    timestamp = "2026-05-28T00:00:00+00:00"

    mon.append_price_history(
        [mk_offer("RTX 5070 Ti Ventus", price=89000)],
        path=history_path,
        timestamp=timestamp,
    )

    lines = history_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    record = json.loads(lines[0])
    assert record == {
        "timestamp": timestamp,
        "source": "DNS",
        "title": "RTX 5070 Ti Ventus",
        "price": 89000,
        "currency": "RUB",
        "url": "https://example.com/product/1",
        "condition": "new",
        "availability": "in_stock",
        "signal": "GOOD_PRICE",
    }


def test_save_reports_appends_price_history(tmp_path, monkeypatch):
    import json
    import monitor_5070_ti_v_2 as mon

    monkeypatch.chdir(tmp_path)

    mon.save_reports([mk_offer("RTX 5070 Ti Ventus", price=89000)], [])

    lines = Path("price_history.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["title"] == "RTX 5070 Ti Ventus"


def test_save_reports_continues_when_price_history_fails(tmp_path, monkeypatch):
    import monitor_5070_ti_v_2 as mon

    monkeypatch.chdir(tmp_path)

    def fail_price_history(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(mon, "append_price_history", fail_price_history)

    mon.save_reports([mk_offer("RTX 5070 Ti Ventus", price=89000)], [])

    assert Path("results.json").exists()
    assert Path("latest_ai_prompt.md").exists()


def test_source_summary_counts_and_errors():
    import monitor_5070_ti_v_2 as mon

    ok_offer = mk_offer("RTX 5070 Ti", url="https://shop.example/product/5070ti")

    offers, err = mon.run_source(
        "DNS",
        lambda: [
            ok_offer,
            mk_offer("RTX 5070", url="https://shop.example/product/5070"),
        ],
    )
    assert err == ""
    assert len(offers) == 2
    assert len(mon.filter_offers(offers)) == 1

    offers_bad, err_bad = mon.run_source(
        "DNS",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert offers_bad == []
    assert "boom" in err_bad


def test_results_md_contains_summary_and_source_summary(tmp_path, monkeypatch):
    import monitor_5070_ti_v_2 as mon

    monkeypatch.chdir(tmp_path)
    mon.save_reports(
        [mk_offer("RTX 5070 Ti Ventus", price=89000)],
        [{"source": "DNS", "raw_count": 3, "filtered_count": 1, "error": ""}],
    )

    content = Path("results.md").read_text(encoding="utf-8")
    assert "## Summary" in content
    assert "## Source summary" in content
    assert "| Source | Classification | Raw offers | Filtered offers | Reason | Warnings |" in content
    assert "| DNS | ok | 3 | 1 | ok | none |" in content


@pytest.mark.parametrize("reason", ["401 unauthorized", "403 forbidden", "429 too many requests"])
def test_source_summary_formats_blocked_status_instead_of_empty_counts(reason):
    import monitor_5070_ti_v_2 as mon

    stat = {
        "source": "ExampleShop",
        "raw_count": 0,
        "filtered_count": 0,
        "error": "",
        "blocked": True,
        "block_reason": reason,
        "warnings": ["Manual verification required."],
    }

    assert mon._format_source_summary_text(stat) == f"ExampleShop: unavailable; raw 0; filtered 0; reason: blocked: {reason}; warnings: Manual verification required."
    assert mon._format_source_summary_markdown_row(stat) == f"| ExampleShop | unavailable | 0 | 0 | blocked: {reason} | Manual verification required. |"
    assert "raw 0 / filtered 0" not in mon._format_source_summary_text(stat)
    assert "| ExampleShop | 0 | 0 |" not in mon._format_source_summary_markdown_row(stat)


def test_source_summary_formats_successful_counts():
    import monitor_5070_ti_v_2 as mon

    stat = {"source": "ExampleShop", "raw_count": 3, "filtered_count": 1, "error": ""}

    assert mon._format_source_summary_text(stat) == "ExampleShop: ok; raw 3; filtered 1; reason: ok; warnings: none"
    assert mon._format_source_summary_markdown_row(stat) == "| ExampleShop | ok | 3 | 1 | ok | none |"


def test_source_summary_formats_no_filtered_warning_row():
    import monitor_5070_ti_v_2 as mon

    stat = {
        "source": "DNS",
        "raw_count": 0,
        "filtered_count": 0,
        "error": "",
        "blocked": False,
        "warnings": ["DNS browser HTML contains no parsed product cards."],
    }

    assert mon._format_source_summary_text(stat) == "DNS: no_filtered_offers; raw 0; filtered 0; reason: no offers after parsing; warnings: DNS browser HTML contains no parsed product cards."
    assert mon._format_source_summary_markdown_row(stat) == "| DNS | no_filtered_offers | 0 | 0 | no offers after parsing | DNS browser HTML contains no parsed product cards. |"


def test_summarize_source_stats_classifies_all_review_states():
    import monitor_5070_ti_v_2 as mon

    summaries = mon.summarize_source_stats(
        [
            {"source": "OK", "raw_count": 3, "filtered_count": 1, "error": "", "warnings": []},
            {"source": "Filtered", "raw_count": 3, "filtered_count": 0, "error": "", "warnings": ["all offers above max price"]},
            {"source": "Blocked", "raw_count": 0, "filtered_count": 0, "error": "", "blocked": True, "block_reason": "403 forbidden"},
            {"source": "Broken", "raw_count": 0, "filtered_count": 0, "error": "boom", "warnings": []},
        ]
    )

    assert summaries == [
        {"source": "OK", "classification": "ok", "raw_count": 3, "filtered_count": 1, "reason": "ok", "warnings": []},
        {
            "source": "Filtered",
            "classification": "no_filtered_offers",
            "raw_count": 3,
            "filtered_count": 0,
            "reason": "raw offers did not pass filters",
            "warnings": ["all offers above max price"],
        },
        {
            "source": "Blocked",
            "classification": "unavailable",
            "raw_count": 0,
            "filtered_count": 0,
            "reason": "blocked: 403 forbidden",
            "warnings": [],
        },
        {"source": "Broken", "classification": "error", "raw_count": 0, "filtered_count": 0, "reason": "boom", "warnings": []},
    ]


def test_results_md_source_summary_shows_blocked_dns(tmp_path, monkeypatch):
    import monitor_5070_ti_v_2 as mon

    monkeypatch.chdir(tmp_path)
    mon.save_reports(
        [],
        [
            {
                "source": "DNS",
                "raw_count": 0,
                "filtered_count": 0,
                "error": "",
                "blocked": True,
                "block_reason": "403 forbidden",
                "warnings": ["DNS access forbidden. Manual verification required."],
            }
        ],
    )

    content = Path("results.md").read_text(encoding="utf-8")
    assert "| DNS | unavailable | 0 | 0 | blocked: 403 forbidden | DNS access forbidden. Manual verification required. |" in content
    assert "| DNS | 0 | 0 |" not in content


def test_results_md_source_summary_shows_blocked_citilink(tmp_path, monkeypatch):
    import monitor_5070_ti_v_2 as mon

    monkeypatch.chdir(tmp_path)
    mon.save_reports(
        [],
        [
            {
                "source": "Ситилинк",
                "raw_count": 0,
                "filtered_count": 0,
                "error": "",
                "blocked": True,
                "block_reason": "429 too many requests",
                "warnings": ["Citilink access blocked. Manual verification required."],
            }
        ],
    )

    content = Path("results.md").read_text(encoding="utf-8")
    assert "| Ситилинк | unavailable | 0 | 0 | blocked: 429 too many requests | Citilink access blocked. Manual verification required. |" in content
    assert "| Ситилинк | 0 | 0 |" not in content


def test_no_search_urls_in_results():
    offers = [
        mk_offer("RTX 5070 Ti", url="https://shop.example/search/?q=rtx+5070+ti"),
        mk_offer("RTX 5070 Ti", url="https://shop.example/product/5070ti"),
    ]
    filtered = filter_offers(offers)
    assert all("/search" not in x.url and "?q=" not in x.url and "?text=" not in x.url for x in filtered)


def test_yandex_market_offer_search_url_with_sku_passes_filter():
    offer = mk_offer(
        "Palit GeForce RTX 5070 Ti GamingPro",
        price=99990,
        url="https://market.yandex.ru/search?text=rtx%205070%20ti&sku=123456789&uniqueId=98765",
        source="Yandex Market",
    )

    assert filter_offers([offer]) == [offer]


def test_yandex_market_plain_search_and_catalog_urls_are_rejected():
    offers = [
        mk_offer(
            "Palit GeForce RTX 5070 Ti GamingPro",
            url="https://market.yandex.ru/search?text=rtx%205070%20ti",
            source="Yandex Market",
        ),
        mk_offer(
            "Palit GeForce RTX 5070 Ti GamingPro",
            url="https://market.yandex.ru/catalog--videokarty/26912670/list?text=rtx%205070%20ti",
            source="Yandex Market",
        ),
        mk_offer(
            "Palit GeForce RTX 5070 Ti GamingPro",
            url="https://shop.example/search?text=rtx%205070%20ti&sku=123456789",
            source="Other Shop",
        ),
    ]

    assert filter_offers(offers) == []


def test_title_is_not_artificial():
    title = "Palit GeForce RTX 5070 Ti GameRock OC"
    offers = [mk_offer(title)]
    filtered = filter_offers(offers)
    assert filtered and filtered[0].title != "RTX 5070 Ti"


def test_dns_fixture_card_parsing_and_filtering():
    html = Path("tests/fixtures/dns_search.html").read_text(encoding="utf-8")
    cards = parse_dns_cards(html)
    offers = [mk_offer(c["title"], price=c["price"], url=f"https://www.dns-shop.ru{c['url']}") for c in cards]
    filtered = filter_offers(offers)
    assert filtered
    assert "Palit" in filtered[0].title
    assert "/search" not in filtered[0].url and "?q=" not in filtered[0].url and "?text=" not in filtered[0].url
    assert filtered[0].price == 89999
    assert all("РІРѕРґРѕР±Р»РѕРє" not in x.title.lower() for x in filtered)
    assert all(" 5070" not in x.title.lower() or "ti" in x.title.lower() for x in filtered)


def test_dns_detects_blocked_html():
    from parsers import dns

    html = "<html><head><title>403 Forbidden</title></head><body>Доступ к сайту запрещен</body></html>"

    assert dns.detect_block_reason(html) == "403 forbidden"
    assert dns.detect_block_reason("<html><body>Доступ к сайту запрещен</body></html>") == "403 forbidden"
    assert dns.detect_block_reason("<html><body>catalog products</body></html>") is None


def test_dns_parse_offers_with_status_returns_blocked_status(monkeypatch):
    from parsers import dns

    html = "<html><head><title>403 Forbidden</title></head><body>Доступ к сайту запрещен</body></html>"
    monkeypatch.setattr(dns, "_download", lambda url: html)

    result = dns.parse_offers_with_status()

    assert result == {
        "offers": [],
        "blocked": True,
        "block_reason": "403 forbidden",
        "warnings": ["DNS access forbidden. Manual verification required."],
        "errors": 1,
    }
    assert dns.parse_offers() == []


def test_dns_parse_offers_with_status_treats_401_as_blocked(monkeypatch):
    from urllib.error import HTTPError

    from parsers import dns

    def raise_401(url):
        raise HTTPError(url, 401, "Unauthorized", hdrs=None, fp=None)

    monkeypatch.setattr(dns, "_download", raise_401)

    result = dns.parse_offers_with_status()

    assert result["blocked"] is True
    assert result["block_reason"] == "401 unauthorized"
    assert result["warnings"] == ["DNS access forbidden. Manual verification required."]
    assert result["errors"] == 1
    assert result["offers"] == []


@pytest.mark.parametrize(
    ("status_code", "reason"),
    [
        (401, "401 unauthorized"),
        (403, "403 forbidden"),
    ],
)
def test_dns_http_blocked_statuses_are_not_empty_successes(monkeypatch, status_code, reason):
    from parsers import dns

    def raise_http_error(url):
        raise HTTPError(url, status_code, reason, hdrs=None, fp=None)

    monkeypatch.setattr(dns, "_download", raise_http_error)

    result = dns.parse_offers_with_status()

    assert result == {
        "offers": [],
        "blocked": True,
        "block_reason": reason,
        "warnings": ["DNS access forbidden. Manual verification required."],
        "errors": 1,
    }

def test_regard_fixture_card_parsing_and_filtering():
    html = Path("tests/fixtures/regard_search.html").read_text(encoding="utf-8")
    cards = parse_regard_cards(html)
    offers = [mk_offer(c["title"], price=c["price"], url=f"https://www.regard.ru{c['url']}") for c in cards]
    filtered = filter_offers(offers)
    assert len(filtered) == 1
    assert "Windforce" in filtered[0].title
    assert "/product/737606/" in filtered[0].url
    assert filtered[0].price == 92500


def test_yandex_market_fixture_card_parsing_and_filtering():
    html = Path("tests/fixtures/yandex_market_search.html").read_text(encoding="utf-8")
    cards = parse_yandex_cards(html)
    offers = [mk_offer(c["title"], price=c["price"], url=c["url"]) for c in cards]
    filtered = filter_offers(offers)
    assert len(filtered) == 1
    assert "5070" in filtered[0].title
    assert "Ti" in filtered[0].title or "TI" in filtered[0].title.upper()
    assert filtered[0].price == 98940
    assert "/card/" in filtered[0].url


def test_citilink_fixture_card_parsing_and_filtering():
    html = Path("tests/fixtures/citilink_search.html").read_text(encoding="utf-8")
    cards = parse_citilink_cards(html)
    offers = [mk_offer(c["title"], price=c["price"], url=f"https://www.citilink.ru{c['url']}") for c in cards]
    filtered = filter_offers(offers)
    assert len(filtered) == 1
    assert "5070" in filtered[0].title
    assert "TI" in filtered[0].title.upper()
    assert "/search" not in filtered[0].url and "?q=" not in filtered[0].url and "?text=" not in filtered[0].url
    assert filtered[0].price == 100730


def test_citilink_parse_offers_with_status_treats_429_as_blocked(monkeypatch):
    from urllib.error import HTTPError

    from parsers import citilink

    def raise_429(url):
        raise HTTPError(url, 429, "Too Many Requests", hdrs=None, fp=None)

    monkeypatch.setattr(citilink, "_download", raise_429)

    result = citilink.parse_offers_with_status()

    assert result["blocked"] is True
    assert result["block_reason"] == "429 too many requests"
    assert result["warnings"] == ["Citilink access blocked. Manual verification required."]
    assert result["errors"] == 1
    assert result["offers"] == []
    assert citilink.parse_offers() == []


@pytest.mark.parametrize(
    ("status_code", "reason"),
    [
        (401, "401 unauthorized"),
        (403, "403 forbidden"),
        (429, "429 too many requests"),
    ],
)
def test_citilink_http_blocked_statuses_are_not_empty_successes(monkeypatch, status_code, reason):
    from parsers import citilink

    def raise_http_error(url):
        raise HTTPError(url, status_code, reason, hdrs=None, fp=None)

    monkeypatch.setattr(citilink, "_download", raise_http_error)

    result = citilink.parse_offers_with_status()

    assert result == {
        "offers": [],
        "blocked": True,
        "block_reason": reason,
        "warnings": ["Citilink access blocked. Manual verification required."],
        "errors": 1,
    }


def test_citilink_parse_offers_with_status_reports_successful_counts_input(monkeypatch):
    from parsers import citilink

    html = Path("tests/fixtures/citilink_search.html").read_text(encoding="utf-8")
    monkeypatch.setattr(citilink, "_download", lambda url: html)

    result = citilink.parse_offers_with_status()

    assert result["blocked"] is False
    assert result["block_reason"] is None
    assert result["warnings"] == []
    assert result["errors"] == 0
    assert len(result["offers"]) == 3

def test_citilink_parse_offers_with_status_detects_blocked_html(monkeypatch):
    from parsers import citilink

    html = "<html><head><title>429 Too Many Requests</title></head><body>Too many requests</body></html>"
    monkeypatch.setattr(citilink, "_download", lambda url: html)

    result = citilink.parse_offers_with_status()

    assert result["blocked"] is True
    assert result["block_reason"] == "429 too many requests"
    assert result["warnings"] == ["Citilink access blocked. Manual verification required."]
    assert result["errors"] == 1
    assert result["offers"] == []

def test_get_signal_label_for_new_good_and_urgent():
    urgent = mk_offer("RTX 5070 Ti", price=75000)
    good = mk_offer("RTX 5070 Ti", price=90000)
    normal = mk_offer("RTX 5070 Ti", price=91000)

    assert get_signal_label(urgent) == "URGENT_BUY"
    assert get_signal_label(good) == "GOOD_PRICE"
    assert get_signal_label(normal) == "NORMAL"


def test_results_md_contains_tier_sections_and_summary(tmp_path, monkeypatch):
    import monitor_5070_ti_v_2 as mon
    from price_oracle import MarketMedian

    market_median = MarketMedian(value=100_000, source="history", window_days=30, point_count=5, reliable=True)

    monkeypatch.chdir(tmp_path)
    mon.save_reports(
        [
            mk_offer("RTX 5070 Ti Cheap", price=75_000),
            mk_offer("RTX 5070 Ti Mid", price=95_000),
            mk_offer("RTX 5070 Ti Expensive", price=120_000),
        ],
        [{"source": "DNS", "raw_count": 3, "filtered_count": 3, "error": ""}],
        market_median=market_median,
    )

    content = Path("results.md").read_text(encoding="utf-8")
    assert "- buy:" in content
    assert "- at_market:" in content
    assert "- above_market:" in content
    assert "- best offer:" in content
    assert "## Buy" in content
    assert "## Source summary" in content
    assert "| Source | Title | Price | Condition | Availability | Tier | URL |" in content
    assert "https://example.com/product/1" in content


def test_results_json_csv_do_not_include_signal(tmp_path, monkeypatch):
    import csv
    import json
    import monitor_5070_ti_v_2 as mon

    monkeypatch.chdir(tmp_path)
    mon.save_reports([mk_offer("RTX 5070 Ti", price=90000)], [])

    data = json.loads(Path("results.json").read_text(encoding="utf-8"))
    assert isinstance(data, list) and data
    assert "signal" not in data[0]

    with open("results.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert "signal" not in reader.fieldnames

def test_notify_telegram_skips_without_env(monkeypatch):
    import monitor_5070_ti_v_2 as mon

    calls = []

    class DummyRequests:
        @staticmethod
        def post(*args, **kwargs):
            calls.append((args, kwargs))

    monkeypatch.delenv("TG_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TG_CHAT_ID", raising=False)
    monkeypatch.setattr(mon, "requests", DummyRequests, raising=False)
    mon.notify_telegram([mk_offer("RTX 5070 Ti", price=90000)])
    assert calls == []


def test_notify_telegram_sends_good_and_urgent_only(monkeypatch):
    import sys
    import types
    import monitor_5070_ti_v_2 as mon

    calls = []

    def fake_post(url, data, timeout):
        calls.append({"url": url, "data": data, "timeout": timeout})

    monkeypatch.setenv("TG_BOT_TOKEN", "token")
    monkeypatch.setenv("TG_CHAT_ID", "chat")
    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(post=fake_post))

    mon.notify_telegram(
        [
            mk_offer("RTX 5070 Ti urgent", price=75000),
            mk_offer("RTX 5070 Ti good", price=90000),
            mk_offer("RTX 5070 Ti normal", price=100000),
        ]
    )

    assert len(calls) == 1
    text = calls[0]["data"]["text"]
    assert "URGENT_BUY" in text
    assert "GOOD_PRICE" in text
    assert "RTX 5070 Ti normal" not in text


def test_notify_telegram_orders_urgent_before_good_price(monkeypatch):
    import sys
    import types
    import monitor_5070_ti_v_2 as mon

    payload = {}

    def fake_post(url, data, timeout):
        payload["text"] = data["text"]

    monkeypatch.setenv("TG_BOT_TOKEN", "token")
    monkeypatch.setenv("TG_CHAT_ID", "chat")
    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(post=fake_post))

    mon.notify_telegram(
        [
            mk_offer("good lower", price=85000),
            mk_offer("urgent", price=75000),
            mk_offer("good higher", price=90000),
        ]
    )

    text = payload["text"]
    assert text.index("URGENT_BUY") < text.index("GOOD_PRICE")
    assert text.index("good lower") < text.index("good higher")


def test_notify_telegram_includes_source_summary(monkeypatch):
    import sys
    import types
    import monitor_5070_ti_v_2 as mon

    payload = {}

    def fake_post(url, data, timeout):
        payload["text"] = data["text"]

    monkeypatch.setenv("TG_BOT_TOKEN", "token")
    monkeypatch.setenv("TG_CHAT_ID", "chat")
    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(post=fake_post))

    mon.notify_telegram(
        [mk_offer("RTX 5070 Ti good", price=90000)],
        [
            {"source": "DNS", "raw_count": 10, "filtered_count": 2, "error": ""},
            {"source": "Ситилинк", "raw_count": 8, "filtered_count": 1, "error": ""},
            {"source": "Регард", "raw_count": 7, "filtered_count": 1, "error": ""},
        ],
    )

    text = payload["text"]
    assert "Source summary:" in text
    assert "DNS: ok; raw 10; filtered 2; reason: ok; warnings: none" in text
    assert "Ситилинк: ok; raw 8; filtered 1; reason: ok; warnings: none" in text
    assert "Регард: ok; raw 7; filtered 1; reason: ok; warnings: none" in text


def test_notify_telegram_source_summary_shows_blocked_dns(monkeypatch):
    import sys
    import types
    import monitor_5070_ti_v_2 as mon

    payload = {}

    def fake_post(url, data, timeout):
        payload["text"] = data["text"]

    monkeypatch.setenv("TG_BOT_TOKEN", "token")
    monkeypatch.setenv("TG_CHAT_ID", "chat")
    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(post=fake_post))

    mon.notify_telegram(
        [mk_offer("RTX 5070 Ti good", price=90000)],
        [
            {
                "source": "DNS",
                "raw_count": 0,
                "filtered_count": 0,
                "error": "",
                "blocked": True,
                "block_reason": "403 forbidden",
                "warnings": ["DNS access forbidden. Manual verification required."],
            },
            {"source": "Ситилинк", "raw_count": 8, "filtered_count": 1, "error": ""},
        ],
    )

    text = payload["text"]
    assert "DNS: unavailable; raw 0; filtered 0; reason: blocked: 403 forbidden; warnings: DNS access forbidden. Manual verification required." in text
    assert "DNS: raw 0 / filtered 0" not in text
    assert "Ситилинк: ok; raw 8; filtered 1; reason: ok; warnings: none" in text


def test_notify_telegram_source_summary_shows_blocked_citilink(monkeypatch):
    import sys
    import types
    import monitor_5070_ti_v_2 as mon

    payload = {}

    def fake_post(url, data, timeout):
        payload["text"] = data["text"]

    monkeypatch.setenv("TG_BOT_TOKEN", "token")
    monkeypatch.setenv("TG_CHAT_ID", "chat")
    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(post=fake_post))

    mon.notify_telegram(
        [mk_offer("RTX 5070 Ti good", price=90000)],
        [
            {
                "source": "Ситилинк",
                "raw_count": 0,
                "filtered_count": 0,
                "error": "",
                "blocked": True,
                "block_reason": "429 too many requests",
                "warnings": ["Citilink access blocked. Manual verification required."],
            },
        ],
    )

    text = payload["text"]
    assert "Ситилинк: unavailable; raw 0; filtered 0; reason: blocked: 429 too many requests; warnings: Citilink access blocked. Manual verification required." in text
    assert "Ситилинк: raw 0 / filtered 0" not in text


def test_notify_telegram_daily_report_sends_even_without_signals(monkeypatch):
    import sys
    import types
    import monitor_5070_ti_v_2 as mon

    calls = []

    def fake_post(url, data, timeout):
        calls.append({"url": url, "data": data, "timeout": timeout})

    monkeypatch.setenv("TG_BOT_TOKEN", "token")
    monkeypatch.setenv("TG_CHAT_ID", "chat")
    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(post=fake_post))

    mon.notify_telegram([mk_offer("RTX 5070 Ti normal", price=100000)], daily_report=True)

    assert len(calls) == 1
    text = calls[0]["data"]["text"]
    assert "📊 RTX 5070 Ti daily report" in text
    assert "Signals:" in text
    assert "- total: 0" in text
    assert "Total filtered offers: 1" in text


def test_notify_telegram_daily_report_includes_best_price(monkeypatch):
    import sys
    import types
    import monitor_5070_ti_v_2 as mon

    payload = {}

    def fake_post(url, data, timeout):
        payload["text"] = data["text"]

    monkeypatch.setenv("TG_BOT_TOKEN", "token")
    monkeypatch.setenv("TG_CHAT_ID", "chat")
    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(post=fake_post))

    mon.notify_telegram(
        [
            mk_offer("RTX 5070 Ti cheapest", price=94800),
            mk_offer("RTX 5070 Ti expensive", price=104510),
        ],
        [{"source": "Ситилинк", "raw_count": 2, "filtered_count": 2, "error": ""}],
        daily_report=True,
    )

    text = payload["text"]
    assert "Best overall price:" in text
    assert "94800 RUB - DNS" in text
    assert "RTX 5070 Ti cheapest" in text
    assert "Ситилинк: ok; raw 2; filtered 2; reason: ok; warnings: none" in text


def test_notify_telegram_daily_report_handles_no_offers(monkeypatch):
    import sys
    import types
    import monitor_5070_ti_v_2 as mon

    payload = {}

    def fake_post(url, data, timeout):
        payload["text"] = data["text"]

    monkeypatch.setenv("TG_BOT_TOKEN", "token")
    monkeypatch.setenv("TG_CHAT_ID", "chat")
    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(post=fake_post))

    mon.notify_telegram([], [], daily_report=True)

    text = payload["text"]
    assert "Best overall price: n/a" in text
    assert "Total filtered offers: 0" in text


def test_daily_report_cli_flag_passed_to_notify(monkeypatch):
    import monitor_5070_ti_v_2 as mon

    captured = {}

    monkeypatch.setattr(mon, "configure_logging", lambda: None)
    monkeypatch.setattr(mon, "save_reports", lambda offers, source_stats=None, config=None, market_median=None: None)
    monkeypatch.setattr(mon, "notify_telegram", lambda offers, source_stats=None, daily_report=False, config=None: captured.update({"daily_report": daily_report}))
    monkeypatch.setattr(mon.dns, "parse_offers", lambda browser_mode=False: [])
    monkeypatch.setattr(mon.dns, "parse_offers_with_status", lambda browser_mode=False: {"offers": [], "blocked": False, "block_reason": None, "warnings": [], "errors": 0})
    monkeypatch.setattr(mon.citilink, "parse_offers_with_status", lambda browser_mode=False: {"offers": [], "blocked": False, "block_reason": None, "warnings": [], "errors": 0})
    monkeypatch.setattr(mon.regard, "parse_offers", lambda: [])
    set_enabled_sources(monkeypatch, mon, (("DNS", mon.dns), ("Ситилинк", mon.citilink), ("Регард", mon.regard)))
    monkeypatch.setattr("sys.argv", ["monitor_5070_ti_v_2.py", "--browser", "--daily-report"])

    mon.main()

    assert captured["daily_report"] is True


def test_main_retries_blocked_dns_with_browser_fallback_success(monkeypatch):
    import monitor_5070_ti_v_2 as mon

    calls = []
    captured = {}
    fallback_offer = mk_offer("RTX 5070 Ti browser offer", price=90000)

    def fake_dns(browser_mode=False):
        calls.append(browser_mode)
        if browser_mode:
            return {"offers": [fallback_offer], "blocked": False, "block_reason": None, "warnings": ["browser ok"], "errors": 0}
        return {"offers": [], "blocked": True, "block_reason": "401 unauthorized", "warnings": ["DNS blocked"], "errors": 0}

    monkeypatch.setattr(mon, "configure_logging", lambda: None)
    monkeypatch.setattr(mon, "save_reports", lambda offers, source_stats=None, config=None, market_median=None: captured.update({"offers": offers, "source_stats": source_stats}))
    monkeypatch.setattr(mon, "notify_telegram", lambda offers, source_stats=None, daily_report=False, config=None: None)
    monkeypatch.setattr(mon.dns, "parse_offers_with_status", fake_dns)
    monkeypatch.setattr(mon.citilink, "parse_offers_with_status", lambda browser_mode=False: {"offers": [], "blocked": False, "block_reason": None, "warnings": [], "errors": 0})
    monkeypatch.setattr(mon.regard, "parse_offers", lambda: [])
    set_enabled_sources(monkeypatch, mon, (("DNS", mon.dns), ("Ситилинк", mon.citilink), ("Регард", mon.regard)))
    monkeypatch.setattr("sys.argv", ["monitor_5070_ti_v_2.py"])

    mon.main()

    dns_stat = captured["source_stats"][0]
    assert calls == [False, True]
    assert captured["offers"] == [fallback_offer]
    assert dns_stat["raw_count"] == 1
    assert dns_stat["blocked"] is False
    assert dns_stat["block_reason"] is None
    assert dns_stat["warnings"] == ["browser ok"]


def test_main_preserves_original_block_when_browser_fallback_has_no_offers(monkeypatch):
    import monitor_5070_ti_v_2 as mon

    calls = []
    captured = {}

    def fake_dns(browser_mode=False):
        calls.append(browser_mode)
        if browser_mode:
            return {"offers": [], "blocked": False, "block_reason": None, "warnings": ["browser empty"], "errors": 0}
        return {"offers": [], "blocked": True, "block_reason": "401 unauthorized", "warnings": ["DNS blocked"], "errors": 0}

    monkeypatch.setattr(mon, "configure_logging", lambda: None)
    monkeypatch.setattr(mon, "save_reports", lambda offers, source_stats=None, config=None, market_median=None: captured.update({"offers": offers, "source_stats": source_stats}))
    monkeypatch.setattr(mon, "notify_telegram", lambda offers, source_stats=None, daily_report=False, config=None: None)
    monkeypatch.setattr(mon.dns, "parse_offers_with_status", fake_dns)
    monkeypatch.setattr(mon.citilink, "parse_offers_with_status", lambda browser_mode=False: {"offers": [], "blocked": False, "block_reason": None, "warnings": [], "errors": 0})
    monkeypatch.setattr(mon.regard, "parse_offers", lambda: [])
    set_enabled_sources(monkeypatch, mon, (("DNS", mon.dns), ("Ситилинк", mon.citilink), ("Регард", mon.regard)))
    monkeypatch.setattr("sys.argv", ["monitor_5070_ti_v_2.py"])

    mon.main()

    dns_stat = captured["source_stats"][0]
    assert calls == [False, True]
    assert captured["offers"] == []
    assert dns_stat["raw_count"] == 0
    assert dns_stat["blocked"] is True
    assert dns_stat["block_reason"] == "401 unauthorized"
    assert dns_stat["warnings"] == ["DNS blocked", mon.BROWSER_FALLBACK_NO_OFFERS_WARNING, "browser empty"]


def test_main_does_not_retry_when_browser_mode_was_requested(monkeypatch):
    import monitor_5070_ti_v_2 as mon

    calls = []
    captured = {}

    def fake_dns(browser_mode=False):
        calls.append(browser_mode)
        return {"offers": [], "blocked": True, "block_reason": "browser blocked", "warnings": ["still blocked"], "errors": 0}

    monkeypatch.setattr(mon, "configure_logging", lambda: None)
    monkeypatch.setattr(mon, "save_reports", lambda offers, source_stats=None, config=None, market_median=None: captured.update({"source_stats": source_stats}))
    monkeypatch.setattr(mon, "notify_telegram", lambda offers, source_stats=None, daily_report=False, config=None: None)
    monkeypatch.setattr(mon.dns, "parse_offers_with_status", fake_dns)
    monkeypatch.setattr(mon.citilink, "parse_offers_with_status", lambda browser_mode=False: {"offers": [], "blocked": False, "block_reason": None, "warnings": [], "errors": 0})
    monkeypatch.setattr(mon.regard, "parse_offers", lambda: [])
    set_enabled_sources(monkeypatch, mon, (("DNS", mon.dns), ("Ситилинк", mon.citilink), ("Регард", mon.regard)))
    monkeypatch.setattr("sys.argv", ["monitor_5070_ti_v_2.py", "--browser"])

    mon.main()

    dns_stat = captured["source_stats"][0]
    assert calls == [True]
    assert dns_stat["blocked"] is True
    assert dns_stat["warnings"] == ["still blocked"]


def test_browser_fallback_exception_is_kept_as_warning(monkeypatch):
    import types
    import monitor_5070_ti_v_2 as mon

    def fake_parse_offers_with_status(browser_mode=False):
        raise RuntimeError("chromium unavailable")

    original_status = {"offers": [], "blocked": True, "block_reason": "429 too many requests", "warnings": ["Citilink blocked"], "errors": 0}
    module = types.SimpleNamespace(parse_offers_with_status=fake_parse_offers_with_status)

    status, error = mon.apply_browser_fallback_if_blocked("Citilink", module, original_status, "", False)

    assert error == ""
    assert status["blocked"] is True
    assert status["block_reason"] == "429 too many requests"
    assert status["warnings"] == [
        "Citilink blocked",
        mon.BROWSER_FALLBACK_NO_OFFERS_WARNING,
        "Browser fallback failed: chromium unavailable",
    ]


def test_enabled_sources_include_existing_retailer_modules():
    import monitor_5070_ti_v_2 as mon

    sources = dict(mon.ENABLED_SOURCES)

    assert sources["DNS"] is mon.dns
    assert sources["Ситилинк"] is mon.citilink
    assert sources["Регард"] is mon.regard
    assert sources["М.Видео"] is mon.mvideo
    assert sources["Эльдорадо"] is mon.eldorado
    assert sources["Wildberries"] is mon.wildberries
    assert sources["Мегамаркет"] is mon.megamarket
    assert sources["AliExpress"] is mon.aliexpress
    assert sources["ComputerUniverse"] is mon.computeruniverse
    assert sources["СДЭК Shopping"] is mon.cdek_shopping
    assert sources["Ozon"] is mon.ozon
    assert sources["Яндекс Маркет"] is mon.yandex_market
    assert sources["Avito"] is mon.avito


def test_main_attempts_multiple_existing_sources_and_isolates_failures(monkeypatch):
    import types
    import monitor_5070_ti_v_2 as mon

    calls = []
    captured = {}
    working_offer = mk_offer("RTX 5070 Ti working", price=89000)

    def working_parse():
        calls.append("working")
        return [working_offer]

    def failing_parse():
        calls.append("failing")
        raise RuntimeError("shop down")

    working_source = types.SimpleNamespace(parse_offers=working_parse)
    failing_source = types.SimpleNamespace(parse_offers=failing_parse)

    monkeypatch.setattr(mon, "configure_logging", lambda: None)
    monkeypatch.setattr(mon, "save_reports", lambda offers, source_stats=None, config=None, market_median=None: captured.update({"offers": offers, "source_stats": source_stats}))
    monkeypatch.setattr(mon, "notify_telegram", lambda offers, source_stats=None, daily_report=False, config=None: None)
    set_enabled_sources(monkeypatch, mon, (("М.Видео", working_source), ("Эльдорадо", failing_source)))
    monkeypatch.setattr("sys.argv", ["monitor_5070_ti_v_2.py"])

    mon.main()

    assert calls == ["working", "failing"]
    assert captured["offers"] == [working_offer]
    assert captured["source_stats"] == [
        {"source": "М.Видео", "raw_count": 1, "filtered_count": 1, "error": "", "blocked": False, "block_reason": None, "warnings": []},
        {"source": "Эльдорадо", "raw_count": 0, "filtered_count": 0, "error": "shop down", "blocked": False, "block_reason": None, "warnings": []},
    ]

def test_load_config_defaults_when_missing(tmp_path):
    import monitor_5070_ti_v_2 as mon

    cfg = mon.load_config(tmp_path / "missing.json")
    assert cfg == mon.DEFAULT_CONFIG


def test_load_config_uses_values_from_file(tmp_path):
    import json
    import monitor_5070_ti_v_2 as mon

    path = tmp_path / "config.json"
    path.write_text(json.dumps({"new_good_price": 95000, "median_window_days": 14}), encoding="utf-8")

    cfg = mon.load_config(path)
    assert cfg["new_good_price"] == 95000
    assert cfg["median_window_days"] == 14


def test_load_config_fallbacks_for_missing_keys(tmp_path):
    import json
    import monitor_5070_ti_v_2 as mon

    path = tmp_path / "config.json"
    path.write_text(json.dumps({"new_good_price": 95000}), encoding="utf-8")

    cfg = mon.load_config(path)
    assert cfg["new_good_price"] == 95000
    assert cfg["new_urgent_buy"] == mon.DEFAULT_CONFIG["new_urgent_buy"]
    assert cfg["used_good_price"] == mon.DEFAULT_CONFIG["used_good_price"]


def test_filter_offers_no_longer_rejects_above_market_price():
    import monitor_5070_ti_v_2 as mon

    # Price ceiling removed — all valid GPU offers pass regardless of price
    cheap = mk_offer("RTX 5070 Ti", price=80_000)
    expensive = mk_offer("RTX 5070 Ti", price=200_000)

    filtered = mon.filter_offers([cheap, expensive], mon.DEFAULT_CONFIG.copy())
    assert cheap in filtered
    assert expensive in filtered


def test_classify_signal_uses_config_thresholds():
    import monitor_5070_ti_v_2 as mon

    cfg = mon.DEFAULT_CONFIG.copy()
    cfg["new_good_price"] = 95000
    cfg["new_urgent_buy"] = 80000

    assert mon.classify_signal(mk_offer("RTX 5070 Ti", price=79000), cfg) == "urgent_buy"
    assert mon.classify_signal(mk_offer("RTX 5070 Ti", price=94800), cfg) == "good_price"
    assert mon.classify_signal(mk_offer("RTX 5070 Ti", price=96000), cfg) is None


def test_results_md_contains_config_thresholds(tmp_path, monkeypatch):
    import monitor_5070_ti_v_2 as mon

    cfg = mon.DEFAULT_CONFIG.copy()
    cfg["new_good_price"] = 95000

    monkeypatch.chdir(tmp_path)
    mon.save_reports([mk_offer("RTX 5070 Ti", price=94800)], [], cfg)

    content = Path("results.md").read_text(encoding="utf-8")
    assert "## Config" in content
    assert "- new_good_price: 95000" in content
    assert "- suspicious_pct:" in content
    assert "- buy_pct:" in content


def test_daily_report_telegram_contains_threshold_line(monkeypatch):
    import sys
    import types
    import monitor_5070_ti_v_2 as mon

    payload = {}

    def fake_post(url, data, timeout):
        payload["text"] = data["text"]

    cfg = mon.DEFAULT_CONFIG.copy()
    cfg["new_good_price"] = 95000
    cfg["new_urgent_buy"] = 80000

    monkeypatch.setenv("TG_BOT_TOKEN", "token")
    monkeypatch.setenv("TG_CHAT_ID", "chat")
    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(post=fake_post))

    mon.notify_telegram([mk_offer("RTX 5070 Ti", price=94800)], [], daily_report=True, config=cfg)

    assert "- thresholds: good <= 95000 RUB, urgent <= 80000 RUB" in payload["text"]


def test_dns_detects_http_403_browser_html():
    from parsers import dns

    html = """
    <html>
      <head><title>HTTP 403</title></head>
      <body>
        <div class="title">403 Error</div>
        <div class="sub-title">Forbidden</div>
        <p>Access to www.dns-shop.ru is forbidden.</p>
      </body>
    </html>
    """

    assert dns.detect_block_reason(html) == "403 forbidden"


def test_dns_diagnose_html_detects_qrator_antibot():
    from parsers import dns

    html = '<html><head><script src="/__qrator/qauth_utm_v2d_v9118.js"></script></head><body></body></html>'

    diagnostics = dns.diagnose_html(html)

    assert diagnostics["contains_qrator"] is True
    assert diagnostics["contains_captcha"] is True
    assert diagnostics["contains_catalog_product"] is False
    assert diagnostics["contains_product_link"] is False


def test_dns_browser_qrator_state_returns_warning(monkeypatch):
    from parsers import dns

    html = '<html><head><script src="/__qrator/qauth_utm_v2d_v9118.js"></script></head><body></body></html>'
    monkeypatch.setattr(dns, "fetch_html", lambda *args, **kwargs: html)

    result = dns.parse_offers_with_status(browser_mode=True)

    assert result["blocked"] is False
    assert result["block_reason"] is None
    assert result["errors"] == 1
    assert result["offers"] == []
    assert result["warnings"] == ["DNS browser HTML looks like Qrator anti-bot challenge. Manual verification required."]


def test_dns_browser_no_cards_problem_state_returns_warning(monkeypatch):
    from parsers import dns

    html = "<html><body><main>DNS shell page without product cards</main></body></html>"
    monkeypatch.setattr(dns, "fetch_html", lambda *args, **kwargs: html)

    result = dns.parse_offers_with_status(browser_mode=True)

    assert result["blocked"] is False
    assert result["block_reason"] is None
    assert result["errors"] == 1
    assert result["offers"] == []
    assert result["warnings"] == [
        "DNS browser HTML contains no parsed product cards. Possible parser mismatch, empty state, or anti-bot page."
    ]


def test_dns_parse_product_link_fallback_card():
    from parsers import dns

    html = """
    <html>
      <body>
        <article class="product-card">
          <a href="/product/abc123/videokarta-palit-geforce-rtx-5070-ti-gamingpro/">
            Видеокарта Palit GeForce RTX 5070 Ti GamingPro 16GB
          </a>
          <div class="price">89 999 ₽</div>
        </article>
      </body>
    </html>
    """

    cards = dns.parse_cards(html)

    assert len(cards) == 1
    assert cards[0]["title"] == "Видеокарта Palit GeForce RTX 5070 Ti GamingPro 16GB"
    assert cards[0]["url"] == "/product/abc123/videokarta-palit-geforce-rtx-5070-ti-gamingpro/"
    assert cards[0]["price"] == 89999
    assert cards[0]["availability"] == "unknown"


def test_citilink_smoke_detects_block_signs():
    from tools import smoke_citilink

    html = "<html><title>HTTP 403</title><body>Access denied by security check</body></html>"

    signs = smoke_citilink.detect_signs(html, status=403)

    assert signs["block"] is True
    assert signs["access_denied"] is True


def test_citilink_smoke_counts_fixture_candidates():
    from tools import smoke_citilink

    html = Path("tests/fixtures/citilink_search.html").read_text(encoding="utf-8")

    counts = smoke_citilink.count_candidates(html)

    assert counts["snippet_titles"] == 3
    assert counts["snippet_prices"] == 3
    assert counts["parsed_cards"] == 3


# ---------------------------------------------------------------------------
# Market-median price classification tests
# ---------------------------------------------------------------------------

def test_classify_market_tier_boundary_minus35pct():
    from price_oracle import classify_market_tier, TIER_BUY, TIER_SUSPICIOUS

    # median=100_000; suspicious_pct=65 → boundary at 65_000 (inclusive for buy)
    assert classify_market_tier(65_000, 100_000) == TIER_BUY       # exactly −35% → buy
    assert classify_market_tier(64_999, 100_000) == TIER_SUSPICIOUS  # one below → suspicious


def test_classify_market_tier_boundary_minus10pct():
    from price_oracle import classify_market_tier, TIER_BUY, TIER_AT_MARKET

    # buy_pct=90 → upper bound at 90_000 (inclusive for buy)
    assert classify_market_tier(90_000, 100_000) == TIER_BUY       # exactly −10% → buy
    assert classify_market_tier(90_001, 100_000) == TIER_AT_MARKET  # one above → at_market


def test_classify_market_tier_boundary_plus10pct():
    from price_oracle import classify_market_tier, TIER_AT_MARKET, TIER_ABOVE_MARKET

    # at_market_pct=110 → upper bound at 110_000 (inclusive for at_market)
    assert classify_market_tier(110_000, 100_000) == TIER_AT_MARKET   # exactly +10% → at_market
    assert classify_market_tier(110_001, 100_000) == TIER_ABOVE_MARKET  # one above → above_market


def test_compute_market_median_from_history(tmp_path):
    import json
    from datetime import datetime, timezone
    from price_oracle import compute_market_median

    history = tmp_path / "price_history.jsonl"
    ts = "2026-06-01T10:00:00+00:00"
    prices = [90_000, 95_000, 100_000, 105_000, 110_000]
    history.write_text(
        "\n".join(
            json.dumps({"timestamp": ts, "source": "DNS", "title": "RTX 5070 Ti", "price": p, "currency": "RUB"})
            for p in prices
        ),
        encoding="utf-8",
    )

    now = datetime(2026, 6, 2, 0, 0, 0, tzinfo=timezone.utc)
    result = compute_market_median([], history_path=history, window_days=30, min_count=5, now=now)

    assert result is not None
    assert result.value == 100_000.0
    assert result.reliable is True
    assert result.source == "history"
    assert result.point_count == 5


def test_compute_market_median_fallback_to_current_run(tmp_path):
    from datetime import datetime, timezone
    from price_oracle import compute_market_median

    history = tmp_path / "price_history.jsonl"
    history.write_text("", encoding="utf-8")  # empty

    now = datetime(2026, 6, 2, 0, 0, 0, tzinfo=timezone.utc)
    current_prices = [90_000.0, 100_000.0, 110_000.0]
    result = compute_market_median(current_prices, history_path=history, min_count=5, now=now)

    assert result is not None
    assert result.reliable is False
    assert result.source == "current_run"
    assert result.value == 100_000.0


def test_compute_market_median_returns_none_when_no_data(tmp_path):
    from datetime import datetime, timezone
    from price_oracle import compute_market_median

    history = tmp_path / "price_history.jsonl"
    history.write_text("", encoding="utf-8")

    now = datetime(2026, 6, 2, 0, 0, 0, tzinfo=timezone.utc)
    result = compute_market_median([], history_path=history, now=now)

    assert result is None


def test_filter_does_not_reject_accessory_high_price_offer():
    """Removing the price ceiling must not let non-GPU accessories through."""
    import monitor_5070_ti_v_2 as mon

    accessory = mk_offer("Gaming PC RTX 5070 Ti", price=50_000)
    gpu = mk_offer("Видеокарта RTX 5070 Ti", price=200_000)

    filtered = mon.filter_offers([accessory, gpu], mon.DEFAULT_CONFIG.copy())
    assert accessory not in filtered  # accessory filter still works
    assert gpu in filtered             # expensive GPU passes now


def test_end_to_end_yandex_offer_above_market(tmp_path, monkeypatch):
    """138 217 ₽ Яндекс-оффер saved as above_market, not dropped by price filter."""
    import json
    from price_oracle import compute_market_median, TIER_ABOVE_MARKET
    import monitor_5070_ti_v_2 as mon

    yandex_offer = mk_offer(
        "NVIDIA RTX 5070 Ti 16GB",
        price=138_217,
        url="https://market.yandex.ru/product/123",
        source="Яндекс Маркет",
    )
    cheap_offer = mk_offer("RTX 5070 Ti MSI", price=95_000, source="DNS")

    cfg = mon.DEFAULT_CONFIG.copy()
    filtered = mon.filter_offers([yandex_offer, cheap_offer], cfg)
    assert yandex_offer in filtered, "138 217 ₽ offer must not be dropped by filter"

    history = tmp_path / "price_history.jsonl"
    ts = "2026-06-01T10:00:00+00:00"
    prices = [95_000, 100_000, 105_000, 110_000, 108_000]
    history.write_text(
        "\n".join(
            json.dumps({"timestamp": ts, "price": p, "source": "DNS", "title": "RTX 5070 Ti", "currency": "RUB"})
            for p in prices
        ),
        encoding="utf-8",
    )
    from datetime import datetime, timezone
    now = datetime(2026, 6, 2, 0, 0, 0, tzinfo=timezone.utc)
    market_median = compute_market_median([], history_path=history, now=now)

    tier = mon.get_market_tier(yandex_offer, market_median, cfg)
    cheap_tier = mon.get_market_tier(cheap_offer, market_median, cfg)

    assert tier == TIER_ABOVE_MARKET
    assert cheap_tier in ("buy", "at_market")


def test_get_market_tier_uses_config_ratios():
    import monitor_5070_ti_v_2 as mon
    from price_oracle import MarketMedian, TIER_BUY, TIER_AT_MARKET, TIER_ABOVE_MARKET

    market_median = MarketMedian(value=100_000, source="history", window_days=30, point_count=10, reliable=True)
    cfg = mon.DEFAULT_CONFIG.copy()

    assert mon.get_market_tier(mk_offer("RTX 5070 Ti", price=85_000), market_median, cfg) == TIER_BUY
    assert mon.get_market_tier(mk_offer("RTX 5070 Ti", price=100_000), market_median, cfg) == TIER_AT_MARKET
    assert mon.get_market_tier(mk_offer("RTX 5070 Ti", price=115_000), market_median, cfg) == TIER_ABOVE_MARKET


def test_results_md_shows_market_median_section(tmp_path, monkeypatch):
    import monitor_5070_ti_v_2 as mon
    from price_oracle import MarketMedian

    cfg = mon.DEFAULT_CONFIG.copy()
    market_median = MarketMedian(value=105_000, source="history", window_days=30, point_count=18, reliable=True)

    monkeypatch.chdir(tmp_path)
    mon.save_reports([mk_offer("RTX 5070 Ti", price=94_800)], [], cfg, market_median)

    content = Path("results.md").read_text(encoding="utf-8")
    assert "## Market median" in content
    assert "105000 RUB" in content
    assert "Points: 18" in content
    assert "reliable" in content


def test_results_md_groups_offers_by_tier(tmp_path, monkeypatch):
    import monitor_5070_ti_v_2 as mon
    from price_oracle import MarketMedian

    cfg = mon.DEFAULT_CONFIG.copy()
    market_median = MarketMedian(value=100_000, source="history", window_days=30, point_count=10, reliable=True)

    buy_offer = mk_offer("RTX 5070 Ti cheap", price=85_000)
    above_offer = mk_offer("RTX 5070 Ti exp", price=120_000)

    monkeypatch.chdir(tmp_path)
    mon.save_reports([buy_offer, above_offer], [], cfg, market_median)

    content = Path("results.md").read_text(encoding="utf-8")
    assert "## Buy" in content
    assert "## Above market" in content
    buy_pos = content.index("## Buy")
    above_pos = content.index("## Above market")
    assert buy_pos < above_pos  # buy section comes first
