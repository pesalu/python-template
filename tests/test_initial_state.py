"""Tests for the __INITIAL_STATE__ JSON-extraction path (web_scraper.initial_state).

All data is synthetic and generic; no real site names, keys, or URLs are used.
"""

import json

import pytest

from web_scraper import jsoncli
from web_scraper.initial_state import (
    InitialStateError,
    Profile,
    extract_initial_state,
    map_listings,
    parse_initial_state,
    select_listings,
)
from web_scraper.jsoncli import load_profile
from web_scraper.jsoncli import main as json_main

# A neutral, made-up state shape and matching profile.
SAMPLE_STATE = {
    "data": {
        "results": {
            "items": [
                {
                    "ref": "a1",
                    "street": "1 Example Street",
                    "city": "Testville",
                    "cost": 47120.47,
                    "rooms": "2 rooms",
                    "size": 68.5,
                },
                {
                    "ref": "b2",
                    "street": "2 Sample Road",
                    "city": "Mockton",
                    "cost": 144990,
                    "rooms": "1 room",
                    "size": 22,
                },
            ]
        }
    }
}

SAMPLE_PROFILE = Profile(
    state_path="data.results.items",
    fields={
        "title": "street",
        "price": "cost",
        "location": "city",
        "rooms": "rooms",
        "area": "size",
    },
    detail_url_template="https://example.com/listing/{value}",
    detail_url_field="ref",
)


def _page(state: dict) -> str:
    return (
        "<!DOCTYPE html><html><body><script>"
        f"window.__INITIAL_STATE__ = {json.dumps(state, ensure_ascii=False)};"
        "</script></body></html>"
    )


def _write_profile(tmp_path, profile: Profile) -> str:
    path = tmp_path / "profile.json"
    path.write_text(
        json.dumps(
            {
                "state_path": profile.state_path,
                "fields": profile.fields,
                "detail_url_template": profile.detail_url_template,
                "detail_url_field": profile.detail_url_field,
            }
        ),
        encoding="utf-8",
    )
    return str(path)


def test_extract_handles_bare_undefined_outside_strings():
    html = '<script>window.__INITIAL_STATE__ = {"a": undefined, "b": 1};</script>'
    assert extract_initial_state(html) == {"a": None, "b": 1}


def test_extract_preserves_undefined_inside_string_values():
    # The word "undefined" inside a string value must NOT be rewritten to null.
    html = (
        "<script>window.__INITIAL_STATE__ = "
        '{"note": "value is undefined here", "x": undefined};</script>'
    )
    assert extract_initial_state(html) == {"note": "value is undefined here", "x": None}


def test_extract_stops_at_balanced_brace_ignoring_trailing_script():
    html = (
        '<script>window.__INITIAL_STATE__ = {"a": {"b": 2}};'
        'window.OTHER = {"not": "mine"};</script>'
    )
    assert extract_initial_state(html) == {"a": {"b": 2}}


def test_extract_missing_marker_raises():
    with pytest.raises(InitialStateError):
        extract_initial_state("<html>no state here</html>")


def test_select_listings_navigates_dotted_path():
    arr = select_listings(SAMPLE_STATE, SAMPLE_PROFILE.state_path)
    assert isinstance(arr, list) and len(arr) == 2


def test_select_listings_bad_path_raises():
    with pytest.raises(InitialStateError):
        select_listings(SAMPLE_STATE, "data.missing.items")


def test_map_listings_applies_profile_and_builds_detail_url():
    items = select_listings(SAMPLE_STATE, SAMPLE_PROFILE.state_path)
    records = map_listings(items, SAMPLE_PROFILE)
    assert records[0] == {
        "title": "1 Example Street",
        "price": "47120.47",
        "location": "Testville",
        "rooms": "2 rooms",
        "area": "68.5",
        "detail_url": "https://example.com/listing/a1",
    }
    assert records[1]["detail_url"] == "https://example.com/listing/b2"
    assert records[1]["price"] == "144990"


def test_map_listings_missing_field_is_null_and_null_detail_url():
    profile = Profile(
        state_path="x",
        fields={"title": "street", "price": "cost"},
        detail_url_template="https://example.com/{value}",
        detail_url_field="ref",
    )
    records = map_listings([{"street": "Only Street"}], profile)
    assert records[0] == {"title": "Only Street", "price": None, "detail_url": None}


def test_parse_initial_state_end_to_end_records():
    records = parse_initial_state(_page(SAMPLE_STATE), SAMPLE_PROFILE)
    assert [r["title"] for r in records] == ["1 Example Street", "2 Sample Road"]


def test_cli_writes_jsonl_and_csv(tmp_path):
    html_file = tmp_path / "page1.html"
    html_file.write_text(_page(SAMPLE_STATE), encoding="utf-8")
    out_dir = tmp_path / "out"
    profile = _write_profile(tmp_path, SAMPLE_PROFILE)

    code = json_main(
        ["--input", str(html_file), "--output-dir", str(out_dir), "--profile", profile]
    )

    assert code == 0
    lines = (out_dir / "listings.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert '"detail_url": "https://example.com/listing/a1"' in lines[0]
    csv_text = (out_dir / "listings.csv").read_text(encoding="utf-8")
    assert csv_text.startswith("title,price,location,rooms,area,detail_url\n")


def test_cli_requires_profile(tmp_path):
    html_file = tmp_path / "page1.html"
    html_file.write_text(_page(SAMPLE_STATE), encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        json_main(["--input", str(html_file), "--output-dir", str(tmp_path / "o")])
    assert excinfo.value.code == 2


def test_cli_missing_input_returns_1(tmp_path):
    profile = _write_profile(tmp_path, SAMPLE_PROFILE)
    code = json_main(
        [
            "--input",
            str(tmp_path / "nope.html"),
            "--output-dir",
            str(tmp_path / "o"),
            "--profile",
            profile,
        ]
    )
    assert code == 1


def test_cli_missing_state_returns_1(tmp_path):
    bad = tmp_path / "bad.html"
    bad.write_text("<html>no state</html>", encoding="utf-8")
    profile = _write_profile(tmp_path, SAMPLE_PROFILE)
    code = json_main(
        ["--input", str(bad), "--output-dir", str(tmp_path / "o"), "--profile", profile]
    )
    assert code == 1


def test_cli_bad_profile_returns_1(tmp_path):
    html_file = tmp_path / "page1.html"
    html_file.write_text(_page(SAMPLE_STATE), encoding="utf-8")
    bad_profile = tmp_path / "bad.json"
    bad_profile.write_text('{"no_state_path": true}', encoding="utf-8")
    code = json_main(
        [
            "--input",
            str(html_file),
            "--output-dir",
            str(tmp_path / "o"),
            "--profile",
            str(bad_profile),
        ]
    )
    assert code == 1


def test_cli_invalid_output_name_exits_2(tmp_path):
    html_file = tmp_path / "page1.html"
    html_file.write_text(_page(SAMPLE_STATE), encoding="utf-8")
    profile = _write_profile(tmp_path, SAMPLE_PROFILE)
    with pytest.raises(SystemExit) as excinfo:
        json_main(
            [
                "--input",
                str(html_file),
                "--output-dir",
                str(tmp_path),
                "--profile",
                profile,
                "--jsonl-name",
                "a/b.jsonl",
            ]
        )
    assert excinfo.value.code == 2


def test_cli_atomic_write_failure_leaves_no_output(monkeypatch, tmp_path):
    html_file = tmp_path / "page1.html"
    html_file.write_text(_page(SAMPLE_STATE), encoding="utf-8")
    out_dir = tmp_path / "out"
    profile = _write_profile(tmp_path, SAMPLE_PROFILE)

    monkeypatch.setattr(
        jsoncli, "write_csv", lambda *a, **k: (_ for _ in ()).throw(OSError("disk"))
    )

    code = json_main(
        ["--input", str(html_file), "--output-dir", str(out_dir), "--profile", profile]
    )

    assert code == 1
    assert not (out_dir / "listings.jsonl").exists()
    assert not (out_dir / "listings.csv").exists()
    assert list(out_dir.glob("*.tmp")) == []


def test_load_profile_override(tmp_path):
    profile_file = tmp_path / "custom.json"
    profile_file.write_text(
        json.dumps(
            {
                "state_path": "data.items",
                "fields": {"title": "name", "price": "cost"},
                "detail_url_template": "https://example.com/{value}",
                "detail_url_field": "slug",
            }
        ),
        encoding="utf-8",
    )
    profile = load_profile(str(profile_file))
    assert isinstance(profile, Profile)

    state = {"data": {"items": [{"name": "A", "cost": 10, "slug": "a1"}]}}
    records = parse_initial_state(_page(state), profile)
    assert records[0] == {
        "title": "A",
        "price": "10",
        "detail_url": "https://example.com/a1",
    }
