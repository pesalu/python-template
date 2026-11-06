"""Tests for the one-shot container job (web-scraper-run)."""

import json
from datetime import UTC, datetime
from urllib.error import URLError

import pytest

from web_scraper import download
from web_scraper.run import main

NOW = datetime(2026, 11, 6, 17, 7, 3, tzinfo=UTC)
STAMP = "20261106T170703Z"

PAGE = (
    '<html><script>window.__INITIAL_STATE__ = {"data": {"items": [{"ref": "a1"}, {"ref": "a2"}]}};'
    "</script></html>"
)


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(download, "fetch", lambda url, user_agent, timeout: PAGE)
    return tmp_path


def test_writes_page_and_raw_json(workdir):
    assert main([], {"SCRAPER_URL": "https://example.com/x"}, NOW) == 0

    assert (workdir / f"page1_{STAMP}.html").read_text(encoding="utf-8") == PAGE
    assert json.loads((workdir / f"raw_{STAMP}.json").read_text(encoding="utf-8")) == {
        "data": {"items": [{"ref": "a1"}, {"ref": "a2"}]}
    }
    assert not (workdir / f"items_{STAMP}.jsonl").exists()


def test_state_path_also_writes_items_jsonl(workdir):
    env = {"SCRAPER_URL": "https://example.com/x", "SCRAPER_STATE_PATH": "data.items"}

    assert main([], env, NOW) == 0

    lines = (workdir / f"items_{STAMP}.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [{"ref": "a1"}, {"ref": "a2"}]


def test_missing_url_exits_2(workdir, capsys):
    assert main([], {}) == 2

    assert "SCRAPER_URL" in capsys.readouterr().err
    assert list(workdir.iterdir()) == []


def test_fetch_failure_stops_the_job(workdir, monkeypatch, capsys):
    def fail(url, user_agent, timeout):
        raise URLError("boom")

    monkeypatch.setattr(download, "fetch", fail)

    assert main([], {"SCRAPER_URL": "https://example.com/x"}) == 1

    assert "error: cannot fetch" in capsys.readouterr().err
    assert list(workdir.iterdir()) == []


def test_bad_state_path_fails_after_raw_json(workdir, capsys):
    env = {"SCRAPER_URL": "https://example.com/x", "SCRAPER_STATE_PATH": "no.such.path"}

    assert main([], env, NOW) == 1

    assert "path not found" in capsys.readouterr().err
    assert (workdir / f"raw_{STAMP}.json").exists()
    assert not (workdir / f"items_{STAMP}.jsonl").exists()


def test_runs_do_not_overwrite_each_other(workdir):
    env = {"SCRAPER_URL": "https://example.com/x", "SCRAPER_STATE_PATH": "data.items"}
    later = datetime(2026, 11, 6, 17, 7, 4, tzinfo=UTC)

    assert main([], env, NOW) == 0
    assert main([], env, later) == 0

    assert len(list(workdir.glob("raw_*.json"))) == 2
    assert len(list(workdir.glob("items_*.jsonl"))) == 2
    assert len(list(workdir.glob("page1_*.html"))) == 2


def test_default_timestamp_is_utc_and_formatted(workdir):
    assert main([], {"SCRAPER_URL": "https://example.com/x"}) == 0

    (raw,) = workdir.glob("raw_*.json")
    assert len(raw.stem) == len("raw_") + len(STAMP)
    assert raw.stem.endswith("Z")
