import json
from pathlib import Path

import monitor_5070_ti_v_2 as mon
from parsers.common import build_search_url
from target_config import DEFAULT_TARGET, get_query, load_target


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
