"""Non-functional requirement tests (NFR1-NFR3): hard tests over a 10x50 on-disk fixture.

The measured operation is a full scrape (fetch + parse + record-build + dedup +
serialize to JSONL+CSV) over 10 on-disk HTML files of 50 cards each (500 records),
run through ``main`` so real file reads, pagination, and serialization happen. Only
the tmp_path fixture materialization (the ``nfr_fixture`` fixture) is excluded.
"""

import socket
import time
import tracemalloc

from web_scraper.main import main


def _run_scrape(input_path, output_dir):
    return main(["--input", str(input_path), "--output-dir", str(output_dir)])


def test_nfr1_throughput_under_5s(nfr_fixture, tmp_path):
    """NFR1: the full scrape over the on-disk fixture completes in <= 5.0 s."""
    out = tmp_path / "out"
    start = time.perf_counter()
    code = _run_scrape(nfr_fixture, out)
    elapsed = time.perf_counter() - start
    assert code == 0
    assert elapsed <= 5.0


def test_nfr2_no_network_sockets(nfr_fixture, tmp_path, monkeypatch):
    """NFR2: zero network sockets are opened during a full scrape."""
    out = tmp_path / "out"

    def _no_socket(*args, **kwargs):
        raise AssertionError("network socket created during scrape")

    monkeypatch.setattr(socket, "socket", _no_socket)
    code = _run_scrape(nfr_fixture, out)
    assert code == 0
    assert (out / "listings.jsonl").exists()


def test_nfr3_peak_memory_under_64mb(nfr_fixture, tmp_path):
    """NFR3: tracemalloc peak during the full scrape is <= 64 MiB (67,108,864 bytes)."""
    out = tmp_path / "out"
    tracemalloc.start()
    try:
        code = _run_scrape(nfr_fixture, out)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert code == 0
    assert peak <= 67_108_864
