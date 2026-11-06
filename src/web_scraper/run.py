"""One-shot job for containers: download a page and save the raw embedded JSON.

Configured by environment variables so cloud job services need no custom command:

* ``SCRAPER_URL`` (required) - page to download.
* ``SCRAPER_STATE_PATH`` (optional) - dotted path to the listings array; also writes
  ``items.jsonl``.

Files are written to the current directory (``/data`` in the image). Each run adds its UTC start
time to the file names (``raw_20261106T170703Z.json``), so earlier runs are never overwritten.
"""

import os
import sys
from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from web_scraper import download, extractcli


def main(
    argv: list[str] | None = None,
    environ: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> int:
    env = os.environ if environ is None else environ
    url = env.get("SCRAPER_URL", "")
    if not url:
        print("error: set SCRAPER_URL to the page to download", file=sys.stderr)
        return 2

    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    page, raw, items = f"page1_{stamp}.html", f"raw_{stamp}.json", f"items_{stamp}.jsonl"

    steps: list[tuple[Callable[[list[str] | None], int], list[str]]] = [
        (download.main, ["--url", url, "--output", page]),
        (extractcli.main, ["--input", page, "--output", raw]),
    ]
    state_path = env.get("SCRAPER_STATE_PATH", "")
    if state_path:
        steps.append(
            (
                extractcli.main,
                ["--input", page, "--output", items, "--state-path", state_path, "--jsonl"],
            )
        )

    for step, args in steps:
        code = step(args)
        if code != 0:
            return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
