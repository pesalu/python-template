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
object (`window.__INITIAL_STATE__`). The HTML-card parser can't read those, so
`web-scraper-extract` captures that embedded JSON **as-is** — the original data,
unchanged. Mapping it to any particular model is intentionally left to a
downstream consumer; this tool only stores the raw data.

```bash
# Stage 1 — download the page (data is embedded in the HTML)
uv run web-scraper-fetch --url "https://example.com/listings?page=1" --output page1.html

# Stage 2a — dump the whole __INITIAL_STATE__ object (pretty-printed) to inspect it
uv run web-scraper-extract --input page1.html --output raw.json

# Stage 2b — find the dotted path to the listings array in raw.json, then extract
#            just that array, one raw object per line:
uv run web-scraper-extract --input page1.html --output items.jsonl \
  --state-path <path.to.listings.array> --jsonl
```

> The `--state-path` is **site-specific** — there is no universal value. Always
> run stage 2a first (no `--state-path`) to dump the full state, locate the array
> of listings inside it, and use that dotted path (e.g. `foo.searchResults.bar`)
> in stage 2b. If the path is wrong or missing, the command exits `1` with
> `error: path not found: ...`.

Arguments: `--input` (saved HTML), `--output` (JSON file), `--state-path`
(optional dotted path to a sub-node; omit to dump the whole state), `--jsonl`
(optional; when the node is an array, write one object per line). Exit codes:
`0` success, `1` on read/extract/write failure.

The resulting `items.jsonl` is ready to use directly — one original JSON object
per line — with any downstream tool (`jq`, `pandas.read_json(..., lines=True)`,
DuckDB's `read_json_auto`, etc.). As always, **check the site's `robots.txt` and
terms of service**: reading JSON embedded in an allowed page is one thing, but
many sites disallow their underlying `/api` endpoints, and robots.txt permission
is not the same as terms-of-service permission.

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
    <span class="listing-location">Rivertown, Dockside</span>
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

## Docker

```bash
docker build -t web-scraper .

# Where to store the results on your machine (any folder you like)
DATA=$HOME/scrapes/site-a
mkdir -p "$DATA"

# Pick the command to run: web-scraper-fetch, web-scraper-extract or web-scraper
RUN="docker run --rm --user $(id -u):$(id -g) -v $DATA:/data web-scraper"

$RUN web-scraper-fetch --url https://example.com/listings --output page1.html
$RUN web-scraper-extract --input page1.html --output raw.json
$RUN web-scraper --input page1.html --output-dir out
```

The container's working directory is `/data`, which is your `$DATA` folder, so relative paths land
there. Use an absolute host path for `DATA` (`-v` treats a bare name as a Docker volume).
`--user` makes the files yours instead of root's. The arguments are the same as without Docker.

### All steps in one command

For single-page-app sites (listings embedded as JSON): download the page, save the whole embedded
state as `raw.json`, and save just the listings as `items.jsonl`.

```bash
STATE_PATH=data.results.items   # site-specific dotted path to the listings array

docker run --rm --user $(id -u):$(id -g) -v $DATA:/data \
  -e URL=https://example.com/listings -e STATE_PATH="$STATE_PATH" web-scraper sh -c '
    web-scraper-fetch   --url "$URL" --output page1.html &&
    web-scraper-extract --input page1.html --output raw.json &&
    web-scraper-extract --input page1.html --output items.jsonl --state-path "$STATE_PATH" --jsonl'
```

The steps run in order and stop at the first one that fails; the container's exit code is that
step's exit code. `STATE_PATH` is the path to the listings inside the embedded JSON; find it by
looking in the dumped `raw.json` (see above). For plain HTML-card sites (no embedded JSON), replace
the two extract steps with `web-scraper --input page1.html --output-dir out`.

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
