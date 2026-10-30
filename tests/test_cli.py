"""CLI tests via main(): AC9, AC12, AC13, AC14, AC15, AC18, AC20.

For argparse usage errors (exit code 2, spec section 6.4) the ``run_main``
fixture normalizes a raised ``SystemExit(2)`` and a returned ``2`` to the same
integer, so these tests assert the process-visible exit code either way.
"""

import os

import pytest

from python_template.main import build_parser, validate_output_name
from tests.helpers import (
    EXPECTED_CSV,
    EXPECTED_CSV_HEADER_ONLY,
    EXPECTED_JSONL,
    canonical_cards,
    make_card,
    make_page,
    write_pages,
)


def _write_single_page(tmp_path, cards, next_href=None):
    (tmp_path / "page1.html").write_text(make_page(cards, next_href), encoding="utf-8")
    return str(tmp_path / "page1.html")


def test_build_parser_returns_argument_parser():
    """R17/6.2: build_parser returns a configured ArgumentParser."""
    import argparse

    parser = build_parser()
    assert isinstance(parser, argparse.ArgumentParser)


def test_cli_zero_records_outputs_ac12(tmp_path, run_main):
    """AC12 (3.1, 3.5): zero records -> empty JSONL, header-only CSV, exit 0."""
    input_path = _write_single_page(tmp_path, [])
    out = tmp_path / "out"
    code = run_main(["--input", input_path, "--output-dir", str(out)])
    assert code == 0
    assert (out / "listings.jsonl").read_bytes() == b""
    assert (out / "listings.csv").read_bytes() == EXPECTED_CSV_HEADER_ONLY
    assert len((out / "listings.csv").read_bytes()) == 43


def test_cli_summary_line_ac12(tmp_path, run_main, capsys):
    """AC12/6.5: summary line reports written=0 for the zero-records run."""
    input_path = _write_single_page(tmp_path, [])
    out = tmp_path / "out"
    run_main(["--input", input_path, "--output-dir", str(out)])
    stdout = capsys.readouterr().out
    assert "written=0" in stdout
    assert stdout.endswith("\n")


def test_cli_summary_counts_ac9(tmp_path, run_main, capsys):
    """AC9 (6.5): --max-pages 2 over 3 linked pages prints pages=2 cards=2 written=2."""
    write_pages(
        tmp_path,
        [
            [make_card(title="A", href="/d/1")],
            [make_card(title="B", href="/d/2")],
            [make_card(title="C", href="/d/3")],
        ],
    )
    out = tmp_path / "out"
    code = run_main(
        [
            "--input",
            str(tmp_path / "page1.html"),
            "--output-dir",
            str(out),
            "--max-pages",
            "2",
        ]
    )
    assert code == 0
    stdout = capsys.readouterr().out
    assert "pages=2" in stdout
    assert "cards=2" in stdout
    assert "written=2" in stdout


def test_cli_idempotent_byte_identical_ac13(tmp_path, run_main):
    """AC13 (R14, R15): two runs into the same dir are byte-identical, overwrite."""
    input_path = _write_single_page(tmp_path, canonical_cards())
    out = tmp_path / "out"
    argv = ["--input", input_path, "--output-dir", str(out)]
    assert run_main(argv) == 0
    first_jsonl = (out / "listings.jsonl").read_bytes()
    first_csv = (out / "listings.csv").read_bytes()
    assert run_main(argv) == 0
    assert (out / "listings.jsonl").read_bytes() == first_jsonl
    assert (out / "listings.csv").read_bytes() == first_csv
    assert first_jsonl == EXPECTED_JSONL
    assert first_csv == EXPECTED_CSV


def test_cli_missing_input_exits_1_no_output_ac14(tmp_path, run_main):
    """AC14 (6.4): a missing --input file exits 1 and writes no output."""
    out = tmp_path / "out"
    code = run_main(
        ["--input", str(tmp_path / "does-not-exist.html"), "--output-dir", str(out)]
    )
    assert code == 1
    assert not (out / "listings.jsonl").exists()
    assert not (out / "listings.csv").exists()


def test_cli_max_pages_zero_is_usage_error_ac15(tmp_path, run_main):
    """AC15 (6.2, 6.4): --max-pages 0 exits 2 and writes no output."""
    input_path = _write_single_page(tmp_path, canonical_cards())
    out = tmp_path / "out"
    code = run_main(
        [
            "--input",
            input_path,
            "--output-dir",
            str(out),
            "--max-pages",
            "0",
        ]
    )
    assert code == 2
    assert not (out / "listings.jsonl").exists()
    assert not (out / "listings.csv").exists()


def test_cli_custom_output_names_ac18(tmp_path, run_main):
    """AC18 (3.1, 6.2): custom --jsonl-name/--csv-name produce those files."""
    input_path = _write_single_page(tmp_path, canonical_cards())
    out = tmp_path / "out"
    code = run_main(
        [
            "--input",
            input_path,
            "--output-dir",
            str(out),
            "--jsonl-name",
            "out.jsonl",
            "--csv-name",
            "out.csv",
        ]
    )
    assert code == 0
    assert (out / "out.jsonl").read_bytes() == EXPECTED_JSONL
    assert (out / "out.csv").read_bytes() == EXPECTED_CSV
    assert not (out / "listings.jsonl").exists()


@pytest.mark.parametrize(
    "jsonl_name, csv_name",
    [
        ("sub/out.jsonl", "listings.csv"),
        ("out\\back.jsonl", "listings.csv"),
        ("", "listings.csv"),
        ("listings.jsonl", "   "),
        (".", "listings.csv"),
        ("..", "listings.csv"),
        ("data.out", "data.out"),
    ],
)
def test_cli_invalid_output_names_exit_2_no_output_ac18(
    tmp_path, run_main, jsonl_name, csv_name
):
    """AC18 (3.1 rules 1-4, 6.4): invalid or equal output names exit 2, no output."""
    input_path = _write_single_page(tmp_path, canonical_cards())
    out = tmp_path / "out"
    code = run_main(
        [
            "--input",
            input_path,
            "--output-dir",
            str(out),
            "--jsonl-name",
            jsonl_name,
            "--csv-name",
            csv_name,
        ]
    )
    assert code == 2
    assert not (out / jsonl_name).exists()
    assert not (out / "listings.jsonl").exists()
    assert not (out / "listings.csv").exists()


@pytest.mark.parametrize(
    "name, expected",
    [
        ("listings.jsonl", True),
        ("out.csv", True),
        ("", False),
        ("   ", False),
        (".", False),
        ("..", False),
        ("sub/out.jsonl", False),
        ("out\\back.jsonl", False),
    ],
)
def test_validate_output_name_branches_ac18(name, expected):
    """AC18 (3.1): validate_output_name accepts only plain basenames."""
    assert validate_output_name(name) is expected


def test_cli_pagination_query_fragment_ac20(tmp_path, run_main):
    """AC20 (R3): a next href with ?query/#fragment resolves under a subdir."""
    base = tmp_path / "a"
    sub = base / "sub"
    sub.mkdir(parents=True)
    (base / "page1.html").write_text(
        make_page(
            [make_card(title="A", href="/d/1")],
            next_href="sub/page2.html?ref=1#top",
        ),
        encoding="utf-8",
    )
    (sub / "page2.html").write_text(
        make_page([make_card(title="B", href="/d/2")], next_href=None),
        encoding="utf-8",
    )
    out = tmp_path / "out"
    code = run_main(["--input", str(base / "page1.html"), "--output-dir", str(out)])
    assert code == 0
    lines = (out / "listings.jsonl").read_bytes().splitlines()
    assert len(lines) == 2


def test_cli_missing_next_page_graceful_exit0_ac16(tmp_path, run_main):
    """AC16 (R13a): missing next page stops gracefully with exit 0 and page-1 output."""
    input_path = _write_single_page(
        tmp_path, [make_card(title="A", href="/detail/900")], next_href="page2.html"
    )
    out = tmp_path / "out"
    code = run_main(["--input", input_path, "--output-dir", str(out)])
    assert code == 0
    lines = (out / "listings.jsonl").read_bytes().splitlines()
    assert len(lines) == 1


def test_cli_atomic_write_failure_leaves_no_output_64(tmp_path, run_main, monkeypatch):
    """§6.4 (R14): a write failure mid-run exits 1 and leaves no final or temp files.

    The JSONL temp is written first, then write_csv raises OSError. main() must
    remove the temp files it created and return 1, so the output directory holds
    neither a partial/looks-successful final file nor any leftover ``*.tmp``.
    """
    import python_template.main as main_module

    def _boom(records, path):
        raise OSError("disk full")

    monkeypatch.setattr(main_module, "write_csv", _boom)

    input_path = _write_single_page(tmp_path, canonical_cards())
    out = tmp_path / "out"
    code = run_main(["--input", input_path, "--output-dir", str(out)])

    assert code == 1
    assert not (out / "listings.jsonl").exists()
    assert not (out / "listings.csv").exists()
    leftover_temps = list(out.glob("*.tmp"))
    assert leftover_temps == []


def test_cli_second_replace_failure_rolls_back_ac_64(tmp_path, run_main, monkeypatch):
    """§6.4 (R14): if the SECOND os.replace fails, the committed first final is
    rolled back so neither final file remains and no temp files are left.

    The first ``os.replace`` (JSONL temp -> final) succeeds via the real
    implementation; the second (CSV temp -> final) raises OSError. main() must
    remove the already-committed JSONL final plus any temp files and return 1.
    """
    import python_template.main as main_module

    real_replace = os.replace
    calls = {"n": 0}

    def _replace(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            return real_replace(src, dst)
        raise OSError("replace failed")

    monkeypatch.setattr(main_module.os, "replace", _replace)

    input_path = _write_single_page(tmp_path, canonical_cards())
    out = tmp_path / "out"
    code = run_main(["--input", input_path, "--output-dir", str(out)])

    assert code == 1
    assert calls["n"] == 2
    assert not (out / "listings.jsonl").exists()
    assert not (out / "listings.csv").exists()
    assert list(out.glob("*.tmp")) == []
