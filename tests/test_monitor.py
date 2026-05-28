from pathlib import Path

from monitor_5070_ti_v_2 import filter_offers, get_signal_label
from models import ProductOffer
from parsers.citilink import parse_cards as parse_citilink_cards
from parsers.dns import parse_cards as parse_dns_cards
from parsers.regard import parse_cards as parse_regard_cards


def mk_offer(title: str, raw: str = "", price: float = 100000, url: str = "https://example.com/product/1") -> ProductOffer:
    return ProductOffer("DNS", title, price, "RUB", url, "new", "DNS", "in_stock", "2026-01-01T00:00:00+00:00", 0.9, raw)


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
    assert "| DNS | 3 | 1 |  |" in content


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
    assert "| DNS | blocked | 403 forbidden | DNS access forbidden. Manual verification required. |" in content
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
    assert "| Ситилинк | blocked | 429 too many requests | Citilink access blocked. Manual verification required. |" in content
    assert "| Ситилинк | 0 | 0 |" not in content


def test_no_search_urls_in_results():
    offers = [
        mk_offer("RTX 5070 Ti", url="https://shop.example/search/?q=rtx+5070+ti"),
        mk_offer("RTX 5070 Ti", url="https://shop.example/product/5070ti"),
    ]
    filtered = filter_offers(offers)
    assert all("/search" not in x.url and "?q=" not in x.url and "?text=" not in x.url for x in filtered)


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


def test_regard_fixture_card_parsing_and_filtering():
    html = Path("tests/fixtures/regard_search.html").read_text(encoding="utf-8")
    cards = parse_regard_cards(html)
    offers = [mk_offer(c["title"], price=c["price"], url=f"https://www.regard.ru{c['url']}") for c in cards]
    filtered = filter_offers(offers)
    assert len(filtered) == 1
    assert "Windforce" in filtered[0].title
    assert "/product/737606/" in filtered[0].url
    assert filtered[0].price == 92500


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


def test_results_md_contains_signal_column_and_best_offers(tmp_path, monkeypatch):
    import monitor_5070_ti_v_2 as mon

    monkeypatch.chdir(tmp_path)
    mon.save_reports(
        [
            mk_offer("RTX 5070 Ti Urgent", price=75000),
            mk_offer("RTX 5070 Ti Good", price=90000),
            mk_offer("RTX 5070 Ti Normal", price=100000),
        ],
        [{"source": "DNS", "raw_count": 3, "filtered_count": 3, "error": ""}],
    )

    content = Path("results.md").read_text(encoding="utf-8")
    assert "- urgent_buy count: 1" in content
    assert "- good_price count: 1" in content
    assert "- normal count: 1" in content
    assert "- best offer:" in content
    assert "## Best offers" in content
    assert "## Source summary" in content
    assert "| Source | Title | Price | Condition | Availability | Signal | URL |" in content
    assert "URGENT_BUY" in content
    assert "GOOD_PRICE" in content
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
    assert "DNS: raw 10 / filtered 2" in text
    assert "Ситилинк: raw 8 / filtered 1" in text
    assert "Регард: raw 7 / filtered 1" in text


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
    assert "DNS: blocked / 403 forbidden" in text
    assert "DNS: raw 0 / filtered 0" not in text
    assert "Ситилинк: raw 8 / filtered 1" in text


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
    assert "Ситилинк: blocked / 429 too many requests" in text
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
    assert "Signals: 0" in text
    assert "Total offers: 1" in text


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
    assert "Best price:" in text
    assert "94800 RUB — DNS" in text
    assert "RTX 5070 Ti cheapest" in text
    assert "Ситилинк: raw 2 / filtered 2" in text


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
    assert "Best price: n/a" in text
    assert "Total offers: 0" in text


def test_daily_report_cli_flag_passed_to_notify(monkeypatch):
    import monitor_5070_ti_v_2 as mon

    captured = {}

    monkeypatch.setattr(mon, "configure_logging", lambda: None)
    monkeypatch.setattr(mon, "save_reports", lambda offers, source_stats=None, config=None: None)
    monkeypatch.setattr(mon, "notify_telegram", lambda offers, source_stats=None, daily_report=False, config=None: captured.update({"daily_report": daily_report}))
    monkeypatch.setattr(mon.dns, "parse_offers", lambda browser_mode=False: [])
    monkeypatch.setattr(mon.dns, "parse_offers_with_status", lambda browser_mode=False: {"offers": [], "blocked": False, "block_reason": None, "warnings": [], "errors": 0})
    monkeypatch.setattr(mon.citilink, "parse_offers_with_status", lambda browser_mode=False: {"offers": [], "blocked": False, "block_reason": None, "warnings": [], "errors": 0})
    monkeypatch.setattr(mon.regard, "parse_offers", lambda: [])
    monkeypatch.setattr("sys.argv", ["monitor_5070_ti_v_2.py", "--browser", "--daily-report"])

    mon.main()

    assert captured["daily_report"] is True

def test_load_config_defaults_when_missing(tmp_path):
    import monitor_5070_ti_v_2 as mon

    cfg = mon.load_config(tmp_path / "missing.json")
    assert cfg == mon.DEFAULT_CONFIG


def test_load_config_uses_values_from_file(tmp_path):
    import json
    import monitor_5070_ti_v_2 as mon

    path = tmp_path / "config.json"
    path.write_text(json.dumps({"new_good_price": 95000, "max_price_rub": 120000}), encoding="utf-8")

    cfg = mon.load_config(path)
    assert cfg["new_good_price"] == 95000
    assert cfg["max_price_rub"] == 120000


def test_load_config_fallbacks_for_missing_keys(tmp_path):
    import json
    import monitor_5070_ti_v_2 as mon

    path = tmp_path / "config.json"
    path.write_text(json.dumps({"new_good_price": 95000}), encoding="utf-8")

    cfg = mon.load_config(path)
    assert cfg["new_good_price"] == 95000
    assert cfg["new_urgent_buy"] == mon.DEFAULT_CONFIG["new_urgent_buy"]
    assert cfg["used_good_price"] == mon.DEFAULT_CONFIG["used_good_price"]


def test_filter_offers_uses_max_price_from_config():
    import monitor_5070_ti_v_2 as mon

    cfg = mon.DEFAULT_CONFIG.copy()
    cfg["max_price_rub"] = 95000

    accepted = mk_offer("RTX 5070 Ti", price=94000)
    rejected = mk_offer("RTX 5070 Ti", price=96000)

    filtered = mon.filter_offers([accepted, rejected], cfg)
    assert filtered == [accepted]


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
    assert "- max_price_rub:" in content


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

    assert "Thresholds: good <= 95000 RUB, urgent <= 80000 RUB" in payload["text"]


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
