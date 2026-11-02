"""Stage: capture the raw embedded ``__INITIAL_STATE__`` JSON, unmapped.

Follows ``web-scraper-fetch`` (which saves the raw HTML): it extracts the
original JSON data as-is so mapping to any downstream model stays a separate
concern. No profile or field mapping is applied.
"""

import argparse
import contextlib
import json
import os
import sys
from typing import Any

from web_scraper.initial_state import InitialStateError, extract_raw


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract the raw embedded __INITIAL_STATE__ JSON (no mapping) to a file."
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--state-path",
        help="Dotted path to a sub-node (e.g. a listings array). Omit to dump the whole state.",
    )
    parser.add_argument(
        "--jsonl",
        action="store_true",
        help="If the extracted node is an array, write one JSON object per line.",
    )
    return parser


def _serialize(node: Any, as_jsonl: bool) -> str:
    if as_jsonl and isinstance(node, list):
        return "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in node)
    return json.dumps(node, ensure_ascii=False, indent=2) + "\n"


def _write_atomic(text: str, path: str) -> None:
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except OSError:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        with open(args.input, encoding="utf-8") as handle:
            html = handle.read()
    except OSError as exc:
        print(f"error: cannot read input file {args.input}: {exc}", file=sys.stderr)
        return 1

    try:
        node = extract_raw(html, args.state_path)
    except InitialStateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        _write_atomic(_serialize(node, args.jsonl), args.output)
    except OSError as exc:
        print(f"error: cannot write output {args.output}: {exc}", file=sys.stderr)
        return 1

    count = len(node) if isinstance(node, list) else 1
    print(f"extracted {count} to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
