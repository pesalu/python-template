from dataclasses import dataclass, field

from web_scraper.fetch import read_page, resolve_next_path
from web_scraper.parse import find_next_page, normalize_text, parse_listings

_FIELDS = ["title", "price", "location", "rooms", "area", "detail_url"]


class InputReadError(Exception):
    """Raised when the first (page-1) input file cannot be read."""


@dataclass
class ScrapeResult:
    records: list[dict[str, str | None]] = field(default_factory=list)
    pages: int = 0
    cards: int = 0
    written: int = 0
    skipped_invalid: int = 0
    skipped_duplicate: int = 0


def scrape(input_path: str, max_pages: int) -> ScrapeResult:
    result = ScrapeResult()
    current_path = input_path
    html = read_page(current_path)
    if html is None:
        raise InputReadError(input_path)

    seen: set[str] = set()
    while result.pages < max_pages:
        result.pages += 1
        for candidate in parse_listings(html):
            result.cards += 1
            title = normalize_text(candidate["title"] or "")
            if title == "":
                result.skipped_invalid += 1
                continue
            detail_url = candidate["detail_url"]
            if detail_url is not None and detail_url in seen:
                result.skipped_duplicate += 1
                continue
            if detail_url is not None:
                seen.add(detail_url)
            record: dict[str, str | None] = {key: candidate.get(key) for key in _FIELDS}
            result.records.append(record)
            result.written += 1

        href = find_next_page(html)
        if href is None:
            break
        next_path = resolve_next_path(current_path, href)
        if next_path is None:
            break
        next_html = read_page(next_path)
        if next_html is None:
            break
        current_path = next_path
        html = next_html

    return result
