"""Pipeline (scrape) tests for counting / dedup / pagination: AC5, AC7-AC11, AC16, AC17, AC20."""

from python_template.scraper.pipeline import scrape
from tests.helpers import make_card, make_page, write_pages


def test_scrape_skips_missing_title_counts_ac5(tmp_path):
    """AC5 (R7, R8): invalid (title-less) card skipped and counted."""
    write_pages(
        tmp_path,
        [
            [
                make_card(price="€99,000", href="/detail/300"),
                make_card(title="Valid One", href="/detail/301"),
            ]
        ],
    )
    result = scrape(str(tmp_path / "page1.html"), 10)
    assert result.cards == 2
    assert result.written == 1
    assert result.skipped_invalid == 1
    assert result.skipped_duplicate == 0
    assert [r["title"] for r in result.records] == ["Valid One"]


def test_scrape_dedup_by_detail_url_across_pages_ac7(tmp_path):
    """AC7 (R9, R10): duplicate detail_url across pages -> later copy skipped."""
    write_pages(
        tmp_path,
        [
            [make_card(title="A", href="/detail/400")],
            [make_card(title="A-again", href="/detail/400")],
        ],
    )
    result = scrape(str(tmp_path / "page1.html"), 10)
    assert result.written == 1
    assert result.skipped_duplicate == 1
    assert [r["title"] for r in result.records] == ["A"]


def test_scrape_null_detail_url_never_deduped_ac8(tmp_path):
    """AC8 (R9): two null-detail_url records are both kept."""
    write_pages(tmp_path, [[make_card(title="X"), make_card(title="Y")]])
    result = scrape(str(tmp_path / "page1.html"), 10)
    assert result.written == 2
    assert result.skipped_duplicate == 0
    assert [r["detail_url"] for r in result.records] == [None, None]


def test_scrape_follows_next_respects_max_pages_ac9(tmp_path):
    """AC9 (R3, R4): --max-pages 2 processes only pages 1 and 2."""
    write_pages(
        tmp_path,
        [
            [make_card(title="A", href="/d/1")],
            [make_card(title="B", href="/d/2")],
            [make_card(title="C", href="/d/3")],
        ],
    )
    result = scrape(str(tmp_path / "page1.html"), 2)
    assert result.pages == 2
    assert result.cards == 2
    assert result.written == 2


def test_scrape_end_of_pagination_no_limit_ac10(tmp_path):
    """AC10 (R3, R13): with max-pages 10 all three linked pages are processed."""
    write_pages(
        tmp_path,
        [
            [make_card(title="A", href="/d/1")],
            [make_card(title="B", href="/d/2")],
            [make_card(title="C", href="/d/3")],
        ],
    )
    result = scrape(str(tmp_path / "page1.html"), 10)
    assert result.pages == 3
    assert result.written == 3


def test_scrape_empty_page_counted_but_no_records_ac11(tmp_path):
    """AC11 (R12): an empty page contributes zero records but is counted."""
    write_pages(
        tmp_path,
        [
            [],
            [make_card(title="Only", href="/d/1")],
        ],
    )
    result = scrape(str(tmp_path / "page1.html"), 10)
    assert result.pages == 2
    assert result.cards == 1
    assert result.written == 1


def test_scrape_missing_next_page_stops_gracefully_ac16(tmp_path):
    """AC16 (R13a): a next-page href pointing to a missing file stops gracefully."""
    # page1 links to page2.html which is never written.
    page1 = make_card(title="A", href="/detail/900")
    (tmp_path / "page1.html").write_text(
        make_page([page1], next_href="page2.html"), encoding="utf-8"
    )
    result = scrape(str(tmp_path / "page1.html"), 10)
    assert result.pages == 1
    assert result.cards == 1
    assert result.written == 1
    assert result.skipped_invalid == 0
    assert result.skipped_duplicate == 0


def test_scrape_non_utf8_next_page_stops_gracefully_ac16(tmp_path):
    """AC16 (R13a): a NEXT page with invalid UTF-8 bytes stops gracefully (exit-0 semantics).

    page1 has one valid card and links to page2.html, which is written as raw
    non-UTF-8 bytes. scrape must not raise; it stops after page 1 and keeps the
    page-1 record, so the CLI would exit 0.
    """
    page1 = make_card(title="A", href="/detail/901")
    (tmp_path / "page1.html").write_text(
        make_page([page1], next_href="page2.html"), encoding="utf-8"
    )
    (tmp_path / "page2.html").write_bytes(b"\xff\xfe\x00not utf-8")
    result = scrape(str(tmp_path / "page1.html"), 10)
    assert result.pages == 1
    assert result.cards == 1
    assert result.written == 1
    assert [r["title"] for r in result.records] == ["A"]


def test_scrape_whitespace_and_empty_href_null_no_dedup_ac17(tmp_path):
    """AC17 (2.2, R9): whitespace-only and empty href -> null detail_url, kept, no dedup."""
    write_pages(
        tmp_path,
        [
            [
                make_card(title="P", href="  "),
                make_card(title="Q", href=""),
            ]
        ],
    )
    result = scrape(str(tmp_path / "page1.html"), 10)
    assert result.written == 2
    assert result.skipped_duplicate == 0
    assert [r["detail_url"] for r in result.records] == [None, None]


def test_scrape_relative_href_with_query_fragment_resolves_ac20(tmp_path):
    """AC20 (R3): next href with ?query/#fragment resolves under a subdirectory."""
    base = tmp_path / "a"
    sub = base / "sub"
    sub.mkdir(parents=True)
    (base / "page1.html").write_text(
        make_page([make_card(title="A", href="/d/1")], next_href="sub/page2.html?ref=1#top"),
        encoding="utf-8",
    )
    (sub / "page2.html").write_text(
        make_page([make_card(title="B", href="/d/2")], next_href=None),
        encoding="utf-8",
    )
    result = scrape(str(base / "page1.html"), 10)
    assert result.pages == 2
    assert result.written == 2


def test_scrape_full_url_next_href_stops_gracefully_ac20(tmp_path):
    """AC20 (R3 step 2, R13a): a full-URL next href stops pagination after page 1."""
    (tmp_path / "page1.html").write_text(
        make_page(
            [make_card(title="A", href="/d/1")],
            next_href="https://example.com/page2",
        ),
        encoding="utf-8",
    )
    result = scrape(str(tmp_path / "page1.html"), 10)
    assert result.pages == 1
    assert result.written == 1
