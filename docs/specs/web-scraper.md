# Functional specification: Scalable MVP web scraper

Status: Draft (round 5)
Feature file: `docs/specs/web-scraper.md`
Applies to package: `src/web_scraper/`

> Project note: this is a plain Python package (hatchling + uv, Python `>=3.12`),
> not a Databricks bundle. There is no Spark, no catalog/schema, and no
> bronze/silver/gold layering. The standard data-pipeline spec sections below
> have been adapted to a plain Python CLI/library context.

> Runtime dependency note: HTML parsing uses **beautifulsoup4** (the
> `BeautifulSoup` class), added as a runtime dependency of the package. It is
> always constructed with the stdlib backend parser string `"html.parser"`
> (i.e. `BeautifulSoup(html, "html.parser")`); no `lxml` or `html5lib` backend
> is used. This pins malformed-HTML handling and text extraction so they are
> deterministic across environments. The only other libraries used are the
> Python standard library (`argparse`, `json`, `csv`, `os`, `socket`,
> `tracemalloc`, `time`).

---

## 1. Purpose and scope

### Purpose
Provide a Minimum Viable Product (MVP) web scraper that extracts **raw** listing
records from an item-listing web page (for example a real-estate listing page
where each item is a "card" exposing title, price, location, number of rooms,
area, and a detail URL) and writes those records to local files in both JSONL
and CSV formats.

The MVP is "scalable" in the sense that its layers are cleanly separated so that
additional sites/parsers and a real network fetcher can be added later without
rewriting the parsing, record-building, or output logic.

### In scope
- Reading listing-page HTML from **local fixture files** (no live network).
- Parsing one listing page's HTML into a list of raw record dictionaries.
- Following pagination across multiple local fixture files up to a configurable
  page limit.
- Collecting records across pages, de-duplicating them, and writing them to
  JSONL and CSV files in a configurable output directory.
- A thin command-line wrapper exposed through the existing
  `[project.scripts]` entry point.

### Non-goals (explicitly out of scope for this MVP)
- Live HTTP/HTTPS fetching, retries, rate limiting, robots.txt, or ToS handling.
  (The fetch layer is designed to be swappable later; see R2.)
- Data cleaning/normalization beyond trivial text extraction and whitespace
  handling (see R6 and section 5).
- JavaScript rendering / headless browsers.
- Support for more than one site layout. Only the single fixture layout in
  section 2 is supported by the MVP. (Multiple layouts is a later extension.)
- Nested `listing-card` elements (a card inside another card). The MVP fixture
  layout never nests cards; only top-level cards are treated as cards (section
  2.2). Nested cards are unsupported input.
- Databases, cloud storage, or any non-local output target.
- Incremental/delta runs or change tracking; every run is a full rewrite (R14).
- Containment/sandboxing of resolved pagination paths. A relative `..` path
  traversal in a `pagination-next` `href` is **not** contained to the input
  directory in the MVP: because R3 resolves such an `href` via
  `os.path.normpath(os.path.join(current_page_dir, stripped_path))` with no
  containment check, a crafted `href` such as `../../../../etc/passwd` can make
  the fetch layer read a file outside the `--input` file's directory. This is
  intentional for the MVP, which assumes **trusted local fixtures** (URLs and
  absolute paths are already rejected per R3; the scraper is read-only and
  UTF-8-only; only listing-card data is surfaced). Restricting resolved paths to
  under the input directory is a later extension and is out of scope here.

---

## 2. Inputs: fixture HTML structure and listing-page contract

### 2.1 Input source
- Input is one or more **local HTML fixture files** stored under
  `tests/fixtures/` (the directory used by tests; at runtime any directory may
  be supplied via the CLI, see section 6). No file path is hardcoded.
- Encoding of fixture files: UTF-8.
- The scraper is given the path to the **first** listing page (page 1). Further
  pages are discovered by following the pagination link (R3).

### 2.2 Listing-page contract (required element/class names)
Each listing page is an HTML document parsed with `BeautifulSoup(html,
"html.parser")`. The scraper recognizes exactly the following structure. Class
names are matched exactly (case-sensitive) and an element "has class X" when `X`
appears as a whitespace-separated token in its `class` attribute.

| Concept            | Selector (element + class)        | Extracted value                 |
|--------------------|-----------------------------------|---------------------------------|
| Listing card       | any **top-level** element with class `listing-card` (see "Nested cards" below) | one card = one candidate record |
| Title              | descendant with class `listing-title` | element text content            |
| Price              | descendant with class `listing-price` | element text content            |
| Location           | descendant with class `listing-location` | element text content         |
| Rooms              | descendant with class `listing-rooms` | element text content            |
| Area               | descendant with class `listing-area` | element text content            |
| Detail URL         | descendant `a` element with class `listing-link` | value of its `href` attribute |
| Pagination "next"  | `a` element with class `pagination-next` | value of its `href` attribute |

**Definition of "element text content".** For a selector element, its text
content is the string returned by BeautifulSoup's `get_text()` called on that
element — i.e. the direct concatenation, in document order, of all descendant
text nodes of the element, with **no** separator inserted between them (bs4
default `separator=""`). HTML entities are already decoded by the parser at this
point (e.g. `&amp;` → `&`). The resulting string is then normalized per R6. The
absence of a separator is immaterial because R6 collapses all internal
whitespace runs (see R6/F1.5), so the only text joins that matter are between
adjacent non-whitespace text fragments, which are intentionally concatenated
directly.

Rules for descendants:
- "Descendant with class X" means the first element in document order, within
  the card subtree, that has class X. If none exists, the value is **absent**
  (see R5/R6 for how absence maps to null).
- For the detail URL, the first descendant `a` with class `listing-link` is
  used; if it exists but has no `href` attribute, the detail URL is absent. If
  the `href` attribute is present but its value is an empty string or consists
  only of whitespace, the detail URL is also **absent** (null) and the record is
  not eligible for de-duplication (R9, F1.10 / data-quality section 5).
- Pagination is searched over the **whole document**, not inside a card. The
  first `a.pagination-next` in document order is used. If none exists, this is
  the last page (R3, R13).

**Nested cards.** Only **top-level** `listing-card` elements are treated as
cards: an element with class `listing-card` is a card only if it has **no**
ancestor element that also has class `listing-card`. A `listing-card` nested
inside another `listing-card` is ignored as a card (its fields are only
reachable as descendants of the outer card). The MVP fixture layout in 2.3 never
nests cards; nested cards are therefore not an expected input, and this rule
exists only to make the behavior deterministic if nesting is encountered. (See
non-goals in section 1.)

### 2.3 Canonical fixture example (page 1)
```html
<!DOCTYPE html>
<html lang="en">
  <body>
    <main class="listings">
      <article class="listing-card">
        <h2 class="listing-title">Cozy Downtown Apartment</h2>
        <span class="listing-price">€250,000</span>
        <span class="listing-location">Rivertown, Dockside</span>
        <span class="listing-rooms">3 rooms</span>
        <span class="listing-area">72 m²</span>
        <a class="listing-link" href="/detail/123">View details</a>
      </article>
      <article class="listing-card">
        <h2 class="listing-title">Seaside Studio</h2>
        <span class="listing-price">€180,000</span>
        <span class="listing-location">Lakeside</span>
        <span class="listing-rooms">1 room</span>
        <span class="listing-area">28 m²</span>
        <a class="listing-link" href="/detail/124">View details</a>
      </article>
    </main>
    <a class="pagination-next" href="page2.html">Next</a>
  </body>
</html>
```

### 2.4 Freshness and volume (MVP bounds)
- Freshness: not applicable (static fixtures).
- Volume supported and tested: up to 10 pages, up to 50 cards per page
  (<= 500 candidate records per run). See section 9.

---

## 3. Outputs: files, schema, grain, output directory

### 3.1 Output files
Two files are written into the output directory (section 6, `--output-dir`):
- A JSONL file — one JSON object per line (JSON Lines). Its filename is given by
  `--jsonl-name` (default `listings.jsonl`; section 6.2).
- A CSV file — CSV with a header row. Its filename is given by `--csv-name`
  (default `listings.csv`; section 6.2).

Both `--jsonl-name` and `--csv-name` are plain filenames (no directory
component) written into `--output-dir`. **Filename validity rule (platform-independent,
checked identically on all platforms).** A supplied name is **rejected as an
argument error (exit code 2; section 6.4)** if ANY of the following holds:
1. it is the empty string `""` or consists only of whitespace (as defined by
   Python `str.isspace()` / `str.strip() == ""`);
2. it is exactly `.` or exactly `..`;
3. it contains the character `/` or the character `\` (both are checked
   unconditionally on every platform, including POSIX);
4. it otherwise differs from `os.path.basename(name)` (i.e. the name is not its
   own basename).
A name is accepted only if none of 1–4 holds. This rule is fully deterministic
and gives the same verdict on every OS. Elsewhere in this spec the names
`listings.jsonl` and `listings.csv` refer to these two files at their default
names.

Both files are always written on a successful run, even when zero records are
produced (in which case the JSONL file is an empty file with zero lines and the
CSV file contains only the header row; section 3.5, F1.11).

### 3.2 Record grain
One output record (one JSONL line / one CSV data row) corresponds to exactly one
**unique** listing card kept after de-duplication (R9) and validity filtering
(R7). Order of records follows discovery order: page order first, then card
order within a page (R10).

### 3.3 Record schema
Field order is fixed and identical in JSONL and CSV:

| # | Field        | Type           | Nullable | Notes                                       |
|---|--------------|----------------|----------|---------------------------------------------|
| 1 | `title`      | string         | No       | Required; a record with absent/empty title is invalid (R7). |
| 2 | `price`      | string \| null | Yes      | Raw text, trimmed (R6).                       |
| 3 | `location`   | string \| null | Yes      | Raw text, trimmed (R6).                       |
| 4 | `rooms`      | string \| null | Yes      | Raw text, trimmed (R6).                       |
| 5 | `area`       | string \| null | Yes      | Raw text, trimmed (R6).                       |
| 6 | `detail_url` | string \| null | Yes      | Raw `href` value stored **exactly as-is** (NOT R6-normalized, not trimmed/collapsed, not resolved to absolute); see R6/R9 and F1.3. Empty/whitespace-only `href` → null (section 2.2). |

All values are strings (or null). No numeric/currency parsing is performed (R6).
`title`, `price`, `location`, `rooms`, and `area` are R6-normalized text
content; `detail_url` is the raw `href` attribute value and is **never**
R6-normalized (F1.3).

### 3.4 JSONL encoding rules
- UTF-8 encoding, no BOM.
- One JSON object per line, keys in the fixed field order of section 3.3.
- Non-ASCII characters are written as-is (not `\uXXXX`-escaped), i.e. Unicode is
  preserved (`ensure_ascii` disabled).
- Null values are the JSON literal `null`.
- Line terminator: single LF (`\n`), including after the last line.

Example line (from the first card in 2.3):
```json
{"title": "Cozy Downtown Apartment", "price": "€250,000", "location": "Rivertown, Dockside", "rooms": "3 rooms", "area": "72 m²", "detail_url": "/detail/123"}
```

### 3.5 CSV encoding rules
- UTF-8 encoding, no BOM.
- First line is the header: `title,price,location,rooms,area,detail_url`.
- One data row per record, fields in the fixed order of section 3.3.
- Quoting is minimal: a field is quoted only when it contains a comma, a double
  quote, CR, or LF; embedded double quotes are escaped by doubling them.
- Null values are written as an empty field (zero-length string). An empty
  string value and a null value are therefore indistinguishable in CSV; the
  JSONL file is the authoritative source for null-vs-empty.
- Line terminator: single LF (`\n`) between and after rows.

The authoritative worked CSV example (with quoting) is **AC3**; no illustrative
CSV row is given here, to avoid any byte-level contradiction with AC3.

**Header-only (zero-record) CSV — exact bytes.** When no records are written,
the CSV file consists of exactly the header line followed by a single trailing
LF, and nothing else:
```
title,price,location,rooms,area,detail_url\n
```
i.e. the 42 characters `title,price,location,rooms,area,detail_url` followed by
one `\n` (one `0x0A` byte), total 43 bytes, no BOM, no second line, no trailing
blank line. This is aligned with AC12 and AC13.

### 3.6 Output directory parameter
- The output directory is supplied via `--output-dir` (section 6). It is never
  hardcoded.
- If the directory does not exist, it is created (including missing parent
  directories).
- Existing output files with the chosen names (`--jsonl-name` / `--csv-name`,
  defaults `listings.jsonl` / `listings.csv`) in that directory are overwritten
  (R14).

---

## 4. Business rules

- **R1 — Layered separation.** The scraper is organized into three independent
  layers whose boundaries are defined by data types, not by implementation
  detail: (a) a **fetch** layer that returns the HTML text of a page given a page
  reference; (b) a **parse** layer of pure functions that turn an HTML string
  into records and discover the next-page reference; (c) an **output** layer that
  serializes records to JSONL and CSV. No layer calls the CLI; the CLI calls the
  layers (R17).

- **R2 — Swappable fetch layer.** For the MVP, the fetch layer reads page HTML
  from a local fixture file identified by a file-system path. The fetch layer’s
  contract is "page reference in → HTML string out" so a network fetcher can
  replace it later without changing the parse or output layers. The MVP fetch
  layer performs **no** network I/O.

- **R3 — Pagination discovery and href→path resolution.** After parsing a page,
  the next-page reference is the `href` of the first `a.pagination-next` element
  in the document. If there is no `a.pagination-next` element, the current page
  is the last page. When an `href` is present, it is resolved to a local file
  path as follows, deterministically:
  1. Any `?query` and/or `#fragment` suffix is stripped from the `href` before
     joining: the path portion is everything before the first `?` or `#`,
     whichever comes first.
  2. If the stripped path is empty, or looks like a full URL
     (it contains `://`, e.g. `http://…`, `https://…`), or is an
     absolute filesystem path (it begins with `/` on POSIX, or with a drive
     letter / leading separator on the platform), it is treated as a **broken
     next-page reference** → pagination stops gracefully, current page is the
     last page (R13a, decision 2). The MVP has no network, so absolute/remote
     references cannot be fetched and are never an error.
  3. Otherwise the target file path is
     `os.path.normpath(os.path.join(current_page_dir, stripped_path))`, where
     `current_page_dir` is the directory of the current page file.
  Self-references and reference loops (e.g. a page linking to itself) are **not**
  specially detected; the only bound on iteration is `--max-pages` (R4). Note:
  step 3 performs **no** containment check, so a relative `..` traversal in the
  `href` may resolve to a file outside the `--input` file's directory; this is an
  intentional, documented non-goal for the trusted-fixtures MVP (section 1).

- **R4 — Page limit.** The scraper processes at most `--max-pages` pages
  (section 6), counting the starting page as page 1. Pagination following stops
  when (a) there is no next link, or (b) `--max-pages` pages have been processed,
  whichever comes first.

- **R5 — Field extraction.** For each card, each field value is the text content
  of its selector element (section 2.2), or the `href` for `detail_url`. If the
  selector element (or, for `detail_url`, the `href` attribute) is absent, the
  raw extracted value is absent.

- **R6 — Minimal normalization (what IS and ISN'T done).**
  - **Scope.** R6 applies ONLY to the five text fields (`title`, `price`,
    `location`, `rooms`, `area`), which are derived from element text content
    (section 2.2). R6 does **NOT** apply to `detail_url`: the `href` value is
    stored exactly as-is, with no trimming, collapsing, or resolution (F1.3).
  - IS done, in this order, for each text field:
    1. Obtain the element text content via bs4 `get_text()` (section 2.2); HTML
       entity decoding (e.g. `&amp;` → `&`, `&nbsp;` → U+00A0) is already applied
       by the parser.
    2. Normalize whitespace using Python `str.split()` / `" ".join(...)`
       semantics: the normalized value is `" ".join(text.split())`. `str.split()`
       with no arguments splits the string on **runs of Unicode whitespace** and
       discards leading/trailing whitespace, so trimming and internal collapsing
       use one and the same rule and the same code-point set. Internal runs
       collapse to a single ASCII space (U+0020).
  - **Exact whitespace code-point set.** The whitespace characters recognized for
    BOTH trimming and internal collapse are exactly those Python's `str.split()`
    treats as whitespace, which includes at least: space U+0020, tab U+0009,
    line feed U+000A, carriage return U+000D, vertical tab U+000B, form feed
    U+000C, **non-breaking space U+00A0**, and the other Unicode whitespace code
    points Python classifies as whitespace (e.g. U+2028, U+2029, U+3000). The set
    is identical for trim and collapse (F1.5).
  - **NBSP (U+00A0) behavior (verified).** Python `str.split()` treats U+00A0 as
    whitespace, so an NBSP (including one produced from `&nbsp;`) is collapsed
    like any other whitespace: a run containing NBSP becomes a single ASCII space
    U+0020, and leading/trailing NBSP is trimmed. For example the title text
    `"\u00a0Cozy\u00a0\u00a0Flat\u00a0"` normalizes to `"Cozy Flat"`.
  - ISN'T done: currency/number parsing; unit stripping (e.g. keep `"72 m²"`);
    lowercasing or case folding; removing thousands separators or currency
    symbols; resolving relative URLs to absolute; trimming of non-whitespace
    punctuation; deriving or inferring any field from another; any modification
    of `detail_url`.
  - After normalization, a text value consisting only of whitespace becomes an
    empty string, which is then treated as absent (null) per R5/R7.

- **R7 — Validity: required title.** A candidate record is **valid** only if its
  `title` is a non-empty string after R6 normalization. A candidate whose title
  is absent or empty is **invalid**.

- **R8 — Invalid record handling.** Invalid records (R7) are **skipped**
  (dropped), never written to output, and counted (section 7 run summary). An
  invalid record does not abort the run.

- **R9 — De-duplication key.** Two valid records are duplicates when both have a
  non-null `detail_url` and those `detail_url` values are byte-for-byte equal.
  The dedup key is the **raw `href` string exactly as stored** (R6 is not applied
  to it; F1.3): no trimming, case folding, or URL resolution is performed before
  comparison. The **first** occurrence in discovery order is kept; later
  duplicates are skipped and counted. Records with a null `detail_url` (absent,
  empty, or whitespace-only `href`; section 2.2) are never considered duplicates
  of any record and are always kept.

- **R10 — Record ordering.** Output order is discovery order: pages in the order
  they are processed (page 1, page 2, …), and within each page, cards in document
  order. De-duplication removes later duplicates but does not reorder kept
  records.

- **R11 — Missing optional fields produce null.** For a valid record, any absent
  optional field (`price`, `location`, `rooms`, `area`, `detail_url`) is set to
  JSON `null` (and an empty CSV field per R14/section 3.5).

- **R12 — Zero cards on a page.** A page that contains no `listing-card` elements
  contributes zero records. This is not an error; pagination still proceeds per
  R3/R4.

- **R13 — End of pagination.** The run ends normally after processing the last
  page (no next link) or after reaching `--max-pages`.

- **R13a — Broken next-page reference stops gracefully (decision 2).** When a
  `pagination-next` `href` resolves (per R3) to a next-page file that cannot be
  read — the file is **missing/nonexistent**, exists but is **unreadable**
  (e.g. permission denied), or **fails to decode as UTF-8** — OR the `href` is a
  broken reference per R3 step 2 (empty-after-strip, full URL, or absolute path):
  pagination **stops gracefully**. The current page is treated as the last page,
  the run exits with code **0**, and all records collected up to and including
  the current page are written normally. This is NOT a runtime failure and never
  yields exit code 1. (Contrast with R2/section 6.4: the **first** page named by
  `--input` being missing/unreadable/non-UTF-8 IS a runtime failure, exit 1.)

- **R14 — Idempotent full rewrite.** Each run fully recomputes output from the
  input and overwrites `listings.jsonl` and `listings.csv`. Two runs over the
  same inputs and arguments produce byte-identical output files. The scraper
  never appends to existing output files.

- **R15 — Deterministic output.** Given identical fixture files and identical
  CLI arguments, the output is fully deterministic (no dependence on wall-clock
  time, randomness, or filesystem iteration order of cards, since card order is
  taken from document order per R10).

- **R16 — Pure parse functions.** The parse layer functions are pure: they take
  an HTML string (and, for next-page resolution, the current page's directory
  path as a plain string) and return values with no side effects, no I/O, and no
  global state.

- **R17 — Thin CLI.** The CLI entry point only parses arguments, invokes the
  layers (R1), and sets the process exit code (section 6). It contains no parsing
  or record-building logic.

---

## 5. Data quality rules

| Condition                                             | Classification | Action                                   | Rule |
|-------------------------------------------------------|----------------|------------------------------------------|------|
| `title` present and non-empty after normalization      | Valid          | Keep (subject to dedup)                  | R7   |
| `title` absent or empty after normalization            | Invalid        | Skip (drop), count as `skipped_invalid`  | R7,R8|
| Optional field absent/empty                            | Valid          | Field set to null                        | R11  |
| `detail_url` href absent, empty, or whitespace-only    | Valid          | `detail_url` set to null; not eligible for dedup | R9, 2.2 |
| Duplicate `detail_url` (non-null) of an earlier record | Valid-but-dup  | Skip later copy, count as `skipped_duplicate` | R9 |
| Card with no recognized fields at all                  | Invalid        | Skip (title is absent → invalid)         | R7,R8|
| Page with zero cards                                   | n/a            | Contributes zero records; not an error   | R12  |

No record is silently altered beyond R6 normalization. There is no "quarantine"
output in the MVP; invalid and duplicate records are dropped and only reflected
in counts (section 7).

---

## 6. CLI contract

### 6.1 Entry point
- The scraper is exposed through the console-script entry point declared in
  `pyproject.toml` `[project.scripts]`:
  `web-scraper = "web_scraper.main:main"`. Invoked as `web-scraper`
  (or `uv run web-scraper`).

### 6.2 Arguments
| Argument        | Required | Type   | Default            | Meaning                                                        |
|-----------------|----------|--------|--------------------|----------------------------------------------------------------|
| `--input`       | Yes      | path   | —                  | Path to the first listing-page HTML fixture file (page 1).     |
| `--output-dir`  | Yes      | path   | —                  | Directory to write the JSONL and CSV output files into.        |
| `--max-pages`   | No       | int    | `10`               | Maximum number of pages to process (page 1 inclusive). Must be an integer `>= 1`. |
| `--jsonl-name`  | No       | string | `listings.jsonl`   | Filename of the JSONL output file, written into `--output-dir`. Plain filename only. |
| `--csv-name`    | No       | string | `listings.csv`     | Filename of the CSV output file, written into `--output-dir`. Plain filename only. |

- `--input` must point to an existing, readable file. The directory of this file
  is the base for resolving pagination `href`s (R3).
- `--max-pages` less than 1 or non-integer is an argument error (exit code 2,
  section 6.4).
- `--jsonl-name` and `--csv-name` must be plain filenames with no directory
  component. Each is validated by the **platform-independent filename validity
  rule in section 3.1**: a value is an argument error (exit code 2, section 6.4)
  if it is empty or whitespace-only; or equals `.` or `..`; or contains `/` or
  `\` (both checked unconditionally on all platforms, including POSIX); or
  otherwise differs from `os.path.basename(name)`. The two names must also differ
  from each other; if they are equal it is an argument error (exit code 2),
  because the two files would otherwise overwrite each other.

### 6.3 Idempotency / rerun behavior
- Overwrite semantics (R14): each run replaces output files; never appends.
- Reruns with identical inputs/arguments are byte-identical (R15).

### 6.4 Exit codes
| Code | Condition                                                                 |
|------|---------------------------------------------------------------------------|
| 0    | Run completed; output files written. Includes the zero-records case AND the case where pagination stopped early because a next-page reference was broken/missing/unreadable/non-UTF-8 (R13a, decision 2). |
| 2    | Invalid command-line arguments: missing required arg, `--max-pages < 1` or non-integer, unknown flag, a `--jsonl-name`/`--csv-name` that is empty or whitespace-only, equal to `.`/`..`, containing `/` or `\` (checked on all platforms), or otherwise not equal to its own `os.path.basename` (section 3.1 rule), or `--jsonl-name` equal to `--csv-name`. This is the standard argparse usage-error code. |
| 1    | Runtime failure of the **first** page or of output writing only: the `--input` file does not exist / is not readable / is not valid UTF-8; or the output directory cannot be created or written. A broken/missing/unreadable/non-UTF-8 **next-page** file is NOT a failure — it stops pagination gracefully with exit 0 (R13a). |

- On a non-zero exit, no partial/corrupt output files are left in a state that a
  consumer could mistake for a successful run: if writing fails mid-way, the run
  exits with code 1 and the partially written file(s) are removed or truncated
  before exit.

### 6.5 Run summary (stdout)
On exit code 0, the CLI prints exactly one line to stdout (LF-terminated)
summarizing counts, in this exact format:
```
pages=<P> cards=<C> written=<W> skipped_invalid=<I> skipped_duplicate=<D>
```
where `<P>` pages processed, `<C>` total cards seen, `<W>` records written,
`<I>` invalid skipped (R8), `<D>` duplicates skipped (R9), and
`<C> = <W> + <I> + <D>`. All five values are non-negative integers.

---

## 7. Error handling and edge cases

| Case                                   | Behavior                                                                 | Rule / Exit |
|----------------------------------------|--------------------------------------------------------------------------|-------------|
| `--input` (first page) file missing/unreadable/non-UTF-8 | No output written; exit code 1; error message to stderr.      | 6.4, R2     |
| Output dir missing                     | Created (with parents); run proceeds.                                    | 3.6         |
| Empty page (no `listing-card`)         | Zero records from that page; pagination still followed.                  | R12         |
| Card missing an optional field         | That field is null (JSONL) / empty (CSV).                                | R11         |
| Card missing title                     | Record skipped, counted as `skipped_invalid`.                           | R7, R8      |
| `detail_url` href empty or whitespace-only | `detail_url` is null; record kept (if title valid); not eligible for dedup. | 2.2, R9, F1.10 |
| Nested `listing-card` (card inside a card) | Inner card ignored; only top-level cards are cards. Unsupported input.   | 2.2, non-goals |
| Malformed HTML (unclosed tags, etc.)   | Best-effort parse via `BeautifulSoup(html, "html.parser")`; cards still matched by class; no crash. Unrecognizable fragments yield absent fields (null), not an abort. | R5, R6 |
| No cards anywhere across all pages      | Output: empty JSONL, CSV with header-only exact bytes (3.5); exit 0; summary `written=0`. | 3.1, 3.5, 6.5 |
| Duplicate `detail_url` across pages     | Later copy skipped, counted as `skipped_duplicate`.                     | R9          |
| Pagination end (no next link)           | Run stops normally after current page.                                  | R3, R13     |
| `--max-pages` reached before end        | Run stops after that many pages; remaining pages ignored; exit 0.       | R4          |
| Next-page `href` → missing/unreadable/non-UTF-8 file | Pagination stops gracefully; current page treated as last; records so far written; **exit 0**. | R13a (decision 2) |
| Next-page `href` is a full URL or absolute path | Treated as broken reference; pagination stops gracefully; **exit 0**. | R3, R13a |
| Next-page `href` has `?query`/`#fragment` | Stripped before resolving to a local path.                             | R3          |

---

## 8. Acceptance criteria

Each AC is written Given/When/Then with concrete data and is unit-testable
against the pure parse/output functions (R16) or the CLI.

### AC1 — Parse a single valid card (R5, R6, R7, R11)
- **Given** the HTML:
  ```html
  <article class="listing-card">
    <h2 class="listing-title">  Cozy   Downtown
      Apartment </h2>
    <span class="listing-price">€250,000</span>
    <span class="listing-location">Rivertown, Dockside</span>
    <span class="listing-rooms">3 rooms</span>
    <span class="listing-area">72 m²</span>
    <a class="listing-link" href="/detail/123">View details</a>
  </article>
  ```
- **When** the page is parsed.
- **Then** exactly one record is produced:
  ```json
  {"title": "Cozy Downtown Apartment", "price": "€250,000", "location": "Rivertown, Dockside", "rooms": "3 rooms", "area": "72 m²", "detail_url": "/detail/123"}
  ```
  Note the title’s internal whitespace run (spaces + newline + indentation) is
  collapsed to single spaces and trimmed (R6).

### AC2 — JSONL serialization of two records (section 3.4)
- **Given** the two cards of the canonical fixture in 2.3.
- **When** the records are written to `listings.jsonl`.
- **Then** the file contains exactly two LF-terminated lines, in card order:
  ```
  {"title": "Cozy Downtown Apartment", "price": "€250,000", "location": "Rivertown, Dockside", "rooms": "3 rooms", "area": "72 m²", "detail_url": "/detail/123"}
  {"title": "Seaside Studio", "price": "€180,000", "location": "Lakeside", "rooms": "1 room", "area": "28 m²", "detail_url": "/detail/124"}
  ```
  with UTF-8 encoding and non-ASCII characters preserved (`€`, `²`).

### AC3 — CSV serialization with quoting (section 3.5)
- **Given** the same two records as AC2.
- **When** they are written to `listings.csv`.
- **Then** the file is exactly (LF line endings, header first):
  ```csv
  title,price,location,rooms,area,detail_url
  Cozy Downtown Apartment,"€250,000","Rivertown, Dockside",3 rooms,72 m²,/detail/123
  Seaside Studio,"€180,000",Lakeside,1 room,28 m²,/detail/124
  ```
  `"€250,000"` and `"Rivertown, Dockside"` are quoted because they contain commas;
  other fields are unquoted.

### AC4 — Missing optional field becomes null/empty (R11)
- **Given** the HTML:
  ```html
  <article class="listing-card">
    <h2 class="listing-title">No Price Listing</h2>
    <span class="listing-location">Hillcrest</span>
    <a class="listing-link" href="/detail/200">View</a>
  </article>
  ```
  (no `listing-price`, `listing-rooms`, or `listing-area`).
- **When** parsed and written.
- **Then** the JSONL line is:
  ```json
  {"title": "No Price Listing", "price": null, "location": "Hillcrest", "rooms": null, "area": null, "detail_url": "/detail/200"}
  ```
  and the CSV data row is:
  ```csv
  No Price Listing,,Hillcrest,,,/detail/200
  ```

### AC5 — Invalid record (missing title) skipped (R7, R8)
- **Given** a page with two cards, the first missing a `listing-title`:
  ```html
  <article class="listing-card">
    <span class="listing-price">€99,000</span>
    <a class="listing-link" href="/detail/300">View</a>
  </article>
  <article class="listing-card">
    <h2 class="listing-title">Valid One</h2>
    <a class="listing-link" href="/detail/301">View</a>
  </article>
  ```
- **When** the page is scraped.
- **Then** only one record is written (`title = "Valid One"`), and the run
  summary reports `cards=2 written=1 skipped_invalid=1 skipped_duplicate=0`.

### AC6 — Empty-after-trim title is invalid (R6, R7)
- **Given** a card whose title element is `<h2 class="listing-title">   </h2>`.
- **When** parsed.
- **Then** the record is invalid and skipped; it is counted in
  `skipped_invalid`.

### AC7 — De-duplication by detail_url across pages (R9, R10)
- **Given** page 1 contains a card with `href="/detail/400"` (title "A") and
  page 2 contains a card with the same `href="/detail/400"` (title "A-again").
- **When** both pages are scraped in order.
- **Then** only the page-1 record (title "A") is written; the page-2 copy is
  skipped and counted in `skipped_duplicate`. Output order keeps "A" before any
  later records.

### AC8 — Null detail_url records are never deduplicated (R9)
- **Given** two valid cards that both lack a `listing-link` (so `detail_url` is
  null) but have titles "X" and "Y".
- **When** scraped.
- **Then** both records are written (`skipped_duplicate=0`).

### AC9 — Pagination follows next link, respects max-pages (R3, R4)
- **Given** `page1.html` with one card and
  `<a class="pagination-next" href="page2.html">`, and `page2.html` with one
  card and `<a class="pagination-next" href="page3.html">`, and `page3.html`
  with one card and no next link; `--input` points to `page1.html`.
- **When** run with `--max-pages 2`.
- **Then** only pages 1 and 2 are processed; the summary reports `pages=2`,
  `cards=2`, `written=2`; page 3 is not read.

### AC10 — End of pagination with no max-pages limit (R3, R13)
- **Given** the three-page fixture of AC9.
- **When** run with the default `--max-pages 10`.
- **Then** all three pages are processed (`pages=3`, `written=3`) and the run
  stops after page 3 because it has no next link.

### AC11 — Empty page contributes nothing but is counted (R12)
- **Given** a page whose body has no `listing-card` element but has a
  `pagination-next` link to a page with one card.
- **When** scraped with `--max-pages 10`.
- **Then** `pages=2`, `cards=1`, `written=1`; the empty page contributes zero
  records and raises no error.

### AC12 — Zero records overall produces header-only CSV and empty JSONL (3.1, 3.5, F1.11)
- **Given** a single page with no cards and no next link.
- **When** scraped.
- **Then** the JSONL output file is a zero-byte / zero-line file; the CSV output
  file contains **exactly** the bytes `title,price,location,rooms,area,detail_url`
  followed by a single LF (`\n`) — 43 bytes total, no BOM, no second line, no
  trailing blank line; the exit code is 0; and the summary reports `written=0`.

### AC13 — Idempotent rerun is byte-identical (R14, R15)
- **Given** any fixture set and fixed arguments.
- **When** the scraper is run twice into the same `--output-dir`.
- **Then** the JSONL and CSV output files from both runs are byte-identical
  (including the header-only CSV being exactly the 43 bytes of AC12 when
  `written=0`), and the second run overwrites (does not append to) the first.

### AC14 — Missing input file exits non-zero (6.4)
- **Given** `--input` pointing to a path that does not exist.
- **When** the CLI runs.
- **Then** no output files are written and the process exits with code 1.

### AC15 — Invalid `--max-pages` is a usage error (6.2, 6.4)
- **Given** `--max-pages 0`.
- **When** the CLI runs.
- **Then** the process exits with code 2 and writes no output files.

### AC16 — Missing next-page file stops gracefully with exit 0 (R13a, decision 2)
- **Given** `page1.html` with one valid card (title "A", `href="/detail/900"`)
  and `<a class="pagination-next" href="page2.html">`, where `page2.html` does
  **not** exist in `page1.html`'s directory; `--input` points to `page1.html`;
  default `--max-pages 10`.
- **When** the CLI runs.
- **Then** pagination stops gracefully after page 1, the exit code is **0**, the
  summary reports `pages=1 cards=1 written=1 skipped_invalid=0
  skipped_duplicate=0`, and the output files contain exactly the one page-1
  record. The same outcome (exit 0, page-1 output) holds when `page2.html` exists
  but is unreadable, or when it contains non-UTF-8 bytes (R13a).

### AC17 — Empty/whitespace-only href yields null detail_url, no dedup (2.2, R9, F1.10)
- **Given** two valid cards: the first has `<a class="listing-link" href="  ">`
  (whitespace-only href) with title "P"; the second has
  `<a class="listing-link" href="">` (empty href) with title "Q".
- **When** scraped.
- **Then** both records are written with `detail_url = null`, and
  `skipped_duplicate=0` (null `detail_url` records are never duplicates).

### AC18 — Configurable output filenames (3.1, 6.2, decision 4)
- **Given** the canonical two-card fixture of 2.3 and
  `--jsonl-name out.jsonl --csv-name out.csv`.
- **When** the CLI runs into `--output-dir`.
- **Then** the files `out.jsonl` and `out.csv` are created in `--output-dir`
  (not `listings.jsonl` / `listings.csv`), with the same byte content AC2/AC3
  prescribe for those two records.
- **And given** instead `--jsonl-name sub/out.jsonl` (contains `/`), **when** the
  CLI runs, **then** it exits with code 2 and writes no output files.
- **And given** instead `--jsonl-name out\back.jsonl` (contains `\`), **when** the
  CLI runs on **any** platform including POSIX, **then** it exits with code 2 and
  writes no output files (the `\` check is unconditional; section 3.1 rule 3).
- **And given** instead `--jsonl-name ""` (empty string), **when** the CLI runs,
  **then** it exits with code 2 and writes no output files (section 3.1 rule 1).
- **And given** instead `--csv-name "   "` (whitespace-only, three spaces),
  **when** the CLI runs, **then** it exits with code 2 and writes no output files
  (section 3.1 rule 1).
- **And given** instead `--jsonl-name .` (single dot), **when** the CLI runs,
  **then** it exits with code 2 and writes no output files (section 3.1 rule 2).
- **And given** instead `--jsonl-name ..` (double dot), **when** the CLI runs,
  **then** it exits with code 2 and writes no output files (section 3.1 rule 2).
- **And given** instead `--jsonl-name data.out --csv-name data.out` (equal
  names), **when** the CLI runs, **then** it exits with code 2 and writes no
  output files.

### AC19 — NBSP and mixed whitespace collapse in text fields (R6, F1.5)
- **Given** a card whose title element is
  `<h2 class="listing-title">&nbsp;Cozy&nbsp;&nbsp;Flat&nbsp;</h2>` (the
  `&nbsp;` entities decode to U+00A0).
- **When** parsed.
- **Then** the record's `title` is exactly `"Cozy Flat"` — leading/trailing NBSP
  trimmed and the internal NBSP run collapsed to a single ASCII space U+0020.

### AC20 — Next-page href with query/fragment and relative resolution (R3, F1.6)
- **Given** `a/page1.html` (under directory `a/`) with one card and
  `<a class="pagination-next" href="sub/page2.html?ref=1#top">`, and
  `a/sub/page2.html` with one card and no next link; `--input` points to
  `a/page1.html`; default `--max-pages`.
- **When** the CLI runs.
- **Then** the next page is resolved to
  `os.path.normpath(os.path.join("a", "sub/page2.html"))` (i.e. `a/sub/page2.html`,
  after stripping `?ref=1#top`), both pages are processed (`pages=2`,
  `written=2`).
- **And given** instead a `pagination-next` `href="https://example.com/page2"`
  (full URL) on page 1, **when** run, **then** pagination stops gracefully after
  page 1 with exit 0 (R3 step 2, R13a).

---

## 9. Non-functional requirements (measurable only)

All three performance/network NFRs below are **hard, deterministic unit tests**
run against a fixed on-disk fixture of exactly **10 pages × 50 cards = 500
candidate records**. As part of the (excluded) test setup, the 500-record
fixture is **materialized as 10 on-disk HTML files** (50 cards each) under a
pytest `tmp_path` temporary directory; the 10 files are linked in sequence by
`pagination-next` `href`s (page 1 → page 2 → … → page 10, where page 10 has no
next link; R3). The scrape is then run with `--input` pointing at page 1, so the
fetch layer genuinely performs local file reads and pagination following (R2,
R3) over real on-disk files. There is **no** in-memory-only fixture for these
NFRs; the only excluded work is writing those 10 fixture files and other pytest
`tmp_path` setup.

**Measured operation (one uniform scope for NFR1, NFR2, and NFR3).** The
measured operation is a **full scrape over the on-disk fixture set** — fetch
(local file reads + pagination following over the 10 on-disk files) + parse +
record-build + de-dup + serialize to JSONL+CSV bytes — excluding only the pytest
fixture-file materialization / tmp-path setup described above. NFR1, NFR2, and
NFR3 all measure this same full-scrape operation.

- **NFR1 — Throughput (hard test).** The **full scrape over the on-disk fixture
  set** (scope above) completes in **≤ 5 seconds**, measured with
  `time.perf_counter()` taken immediately before and after that full-scrape
  operation; the elapsed difference must be `≤ 5.0`. The threshold is
  intentionally generous for a standard CI runner so the test is not flaky
  (F1.7).
- **NFR2 — No network (hard test).** The MVP opens **zero** network sockets. This
  is verified by monkeypatching `socket.socket` to raise on any instantiation
  for the duration of the **full scrape over the on-disk fixture set** (scope
  above); the scrape must complete successfully with no socket ever constructed.
  Any network attempt would raise and fail the test (F1.12).
- **NFR3 — Memory bound (hard test).** Peak **additional heap** — defined as the
  peak traced allocation reported by `tracemalloc` (the second value of
  `tracemalloc.get_traced_memory()`) during the same **full scrape over the
  on-disk fixture set** (scope above), with `tracemalloc.start()` called
  immediately before and `tracemalloc.stop()` after — is **≤ 64 MB**
  (≤ 67,108,864 bytes) for the 500-record fixture (F1.7).
- **NFR4 — Encoding.** All output bytes are valid UTF-8 (no BOM); verifiable by
  decoding the output files as UTF-8 without error.
- **NFR5 — Determinism.** For identical inputs/arguments, output files are
  byte-identical across runs (also covered by AC13).

---

## 10. Open questions and assumptions

### Open questions (need user decision)
- **None.** All previously open questions (R-open-1, R-open-2, R-open-3) were
  resolved by the user's Round-2 binding decisions and are recorded as closed
  below and in the revision log.

### Closed questions (resolved in Round 2)
- **R-open-1 — Provenance field: CLOSED / EXCLUDED.** No provenance field is
  added. The output schema stays exactly six fields (section 3.3). (Decision 3.)
- **R-open-2 — Broken/missing next-page file: CLOSED.** All next-page failure
  modes (missing, unreadable, non-UTF-8, or a broken reference such as a full URL
  or absolute path) stop pagination **gracefully with exit 0**, treating the
  current page as the last page and writing records collected so far (R13a,
  section 6.4, section 7, AC16). (Decision 2.)
- **R-open-3 — Output file names: CLOSED / CONFIGURABLE.** Output filenames are
  configurable via `--jsonl-name` (default `listings.jsonl`) and `--csv-name`
  (default `listings.csv`), both plain filenames in `--output-dir`. A name that
  is empty/whitespace-only, equal to `.`/`..`, contains `/` or `\` (checked on
  all platforms), or otherwise differs from its own `os.path.basename` (the §3.1
  filename validity rule), or equals the other name, is an argument error
  (exit 2) (sections 3.1, 6.2, 6.4, AC18). (Decision 4.)

### Assumptions (used so the spec is complete and testable)
- **A1.** `detail_url` is stored exactly as the raw `href` value, not R6-normalized
  and not resolved to an absolute URL (R6, R9, F1.3).
- **A2.** De-duplication uses only the raw `detail_url` string; null-URL records
  (absent, empty, or whitespace-only href) are always kept (R9, F1.10).
- **A3.** HTML parsing uses `BeautifulSoup(html, "html.parser")` with the stdlib
  backend; "element text content" is bs4 `get_text()` (decision 1).
- **A4.** Whitespace normalization for text fields follows `" ".join(text.split())`
  semantics, which treats NBSP U+00A0 as whitespace (R6, F1.5).
- **A5.** Only one site layout (section 2.2) is supported in the MVP; nested
  `listing-card` elements are unsupported and only top-level cards are treated as
  cards (section 2.2, non-goals).

---

## 11. Revision log

### Round 1 — Initial draft (self-consistency pass)
- **RL-1 (CONTRADICTION fixed).** Section 6.4/section 7 initially implied a
  missing next-page file is always a runtime failure (exit 1), while pagination
  handling needed a graceful end-of-pages behavior. Resolved by adopting
  assumption A3 (stop gracefully, exit 0) as the governing behavior and flagging
  the exit-1 wording as tentative/superseded, and by raising R-open-2 for the
  user to confirm. The two passages no longer prescribe conflicting outcomes: A3
  governs; R-open-2 tracks the final decision.
- **RL-2 (CSV example corrected).** An illustrative CSV snippet in section 3.5
  showed `Rivertown, Dockside` unquoted, which contradicted the minimal-quoting rule
  in the same section. The authoritative, correctly quoted CSV is given in AC3,
  and section 3.5 now explicitly notes the quoting of `"Rivertown, Dockside"`.
- **RL-3 (consistency check passed).** Verified field order (section 3.3) matches
  JSONL (3.4), CSV header (3.5), and all ACs; counts identity
  `cards = written + skipped_invalid + skipped_duplicate` (6.5) is consistent
  with AC5; `--max-pages` default (10) is consistent across 2.4, 6.2, AC9, AC10,
  and NFR1.

### Round 2 — test-engineer findings (13) + user binding decisions

User decisions baked in: (1) parser = beautifulsoup4 with `"html.parser"`,
`get_text()` text content; (2) broken/missing/unreadable/non-UTF-8 next-page →
stop gracefully, exit 0; (3) no provenance field; (4) configurable output
filenames `--jsonl-name` / `--csv-name`; (5) NFR1/NFR2/NFR3 as hard deterministic
unit tests with specified fixture scale and measurement method.

- **F1.1 (CONTRADICTION fixed).** Removed the literally-incorrect unquoted
  `Rivertown, Dockside` illustrative CSV row from section 3.5. AC3 is now the single
  authoritative CSV example; section 3.5 explicitly defers to it.
- **F1.2 (CONTRADICTION fixed).** Unified all next-page failure modes to exit 0
  (graceful stop) across R13a, section 6.4, and section 7; removed the
  conflicting exit-1 wording for next-page files. Exit 1 now applies only to the
  first (`--input`) page and to output-write failures.
- **F1.3 (CONTRADICTION/AMBIGUITY resolved).** Stated that `detail_url` stores the
  raw `href` exactly as-is (no R6 normalization) and that this exact string is the
  byte-for-byte dedup key; R6 scope restricted to the five text fields (sections
  3.3, R6, R9).
- **F1.4 (AMBIGUITY fixed).** Defined "element text content" precisely as bs4
  `get_text()` with `separator=""` over all descendant text nodes in document
  order, then R6 normalization (section 2.2).
- **F1.5 (AMBIGUITY fixed).** Defined whitespace handling as `" ".join(text.split())`,
  using one identical Unicode-whitespace set for both trim and collapse;
  enumerated the code points and stated NBSP U+00A0 is treated as whitespace and
  collapsed (R6, AC19).
- **F1.6 (AMBIGUITY fixed).** Specified href→path resolution: strip `?query`/`#fragment`,
  then `os.path.normpath(os.path.join(current_page_dir, href))`; full URLs and
  absolute paths are broken references → stop gracefully; self/loop references
  bounded only by `--max-pages` (R3, AC20).
- **F1.7 (addressed by decision 5).** Made NFR1 (`time.perf_counter()`, ≤5s) and
  NFR3 (`tracemalloc` peak, ≤64 MB) hard tests over a 500-record (10×50) fixture;
  defined "additional heap" as tracemalloc peak during the operation (section 9).
- **F1.8 (addressed by decision 1).** Pinned beautifulsoup4 + `"html.parser"` as a
  runtime dependency; malformed-HTML handling and text extraction are now
  deterministic (header note, section 2.2, section 7).
- **F1.9 (addressed by decision 2).** Added AC16 for a missing (and unreadable /
  non-UTF-8) next-page file: exit 0 with output for prior pages.
- **F1.10 (AMBIGUITY fixed).** Defined empty-string and whitespace-only `href` as
  yielding `detail_url = null`, not eligible for dedup; added section 2.2 rule,
  a data-quality row (section 5), and AC17.
- **F1.11 (AMBIGUITY fixed).** Pinned the exact header-only CSV bytes:
  `title,price,location,rooms,area,detail_url` + one LF (43 bytes, no BOM, no
  trailing blank line); aligned sections 3.5, AC12, AC13.
- **F1.12 (addressed by decision 5).** Specified NFR2's mechanism: monkeypatch
  `socket.socket` to raise on instantiation so any network attempt fails the test
  (section 9).
- **F1.13 (AMBIGUITY fixed).** Defined that only top-level `listing-card` elements
  (no `listing-card` ancestor) are treated as cards; nested cards are unsupported
  input and added to non-goals (section 2.2, section 1, section 7).
- **R-open-1/2/3 closed** per decisions 3/2/4 (section 10).
- **RL-4 (self-consistency pass, Round 2).** Re-verified: 6-field order identical
  across 3.3/3.4/3.5/all ACs; count identity `cards = written + skipped_invalid +
  skipped_duplicate` holds (AC5, AC16, AC17); exit codes consistent (0 graceful /
  1 first-page+write / 2 args) across 6.4, 7, AC14–AC18; CLI args (`--input`,
  `--output-dir`, `--max-pages`, `--jsonl-name`, `--csv-name`) consistent across
  3.1, 6.2, 6.4, AC18; every new rule (R13a) and field behavior has a covering AC
  and vice versa. No remaining contradictions found.

### Round 3 — test-engineer round-2 findings (4)

- **F2.1 (AMBIGUITY fixed).** An empty-string or whitespace-only `--jsonl-name` /
  `--csv-name` is now an argument error (exit 2). Added as rule 1 of the §3.1
  filename validity rule, referenced in §6.2 and the §6.4 exit-2 list, and
  covered by two new AC18 branches (`--jsonl-name ""` and `--csv-name "   "`).
- **F2.2 (AMBIGUITY fixed).** Made filename validation platform-independent and
  deterministic. Replaced the enumerated/platform-dependent separator wording with
  a single precise §3.1 rule: a name is rejected (exit 2) if it is empty or
  whitespace-only, equals `.` or `..`, contains `/` or `\` (both checked
  unconditionally on all platforms including POSIX), or otherwise differs from
  `os.path.basename(name)`. Updated §3.1, §6.2, and §6.4 to the same wording;
  the `\` branch now has a pinned expected result (exit 2) on POSIX, covered by a
  new AC18 branch.
- **F2.3 (traceability fixed).** Added AC18 branches pinning `--jsonl-name .` and
  `--jsonl-name ..` → exit 2 with no output files (traces to §3.1 rule 2 / §6.4).
- **F2.4 (AMBIGUITY fixed).** Defined one uniform measured-operation scope for
  NFR1/NFR2/NFR3: a **full scrape over the fixture set** — fetch (local file reads
  + pagination following) + parse + record-build + de-dup + serialize to
  JSONL+CSV bytes — excluding only pytest fixture / tmp-path setup. Rewrote the §9
  opener and NFR1/NFR2/NFR3 so all three reference this identical phrasing.
- **RL-5 (self-consistency pass, Round 3).** Re-verified: 6-field order identical
  across 3.3/3.4/3.5/all ACs; count identity `cards = written + skipped_invalid +
  skipped_duplicate` unchanged (AC5, AC16, AC17); exit codes consistent
  (0 graceful / 1 first-page+write / 2 args) across 6.4, 7, AC14–AC18; the §3.1
  filename validity rule is stated once and referenced identically by §6.2, §6.4,
  and AC18; CLI args unchanged and consistent across 3.1, 6.2, 6.4, AC18; the
  single NFR scope wording is identical in the §9 opener and NFR1/NFR2/NFR3. No
  remaining contradictions found.

### Round 4 — test-engineer round-3 findings (1)

- **F3.1 (CONTRADICTION fixed).** The §9 opener previously allowed the 500-record
  NFR fixture to be "built in-memory (or read from committed fixture files)",
  which contradicted the F2.4 measured-operation scope requiring the operation to
  include "fetch (local file reads + pagination following)" — an in-memory
  fixture has no files and cannot exercise local file reads or pagination,
  leaving NFR1/NFR3 non-deterministic. Resolved by removing the in-memory option
  entirely: the §9 opener now mandates that, as part of the (excluded) test
  setup, the 500-record fixture is **materialized as 10 on-disk HTML files**
  (50 cards each) linked by `pagination-next` under a pytest `tmp_path`, with the
  scrape run via `--input` pointing at page 1. The measured window is the full
  scrape (fetch local files + pagination + parse + dedup + serialize) over those
  on-disk files; only the fixture-file materialization / tmp-path setup is
  excluded. NFR1, NFR2, and NFR3 now all reference the "full scrape over the
  on-disk fixture set" with no residual "in-memory" wording. Thresholds
  (≤ 5.0 s / ≤ 64 MB) and measurement tools (`time.perf_counter`, `tracemalloc`
  peak, `socket.socket` monkeypatch) are unchanged. This aligns with R2 (fetch
  reads HTML from a local file path) and R3 (pagination href→path resolution).
- **RL-6 (self-consistency pass, Round 4).** Re-verified after the F3.1 fix: the
  §9 opener, NFR1, NFR2, and NFR3 all describe the identical on-disk-files scope
  ("full scrape over the on-disk fixture set") with no "in-memory" wording
  remaining anywhere in §9; the on-disk 10-file / 50-card / `pagination-next`
  fixture is consistent with R2 (local-file fetch), R3 (pagination discovery and
  href→path resolution), and §2.4 volume bounds (≤ 10 pages, ≤ 50 cards/page,
  ≤ 500 records); 6-field order, the count identity, exit-code semantics, and the
  §3.1 filename validity rule are all unchanged from Round 3. No remaining
  contradictions found.

### Round 5 — test-engineer round-4 finding (1, advisory)

- **RL-7 (documentation-only clarification, no behavior change).** The reviewer
  flagged (advisory, not a defect) that R3 resolves a pagination `href` via
  `os.path.normpath(os.path.join(current_page_dir, stripped_path))` with **no**
  containment, so a crafted relative `href` such as `../../../../etc/passwd`
  could make the fetch layer read a file outside the `--input` file's directory.
  This is intentional for the trusted-local-fixtures MVP (URLs and absolute
  paths are already rejected by R3; read-only; UTF-8-only; only listing-card data
  surfaced), but was previously undocumented. Resolved by making it an explicit
  non-goal: added a Non-goals bullet in §1 stating that containment/sandboxing of
  resolved pagination paths is out of scope (a later extension could restrict
  resolved paths to under the input directory), and added a cross-referencing
  one-line note under R3. **No behavior change**: R3 step 3 resolution,
  R3 step 2 rejection of URLs/absolute paths, exit codes (0/1/2), data-quality
  rules, and all acceptance criteria (AC1–AC20) are unchanged. No AC was added,
  removed, or modified.
- **RL-7 self-consistency pass (Round 5).** Re-verified after the
  documentation-only edit: the new §1 non-goal and the R3 note agree with the
  existing R3 resolution steps (strip query/fragment → reject empty/URL/absolute
  → `normpath(join(...))`) and introduce no new behavior; the 6-field order,
  the count identity `cards = written + skipped_invalid + skipped_duplicate`,
  exit-code semantics (0 graceful / 1 first-page+write / 2 args), the §3.1
  filename validity rule, and NFR scope wording are all unchanged from Round 4.
  No contradictions introduced.
