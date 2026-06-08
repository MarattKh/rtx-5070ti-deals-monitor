import json
from pathlib import Path

import monitor_5070_ti_v_2 as mon
from parsers.common import build_search_url
from target_config import DEFAULT_TARGET, get_query, get_source_filter, load_target


def test_repo_target_json_matches_5070_ti_defaults():
    """The checked-in target.json must reproduce the original 5070 Ti config."""
    repo_target = load_target(Path(__file__).resolve().parent.parent / "target.json")
    assert repo_target["product_id"] == "rtx_5070_ti"
    assert repo_target["label"] == "RTX 5070 Ti"
    assert repo_target["query"] == "rtx 5070 ti"
    assert repo_target == DEFAULT_TARGET


def test_load_target_falls_back_to_defaults_when_missing(tmp_path):
    target = load_target(tmp_path / "absent.json")
    assert target == DEFAULT_TARGET


def test_load_target_falls_back_on_malformed_file(tmp_path):
    path = tmp_path / "target.json"
    path.write_text("{ not valid json", encoding="utf-8")
    assert load_target(path) == DEFAULT_TARGET


def test_module_target_is_loaded_5070_ti():
    assert mon.TARGET["product_id"] == "rtx_5070_ti"
    assert mon.TARGET["label"] == "RTX 5070 Ti"


def test_relevance_is_driven_by_target_config():
    """filter_offers relevance must come from the target ruleset, not hard-code."""
    relevant = mon.is_relevant_product("MSI RTX 5070 Ti Gaming", "")
    assert relevant is True

    # A custom relevance ruleset rejects the 5070 Ti and accepts something else.
    custom = {
        "match_any": [{"all_tokens": ["5080"]}],
        "exclude_patterns": [],
    }
    haystack = mon.normalize_title("MSI RTX 5070 Ti Gaming")
    assert mon._has_product_signal(haystack, haystack.replace(" ", ""), custom) is False
    other = mon.normalize_title("MSI RTX 5080 Gaming")
    assert mon._has_product_signal(other, other.replace(" ", ""), custom) is True


def test_build_search_url_reproduces_encodings():
    assert build_search_url("https://x/?text={query}", "rtx 5070 ti") == "https://x/?text=rtx%205070%20ti"
    assert build_search_url("https://x/?search={query}", "rtx 5070 ti", plus=True) == "https://x/?search=rtx+5070+ti"


def test_get_query_returns_target_query():
    assert get_query(Path(__file__).resolve().parent.parent / "target.json") == "rtx 5070 ti"


# ---------------------------------------------------------------------------
# source_filters tests
# ---------------------------------------------------------------------------

def test_repo_target_json_has_all_five_source_filters():
    repo = load_target(Path(__file__).resolve().parent.parent / "target.json")
    filters = repo["source_filters"]
    assert filters["XCOM-SHOP"] == "nvidia-geforce-rtx-5070-ti"
    assert filters["KNS"] == "nvidia-geforce-rtx-5070-ti"
    assert filters["Ф-Центр"] == "46060"
    assert filters["Позитроника"] == "arrFilter_121681_2580419962"
    assert filters["НИКС"] == "5070Ti"


def test_get_source_filter_returns_value_from_file(tmp_path):
    path = tmp_path / "target.json"
    path.write_text(json.dumps({"source_filters": {"TestShop": "my-gpu"}}), encoding="utf-8")
    assert get_source_filter("TestShop", path) == "my-gpu"


def test_get_source_filter_returns_empty_for_missing_source(tmp_path):
    path = tmp_path / "target.json"
    path.write_text(json.dumps({"source_filters": {}}), encoding="utf-8")
    assert get_source_filter("XCOM-SHOP", path) == ""


def test_get_source_filter_falls_back_to_default_when_file_absent(tmp_path):
    assert get_source_filter("XCOM-SHOP", tmp_path / "absent.json") == "nvidia-geforce-rtx-5070-ti"


def test_source_filter_urls_are_byte_for_byte_identical():
    """Verify that all 5 catalog URLs match the original hard-coded values."""
    from parsers import xcom_shop, kns, fcenter, positronica, nix

    assert xcom_shop.CATALOG_URL == (
        "https://www.xcom-shop.ru/catalog/komplektyyuschie_dlya_pk_i_noytbykov/"
        "videokarty/filter/graficheskiy-processor=nvidia-geforce-rtx-5070-ti/"
    )
    assert kns.CATALOG_URL == (
        "https://www.kns.ru/catalog/komplektuyuschie/videokarty/"
        "_graficheskij-protsessor_nvidia-geforce-rtx-5070-ti/"
    )
    assert fcenter.CATALOG_URL == "https://fcenter.ru/product/type/7?param=46060"
    assert positronica.CATALOG_URL == (
        "https://www.positronica.ru/catalog/videokarty/"
        "?set_filter=y&arrFilter_121681_2580419962=Y"
    )
    assert nix._PRODUCT_RE is not None
    assert "5070Ti" in nix._PRODUCT_RE.pattern


def _make_not_configured_result():
    return {
        "offers": [], "blocked": False, "block_reason": None,
        "warnings": ["Источник не настроен для данного товара"], "errors": 0,
    }


def test_xcom_skips_when_filter_empty(monkeypatch):
    from parsers import xcom_shop
    monkeypatch.setattr(xcom_shop, "CATALOG_URL", "")
    result = xcom_shop.parse_offers_with_status()
    assert result == _make_not_configured_result()


def test_kns_skips_when_filter_empty(monkeypatch):
    from parsers import kns
    monkeypatch.setattr(kns, "CATALOG_URL", "")
    result = kns.parse_offers_with_status()
    assert result == _make_not_configured_result()


def test_fcenter_skips_when_filter_empty(monkeypatch):
    from parsers import fcenter
    monkeypatch.setattr(fcenter, "CATALOG_URL", "")
    result = fcenter.parse_offers_with_status()
    assert result == _make_not_configured_result()


def test_positronica_skips_when_filter_empty(monkeypatch):
    from parsers import positronica
    monkeypatch.setattr(positronica, "CATALOG_URL", "")
    result = positronica.parse_offers_with_status()
    assert result == _make_not_configured_result()


def test_nix_skips_when_filter_empty(monkeypatch):
    from parsers import nix
    monkeypatch.setattr(nix, "_FILTER", "")
    result = nix.parse_offers_with_status()
    assert result == _make_not_configured_result()
