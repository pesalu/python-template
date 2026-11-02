"""Stage 1: fetch a web page over HTTP(S) and save the raw HTML to a file.

The saved file can then be parsed by the ``web-scraper`` command (stage 2).
Only ``http://`` and ``https://`` URLs are allowed; the caller is responsible
for honoring the target site's robots.txt and terms of service.
"""

import argparse
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen

DEFAULT_USER_AGENT = "sample-web-scraper/0.1 (+https://github.com/yourname/sample-web-scraper)"
DEFAULT_TIMEOUT = 30.0
_ALLOWED_SCHEMES = ("http://", "https://")


def fetch(
    url: str,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """Perform an HTTP(S) GET and return the decoded response body."""
    request = Request(url, headers={"User-Agent": user_agent})
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        body: bytes = response.read()
        return body.decode(charset, errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download a web page to a local HTML file.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.url.startswith(_ALLOWED_SCHEMES):
        parser.error("--url must be an http:// or https:// URL")

    try:
        html = fetch(args.url, user_agent=args.user_agent, timeout=args.timeout)
    except (URLError, OSError, ValueError) as exc:
        print(f"error: cannot fetch {args.url}: {exc}", file=sys.stderr)
        return 1

    try:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(html)
    except OSError as exc:
        print(f"error: cannot write {args.output}: {exc}", file=sys.stderr)
        return 1

    print(f"saved {len(html)} characters to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
