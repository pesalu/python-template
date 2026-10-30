"""Shared fixtures for the scraper test-suite."""

import pytest

from tests.helpers import make_card, write_pages
from web_scraper.main import main


@pytest.fixture
def run_main():
    """Call ``main(argv)`` and return the process-visible exit code.

    argparse usage errors raise ``SystemExit(2)``; the implementation may also
    choose to return the code directly. This helper normalizes both so tests can
    assert the integer exit code regardless of which contract ``main`` uses.
    """

    def _run(argv):
        try:
            return main(argv)
        except SystemExit as exc:
            return 0 if exc.code is None else exc.code

    return _run


@pytest.fixture
def nfr_fixture(tmp_path):
    """Materialize the NFR fixture: 10 on-disk pages x 50 cards = 500 records.

    Every card has a unique title and a unique ``detail_url`` so none are
    dropped as invalid or duplicate; the 10 files are linked by
    ``pagination-next`` hrefs. Returns the path to page 1.
    """
    pages = []
    for page in range(1, 11):
        cards = [
            make_card(
                title=f"Listing {page}-{i}",
                price=f"€{page}{i:02d},000",
                location="Helsinki",
                rooms="3 rooms",
                area="72 m²",
                href=f"/detail/{page}_{i}",
            )
            for i in range(50)
        ]
        pages.append(cards)
    paths = write_pages(tmp_path, pages)
    return paths[0]
