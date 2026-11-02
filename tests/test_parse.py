"""Parse-layer tests (pure functions) derived from spec AC1, AC4-AC8, AC17, AC19."""

from tests.helpers import make_card, make_page
from web_scraper.parse import (
    find_next_page,
    normalize_text,
    parse_listings,
)

AC1_CARD = """
<article class="listing-card">
  <h2 class="listing-title">  Cozy   Downtown
    Apartment </h2>
  <span class="listing-price">€250,000</span>
  <span class="listing-location">Rivertown, Dockside</span>
  <span class="listing-rooms">3 rooms</span>
  <span class="listing-area">72 m²</span>
  <a class="listing-link" href="/detail/123">View details</a>
</article>
"""


def test_parse_single_valid_card_ac1():
    """AC1 (R5, R6, R7, R11): one card parses to one record with collapsed title."""
    records = parse_listings(AC1_CARD)
    assert records == [
        {
            "title": "Cozy Downtown Apartment",
            "price": "€250,000",
            "location": "Rivertown, Dockside",
            "rooms": "3 rooms",
            "area": "72 m²",
            "detail_url": "/detail/123",
        }
    ]


def test_parse_missing_optional_fields_ac4():
    """AC4 (R11): absent optional selectors yield None values on the record."""
    html = make_card(
        title="No Price Listing",
        location="Hillcrest",
        href="/detail/200",
    )
    records = parse_listings(html)
    assert records == [
        {
            "title": "No Price Listing",
            "price": None,
            "location": "Hillcrest",
            "rooms": None,
            "area": None,
            "detail_url": "/detail/200",
        }
    ]


def test_parse_card_missing_title_yields_empty_title_ac5():
    """AC5 (R7): a card with no title is still returned with title "" (filtering is
    the pipeline's job); both cards are produced in document order."""
    html = make_page(
        [
            make_card(price="€99,000", href="/detail/300"),
            make_card(title="Valid One", href="/detail/301"),
        ]
    )
    records = parse_listings(html)
    assert len(records) == 2
    assert records[0]["title"] == ""
    assert records[0]["detail_url"] == "/detail/300"
    assert records[1]["title"] == "Valid One"


def test_parse_whitespace_only_title_is_empty_ac6():
    """AC6 (R6, R7): a whitespace-only title normalizes to "" (invalid candidate)."""
    html = make_card(title="   ", href="/detail/1")
    records = parse_listings(html)
    assert records[0]["title"] == ""


def test_parse_missing_link_detail_url_is_none_ac8():
    """AC8 (R9): cards with no listing-link have detail_url None."""
    html = make_page(
        [
            make_card(title="X"),
            make_card(title="Y"),
        ]
    )
    records = parse_listings(html)
    assert [r["detail_url"] for r in records] == [None, None]
    assert [r["title"] for r in records] == ["X", "Y"]


def test_parse_empty_and_whitespace_href_detail_url_is_none_ac17():
    """AC17 (2.2, R9): empty or whitespace-only href yields detail_url None."""
    html = make_page(
        [
            make_card(title="P", href="  "),
            make_card(title="Q", href=""),
        ]
    )
    records = parse_listings(html)
    assert [r["detail_url"] for r in records] == [None, None]
    assert [r["title"] for r in records] == ["P", "Q"]


def test_parse_empty_page_has_no_cards_ac11():
    """AC11/R12: a page with no listing-card produces zero records."""
    assert parse_listings(make_page([])) == []


def test_normalize_collapses_internal_whitespace_ac1():
    """AC1 (R6): runs of spaces/newlines/indentation collapse to single spaces."""
    assert normalize_text("  Cozy   Downtown\n    Apartment ") == "Cozy Downtown Apartment"


def test_normalize_nbsp_and_mixed_whitespace_ac19():
    """AC19 (R6, F1.5): NBSP (U+00A0) is treated as whitespace; trimmed and collapsed."""
    assert normalize_text("\u00a0Cozy\u00a0\u00a0Flat\u00a0") == "Cozy Flat"


def test_parse_title_nbsp_collapse_ac19():
    """AC19 (R6): &nbsp; entities decode to U+00A0 and collapse to a single space."""
    html = make_card(
        title="&nbsp;Cozy&nbsp;&nbsp;Flat&nbsp;",
        href="/detail/1",
    )
    records = parse_listings(html)
    assert records[0]["title"] == "Cozy Flat"


def test_find_next_page_returns_raw_href_ac9():
    """AC9 (R3): find_next_page returns the raw pagination-next href."""
    html = make_page([make_card(title="A", href="/d/1")], next_href="page2.html")
    assert find_next_page(html) == "page2.html"


def test_find_next_page_none_when_absent_ac10():
    """AC10 (R3, R13): no pagination-next element means the page is the last one."""
    html = make_page([make_card(title="A", href="/d/1")], next_href=None)
    assert find_next_page(html) is None


def test_parse_nested_card_counts_only_top_level_ac_section_2_2():
    """Section 2.2 / non-goals: a listing-card nested inside another is not a
    separate card; only the top-level card is produced."""
    html = (
        '<main class="listings">'
        '<article class="listing-card">'
        '<h2 class="listing-title">Outer</h2>'
        '<a class="listing-link" href="/detail/1">View</a>'
        '<article class="listing-card">'
        '<h2 class="listing-title">Inner</h2>'
        "</article>"
        "</article>"
        "</main>"
    )
    records = parse_listings(html)
    assert len(records) == 1
    assert records[0]["title"] == "Outer"
