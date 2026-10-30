import argparse
import contextlib
import os
import sys

from web_scraper.output import write_csv, write_jsonl
from web_scraper.pipeline import InputReadError, scrape


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("--max-pages must be >= 1")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape listing pages to JSONL and CSV.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-pages", type=_positive_int, default=10)
    parser.add_argument("--jsonl-name", default="listings.jsonl")
    parser.add_argument("--csv-name", default="listings.csv")
    return parser


def validate_output_name(name: str) -> bool:
    if name.strip() == "":
        return False
    if name in {".", ".."}:
        return False
    if "/" in name or "\\" in name:
        return False
    return name == os.path.basename(name)


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
        result = scrape(args.input, args.max_pages)
    except InputReadError:
        print(f"error: cannot read input file: {args.input}", file=sys.stderr)
        return 1

    try:
        os.makedirs(args.output_dir, exist_ok=True)
        jsonl_final = os.path.join(args.output_dir, args.jsonl_name)
        csv_final = os.path.join(args.output_dir, args.csv_name)
        jsonl_tmp = jsonl_final + ".tmp"
        csv_tmp = csv_final + ".tmp"
        committed_finals: list[str] = []
        try:
            write_jsonl(result.records, jsonl_tmp)
            write_csv(result.records, csv_tmp)
            os.replace(jsonl_tmp, jsonl_final)
            committed_finals.append(jsonl_final)
            os.replace(csv_tmp, csv_final)
            committed_finals.append(csv_final)
        except OSError:
            for path in (*committed_finals, jsonl_tmp, csv_tmp):
                with contextlib.suppress(OSError):
                    os.remove(path)
            raise
    except OSError as exc:
        print(f"error: cannot write output: {exc}", file=sys.stderr)
        return 1

    print(
        f"pages={result.pages} cards={result.cards} written={result.written} "
        f"skipped_invalid={result.skipped_invalid} "
        f"skipped_duplicate={result.skipped_duplicate}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
