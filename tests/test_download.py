"""Tests for the stage-1 download command (web_scraper.download).

Network is always mocked; no real HTTP calls are made.
"""

import pytest

import web_scraper.download as download
from tests.helpers import make_card, make_page
from web_scraper.main import main as parse_main


class _FakeResponse:
    """Minimal stand-in for the object returned by urllib's urlopen."""

    def __init__(self, body: bytes, charset: str | None = "utf-8") -> None:
        self._body = body
        self.headers = _FakeHeaders(charset)

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class _FakeHeaders:
    def __init__(self, charset: str | None) -> None:
        self._charset = charset

    def get_content_charset(self) -> str | None:
        return self._charset


def test_fetch_decodes_body_with_declared_charset(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["ua"] = request.get_header("User-agent")
        captured["timeout"] = timeout
        return _FakeResponse("<html>€</html>".encode())

    monkeypatch.setattr(download, "urlopen", fake_urlopen)
    html = download.fetch("https://example.com/x", user_agent="test-agent", timeout=5.0)

    assert html == "<html>€</html>"
    assert captured == {"url": "https://example.com/x", "ua": "test-agent", "timeout": 5.0}


def test_main_writes_fetched_html_to_file(monkeypatch, tmp_path):
    monkeypatch.setattr(download, "fetch", lambda url, user_agent, timeout: "<html>ok</html>")
    out = tmp_path / "page1.html"

    code = download.main(["--url", "https://example.com", "--output", str(out)])

    assert code == 0
    assert out.read_text(encoding="utf-8") == "<html>ok</html>"


def test_main_rejects_non_http_scheme(monkeypatch, tmp_path):
    # SSRF/local-file guard: file:// (and other schemes) are rejected before any fetch.
    called = {"fetched": False}
    monkeypatch.setattr(
        download, "fetch", lambda *a, **k: called.__setitem__("fetched", True) or ""
    )
    out = tmp_path / "out.html"

    with pytest.raises(SystemExit) as excinfo:
        download.main(["--url", "file:///etc/passwd", "--output", str(out)])

    assert excinfo.value.code == 2
    assert called["fetched"] is False
    assert not out.exists()


def test_main_returns_1_on_fetch_failure(monkeypatch, tmp_path):
    def boom(url, user_agent, timeout):
        raise download.URLError("boom")

    monkeypatch.setattr(download, "fetch", boom)
    out = tmp_path / "out.html"

    code = download.main(["--url", "https://example.com", "--output", str(out)])

    assert code == 1
    assert not out.exists()


def test_two_stage_fetch_then_parse(monkeypatch, tmp_path):
    """Stage 1 saves HTML; stage 2 parses that file into JSONL + CSV."""
    page = make_page(
        [
            make_card(title="Flat A", price="€100,000", href="/d/1"),
            make_card(title="Flat B", price="€200,000", href="/d/2"),
        ]
    )
    monkeypatch.setattr(download, "fetch", lambda url, user_agent, timeout: page)

    html_file = tmp_path / "page1.html"
    assert download.main(["--url", "https://example.com", "--output", str(html_file)]) == 0

    out_dir = tmp_path / "out"
    assert parse_main(["--input", str(html_file), "--output-dir", str(out_dir)]) == 0

    lines = (out_dir / "listings.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert '"title": "Flat A"' in lines[0]
    assert '"title": "Flat B"' in lines[1]
    assert (out_dir / "listings.csv").read_text(encoding="utf-8").startswith(
        "title,price,location,rooms,area,detail_url\n"
    )


def test_main_handles_missing_charset(monkeypatch, tmp_path):
    monkeypatch.setattr(
        download, "urlopen", lambda request, timeout: _FakeResponse(b"<html>x</html>", charset=None)
    )
    out = tmp_path / "page.html"

    code = download.main(["--url", "http://example.com", "--output", str(out)])

    assert code == 0
    assert out.read_text(encoding="utf-8") == "<html>x</html>"
