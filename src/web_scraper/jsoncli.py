"""Stage-2 variant: parse listings from an embedded ``__INITIAL_STATE__`` blob.

For single-page-app listing sites whose data is embedded as JSON in the page
(rather than as HTML cards), this command reads a saved HTML file, extracts the
state, maps it with a caller-supplied profile, and writes the same JSONL + CSV
output as the HTML parser. A ``--profile`` JSON file is required; it declares the
listings path and the field mapping, so no site-specific logic is built in.
"""

import argparse
import contextlib
import json
import os
import sys

from web_scraper.initial_state import InitialStateError, Profile, parse_initial_state
from web_scraper.main import validate_output_name
from web_scraper.output import write_csv, write_jsonl


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse listings from an embedded __INITIAL_STATE__ blob into JSONL and CSV."
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--profile",
        required=True,
        help="JSON profile declaring the listings path and field mapping.",
    )
    parser.add_argument("--jsonl-name", default="listings.jsonl")
    parser.add_argument("--csv-name", default="listings.csv")
    return parser


def load_profile(path: str) -> Profile:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or "state_path" not in data:
        raise ValueError("profile must be an object with a 'state_path' key")
    return Profile(
        state_path=data["state_path"],
        fields=dict(data.get("fields", {})),
        detail_url_template=data.get("detail_url_template"),
        detail_url_field=data.get("detail_url_field"),
    )


def _write_outputs(
    records: list[dict[str, str | None]], output_dir: str, names: tuple[str, str]
) -> None:
    """Write JSONL + CSV atomically: temp files, then replace, with rollback."""
    os.makedirs(output_dir, exist_ok=True)
    jsonl_final = os.path.join(output_dir, names[0])
    csv_final = os.path.join(output_dir, names[1])
    jsonl_tmp = jsonl_final + ".tmp"
    csv_tmp = csv_final + ".tmp"
    committed_finals: list[str] = []
    try:
        write_jsonl(records, jsonl_tmp)
        write_csv(records, csv_tmp)
        os.replace(jsonl_tmp, jsonl_final)
        committed_finals.append(jsonl_final)
        os.replace(csv_tmp, csv_final)
        committed_finals.append(csv_final)
    except OSError:
        for path in (*committed_finals, jsonl_tmp, csv_tmp):
            with contextlib.suppress(OSError):
                os.remove(path)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if (
        not validate_output_name(args.jsonl_name)
        or not validate_output_name(args.csv_name)
        or args.jsonl_name == args.csv_name
    ):
        parser.error("invalid or duplicate output file names")

    try:
        profile = load_profile(args.profile)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: cannot load profile {args.profile}: {exc}", file=sys.stderr)
        return 1

    try:
        with open(args.input, encoding="utf-8") as handle:
            html = handle.read()
    except OSError as exc:
        print(f"error: cannot read input file {args.input}: {exc}", file=sys.stderr)
        return 1

    try:
        records = parse_initial_state(html, profile)
    except InitialStateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        _write_outputs(records, args.output_dir, (args.jsonl_name, args.csv_name))
    except OSError as exc:
        print(f"error: cannot write output: {exc}", file=sys.stderr)
        return 1

    print(f"listings={len(records)} written={len(records)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
