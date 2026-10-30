"""Fetch-layer tests (read_page, resolve_next_path) from spec R2, R3, AC16, AC20."""

import os

from python_template.scraper.fetch import read_page, resolve_next_path


def test_read_page_returns_utf8_content(tmp_path):
    """R2: read_page returns the decoded UTF-8 text of an existing file."""
    path = tmp_path / "p.html"
    path.write_text("<html>café €</html>", encoding="utf-8")
    assert read_page(str(path)) == "<html>café €</html>"


def test_read_page_missing_returns_none_ac16(tmp_path):
    """AC16 (R13a): a missing file yields None (graceful, not an exception)."""
    assert read_page(str(tmp_path / "nope.html")) is None


def test_read_page_non_utf8_returns_none_ac16(tmp_path):
    """AC16 (R13a): a file that is not valid UTF-8 yields None."""
    path = tmp_path / "bad.html"
    path.write_bytes(b"\xff\xfe\x00bad")
    assert read_page(str(path)) is None


def test_resolve_relative_with_query_fragment_ac20():
    """AC20 (R3): strip ?query/#fragment then normpath(join(dir, path))."""
    result = resolve_next_path(
        os.path.join("a", "page1.html"),
        "sub/page2.html?ref=1#top",
    )
    assert result == os.path.normpath(os.path.join("a", "sub/page2.html"))


def test_resolve_full_url_returns_none_ac20():
    """AC20 (R3 step 2): a full URL is a broken reference -> None."""
    assert resolve_next_path("a/page1.html", "https://example.com/page2") is None


def test_resolve_absolute_path_returns_none_ac20():
    """AC20 (R3 step 2): an absolute filesystem path is a broken reference -> None."""
    assert resolve_next_path("a/page1.html", "/detail/page2.html") is None


def test_resolve_empty_after_strip_returns_none_ac20():
    """R3 step 2: an href that is empty after stripping query/fragment -> None."""
    assert resolve_next_path("a/page1.html", "?only=query") is None


def test_resolve_plain_relative_joins_and_normalizes():
    """R3 step 3: a plain relative href is joined to the current page directory."""
    result = resolve_next_path(os.path.join("a", "page1.html"), "page2.html")
    assert result == os.path.normpath(os.path.join("a", "page2.html"))


def test_resolve_strips_query_before_url_check_ac20():
    """R3/AC20: ?query and #fragment are stripped BEFORE the full-URL/absolute check.

    A relative path whose query happens to contain ``://`` or an absolute-looking
    value must still resolve, because stripping precedes the broken-reference
    check; only a genuine full URL or absolute path is rejected.
    """
    base = os.path.join("/base", "page1.html")
    expected = os.path.normpath(os.path.join("/base", "page2.html"))
    assert resolve_next_path(base, "page2.html?x=http://y") == expected
    assert resolve_next_path(base, "page2.html#frag") == expected
    assert resolve_next_path(base, "http://example.com/x") is None
    assert resolve_next_path(base, "/etc/passwd") is None

