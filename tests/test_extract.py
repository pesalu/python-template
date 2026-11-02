"""Tests for the raw embedded-JSON capture command (web_scraper.extractcli).

All data is synthetic and generic; no real site names, keys, or URLs are used.
"""

import json

import pytest

from web_scraper import extractcli
from web_scraper.extractcli import main as extract_main
from web_scraper.initial_state import (
    InitialStateError,
    extract_initial_state,
    extract_raw,
    select_node,
)

SAMPLE_STATE = {
    "data": {
        "results": {
            "items": [
                {"ref": "a1", "street": "1 Example Street", "cost": 100},
                {"ref": "b2", "street": "2 Sample Road", "cost": 200},
            ]
        }
    }
}


def _page(state: dict) -> str:
    return (
        "<!DOCTYPE html><html><body><script>"
        f"window.__INITIAL_STATE__ = {json.dumps(state, ensure_ascii=False)};"
        "</script></body></html>"
    )


def test_extract_raw_returns_whole_state_when_no_path():
    assert extract_raw(_page(SAMPLE_STATE)) == SAMPLE_STATE


def test_extract_raw_returns_node_at_path():
    node = extract_raw(_page(SAMPLE_STATE), "data.results.items")
    assert node == SAMPLE_STATE["data"]["results"]["items"]


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


def test_select_node_bad_path_raises():
    with pytest.raises(InitialStateError):
        select_node(SAMPLE_STATE, "data.missing.items")


def test_cli_writes_whole_state_as_pretty_json(tmp_path):
    html_file = tmp_path / "page1.html"
    html_file.write_text(_page(SAMPLE_STATE), encoding="utf-8")
    out = tmp_path / "raw.json"

    code = extract_main(["--input", str(html_file), "--output", str(out)])

    assert code == 0
    # Raw, unmapped data is preserved exactly (round-trips to the original state).
    assert json.loads(out.read_text(encoding="utf-8")) == SAMPLE_STATE


def test_cli_narrows_to_state_path(tmp_path):
    html_file = tmp_path / "page1.html"
    html_file.write_text(_page(SAMPLE_STATE), encoding="utf-8")
    out = tmp_path / "items.json"

    code = extract_main(
        ["--input", str(html_file), "--output", str(out), "--state-path", "data.results.items"]
    )

    assert code == 0
    assert json.loads(out.read_text(encoding="utf-8")) == SAMPLE_STATE["data"]["results"]["items"]


def test_cli_jsonl_writes_one_object_per_line(tmp_path):
    html_file = tmp_path / "page1.html"
    html_file.write_text(_page(SAMPLE_STATE), encoding="utf-8")
    out = tmp_path / "items.jsonl"

    code = extract_main(
        [
            "--input",
            str(html_file),
            "--output",
            str(out),
            "--state-path",
            "data.results.items",
            "--jsonl",
        ]
    )

    assert code == 0
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"ref": "a1", "street": "1 Example Street", "cost": 100}


def test_cli_missing_input_returns_1(tmp_path):
    code = extract_main(
        ["--input", str(tmp_path / "nope.html"), "--output", str(tmp_path / "o.json")]
    )
    assert code == 1


def test_cli_missing_marker_returns_1(tmp_path):
    bad = tmp_path / "bad.html"
    bad.write_text("<html>no state</html>", encoding="utf-8")
    code = extract_main(["--input", str(bad), "--output", str(tmp_path / "o.json")])
    assert code == 1


def test_cli_bad_path_returns_1(tmp_path):
    html_file = tmp_path / "page1.html"
    html_file.write_text(_page(SAMPLE_STATE), encoding="utf-8")
    code = extract_main(
        [
            "--input",
            str(html_file),
            "--output",
            str(tmp_path / "o.json"),
            "--state-path",
            "data.missing",
        ]
    )
    assert code == 1


def test_cli_write_failure_leaves_no_tmp(monkeypatch, tmp_path):
    html_file = tmp_path / "page1.html"
    html_file.write_text(_page(SAMPLE_STATE), encoding="utf-8")
    out = tmp_path / "raw.json"

    def boom(*args, **kwargs):
        raise OSError("disk full")

    # The temp file is written, then os.replace fails; rollback must remove it.
    monkeypatch.setattr(extractcli.os, "replace", boom)

    code = extract_main(["--input", str(html_file), "--output", str(out)])

    assert code == 1
    assert not out.exists()
    assert list(tmp_path.glob("*.tmp")) == []
