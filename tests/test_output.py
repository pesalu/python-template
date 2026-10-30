"""Output-layer tests (JSONL/CSV serialization) from spec AC2, AC3, AC4, AC12."""

from tests.helpers import (
    CANONICAL_RECORDS,
    EXPECTED_CSV,
    EXPECTED_CSV_HEADER_ONLY,
    EXPECTED_JSONL,
)
from web_scraper.output import write_csv, write_jsonl


def test_write_jsonl_two_records_ac2(tmp_path):
    """AC2 (section 3.4): two LF-terminated UTF-8 lines, last line LF-terminated,
    non-ASCII preserved (€, ²)."""
    path = tmp_path / "listings.jsonl"
    write_jsonl(CANONICAL_RECORDS, str(path))
    assert path.read_bytes() == EXPECTED_JSONL


def test_write_csv_two_records_minimal_quoting_ac3(tmp_path):
    """AC3 (section 3.5): header + two rows, commas quoted, LF terminators."""
    path = tmp_path / "listings.csv"
    write_csv(CANONICAL_RECORDS, str(path))
    assert path.read_bytes() == EXPECTED_CSV


def test_write_missing_optional_null_vs_empty_ac4(tmp_path):
    """AC4 (R11): null in JSONL, empty field in CSV for absent optional fields."""
    record = {
        "title": "No Price Listing",
        "price": None,
        "location": "Tampere",
        "rooms": None,
        "area": None,
        "detail_url": "/detail/200",
    }
    jsonl_path = tmp_path / "out.jsonl"
    csv_path = tmp_path / "out.csv"
    write_jsonl([record], str(jsonl_path))
    write_csv([record], str(csv_path))
    expected_jsonl = (
        b'{"title": "No Price Listing", "price": null, '
        b'"location": "Tampere", "rooms": null, '
        b'"area": null, "detail_url": "/detail/200"}\n'
    )
    expected_csv = (
        b"title,price,location,rooms,area,detail_url\n"
        b"No Price Listing,,Tampere,,,/detail/200\n"
    )
    assert jsonl_path.read_bytes() == expected_jsonl
    assert csv_path.read_bytes() == expected_csv


def test_write_zero_records_jsonl_empty_csv_header_only_ac12(tmp_path):
    """AC12 (3.1, 3.5): zero records -> empty JSONL and header-only 43-byte CSV."""
    jsonl_path = tmp_path / "listings.jsonl"
    csv_path = tmp_path / "listings.csv"
    write_jsonl([], str(jsonl_path))
    write_csv([], str(csv_path))
    assert jsonl_path.read_bytes() == b""
    csv_bytes = csv_path.read_bytes()
    assert csv_bytes == EXPECTED_CSV_HEADER_ONLY
    assert len(csv_bytes) == 43
