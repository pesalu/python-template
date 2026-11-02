# sample-web-scraper

An MVP web scraper for item-listing pages (e.g. real-estate listings) built with
[uv](https://docs.astral.sh/uv/) for
dependency management, [hatchling](https://hatch.pypa.io/) as the build
backend, [Ruff](https://docs.astral.sh/ruff/) for linting/formatting,
[mypy](https://mypy.readthedocs.io/) for type checking, [pytest](https://docs.pytest.org/)
for testing, [pre-commit](https://pre-commit.com/) for git hooks, and
[pip-audit](https://pypi.org/project/pip-audit/) for dependency vulnerability scanning.

## Setup

```bash
uv sync
uv run pre-commit install
```

## Usage

This package ships an MVP web scraper that reads **local HTML listing-page
fixtures**, extracts one record per listing "card", follows pagination across
files, de-duplicates, and writes the results to JSONL and CSV. The parser itself
performs no network I/O — you point it at an HTML file on disk. See the full
behavior specification in [docs/specs/web-scraper.md](docs/specs/web-scraper.md).

### Two-stage workflow (download, then parse)

The two commands are separate on purpose, so parsing stays deterministic and
offline:

```bash
# Stage 1 — download a page to a local HTML file
uv run web-scraper-fetch --url https://example.com/listings --output page1.html

# Stage 2 — parse the saved file into JSONL + CSV
uv run web-scraper --input page1.html --output-dir out
```

`web-scraper-fetch` only performs an HTTP(S) GET and saves the raw response.
**You are responsible for honoring the target site's `robots.txt` and terms of
service.** Many listing sites (e.g. large real-estate portals) are
JavaScript-rendered or serve their data from endpoints their `robots.txt`
disallows, so a saved page may contain no listings. For a parse to produce
records, the saved HTML must use the class names the parser expects (see
[src/web_scraper/parse.py](src/web_scraper/parse.py)); adapt those selectors to
the target site.

`web-scraper-fetch` arguments: `--url` (required, `http://`/`https://` only),
`--output` (required, file path), `--user-agent` (optional), `--timeout`
(optional, seconds).

### Single-page-app sites (embedded JSON)

Many modern listing sites are React/Vue apps: the rendered HTML uses
build-hashed class names and the actual listings are embedded as a JSON state
object (`window.__INITIAL_STATE__`). The HTML-card parser can't read those, so a
second parser handles them:

```bash
# Stage 1 — download the page (data is embedded in the HTML)
uv run web-scraper-fetch --url "https://example.com/listings?page=1" --output page1.html

# Stage 2 — extract listings from the embedded __INITIAL_STATE__ blob
uv run web-scraper-json --input page1.html --output-dir out --profile mysite.json
```

`web-scraper-json` has **no built-in site profile** — you must pass a `--profile`
JSON file that declares the dotted path to the listings array and maps each
output field to a source key:

```json
{
  "state_path": "data.searchResults.items",
  "fields": { "title": "address", "price": "price", "area": "livingArea" },
  "detail_url_template": "https://example.com/listing/{value}",
  "detail_url_field": "slug"
}
```

Arguments: `--input` (saved HTML), `--output-dir`, `--profile` (required JSON
mapping), `--jsonl-name`/`--csv-name` (optional). As always, **check the site's
`robots.txt` and terms of service** — reading JSON embedded in an allowed page is
one thing, but many sites disallow their underlying `/api` endpoints, and
robots.txt permission is not the same as terms-of-service permission.

### Run the parser

```bash
uv run web-scraper --input path/to/page1.html --output-dir out
```

This writes `out/listings.jsonl` and `out/listings.csv`, then prints a one-line
summary:

```
pages=1 cards=2 written=2 skipped_invalid=0 skipped_duplicate=0
```

### Arguments

| Argument        | Required | Default           | Meaning                                                      |
|-----------------|----------|-------------------|--------------------------------------------------------------|
| `--input`       | yes      | —                 | Path to the first listing-page HTML file (page 1).           |
| `--output-dir`  | yes      | —                 | Directory for the output files (created if missing).         |
| `--max-pages`   | no       | `10`              | Maximum pages to follow via pagination (page 1 included). Must be `>= 1`. |
| `--jsonl-name`  | no       | `listings.jsonl`  | Output JSONL filename (plain name, no path separators).      |
| `--csv-name`    | no       | `listings.csv`    | Output CSV filename (plain name, no path separators).        |

### Expected HTML structure

Each page is matched by class names (not tag names). A minimal page looks like:

```html
<main class="listings">
  <article class="listing-card">
    <h2 class="listing-title">Cozy Downtown Apartment</h2>
    <span class="listing-price">€250,000</span>
    <span class="listing-location">Helsinki, Kallio</span>
    <span class="listing-rooms">3 rooms</span>
    <span class="listing-area">72 m²</span>
    <a class="listing-link" href="/detail/123">View details</a>
  </article>
</main>
<a class="pagination-next" href="page2.html">Next</a>
```

- Only `title` is required; a card without a non-empty `listing-title` is
  skipped. The other fields become `null` (JSONL) / empty (CSV) when absent.
- `detail_url` is the raw `href`; records are de-duplicated on it.
- `a.pagination-next` is followed relative to the current file's directory.
  Pagination stops at the last page, at `--max-pages`, or when the next file is
  missing/unreadable (exit code `0`).

### Output

- `listings.jsonl` — one UTF-8 JSON object per line, fields in order
  `title, price, location, rooms, area, detail_url`.
- `listings.csv` — same fields with a header row and minimal quoting.

### Exit codes

| Code | Meaning                                                              |
|------|---------------------------------------------------------------------|
| `0`  | Success (including zero records: empty JSONL + header-only CSV).     |
| `1`  | The `--input` file cannot be read, or output cannot be written.      |
| `2`  | Invalid arguments (e.g. `--max-pages 0`, or a bad/duplicate name).   |

## Development

```bash
# Run tests with coverage
uv run pytest

# Lint
uv run ruff check .

# Format
uv run ruff format .

# Type check
uv run mypy

# Scan dependencies for known vulnerabilities
uv run pip-audit

# Run all pre-commit hooks against every file
uv run pre-commit run --all-files
```
