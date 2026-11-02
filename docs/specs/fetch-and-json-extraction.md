# Functional specification: Fetch stage and embedded-JSON extraction

Status: Draft (round 1)
Feature file: `docs/specs/fetch-and-json-extraction.md`
Applies to package: `src/web_scraper/`

> Companion to [docs/specs/web-scraper.md](web-scraper.md) (the HTML-card
> parser). This plain Python package (hatchling + uv, Python `>=3.12`) is not a
> Databricks bundle. These two commands extend the project with a network
> download stage and an alternative parser for single-page-app sites whose
> listings are embedded as JSON. All examples use generic placeholders
> (`https://example.com`, generic JSON keys); no real site is assumed.

---

## 1. Purpose and scope

### Purpose
Provide two companion command-line tools:
1. `web-scraper-fetch` — download a single web page over HTTP(S) and save its raw
   body to a local file (stage 1), so parsing stays deterministic and offline.
2. `web-scraper-json` — parse listings from a saved HTML file whose data is
   embedded as a JavaScript `window.__INITIAL_STATE__` object (single-page-app
   sites), mapping them, via a caller-supplied profile, onto the same six-field
   record schema and JSONL/CSV output as the HTML parser.

### In scope
- A thin HTTP(S) GET to a file (`web-scraper-fetch`).
- Extraction of a `window.__INITIAL_STATE__` object, tolerating the JS literal
  `undefined`, and config-driven mapping to records (`web-scraper-json`).

### Non-goals (explicit)
- No retries, rate limiting, caching, or `robots.txt` enforcement in the fetch
  stage. **The operator is responsible for honoring each target site's
  `robots.txt` AND terms of service.** `robots.txt` permission is not
  terms-of-service permission.
- No JavaScript execution / headless rendering.
- No crawling or pagination: `web-scraper-fetch` downloads one URL per run;
  `web-scraper-json` parses exactly one saved file's embedded state per run.
- Only the `window.__INITIAL_STATE__` marker is supported; other markers
  (e.g. `__NEXT_DATA__`, `__NUXT__`, JSON-LD) are out of scope.
- No semantic validation of fields: the profile author decides which source key
  maps to `price`, `area`, etc.; the tool does not interpret meaning.
- No built-in site profile ships with the tool.

---

## 2. Inputs

### 2.1 `web-scraper-fetch`
- `--url` (string, required): the page URL. Must begin with `http://` or
  `https://`; any other scheme is an argument error (§6, exit 2).
- `--output` (path, required): file to write the decoded body to.
- `--user-agent` (string, optional): request User-Agent; a non-empty default is
  sent when omitted.
- `--timeout` (float seconds, optional): socket timeout; a positive default is
  used when omitted.

### 2.2 `web-scraper-json`
- `--input` (path, required): a saved HTML file containing a
  `window.__INITIAL_STATE__ = {…}` assignment, UTF-8.
- `--output-dir` (path, required): output directory (created if missing).
- `--profile` (path, **required**): a JSON profile (§2.3). There is no default.
- `--jsonl-name` / `--csv-name` (optional): output filenames, validated by the
  same rule as [web-scraper.md §3.1/§6.2](web-scraper.md) (reject empty/whitespace,
  `.`/`..`, names containing `/` or `\`, names differing from their basename, or
  the two names being equal → exit 2). Defaults `listings.jsonl` / `listings.csv`.

### 2.3 Profile schema (JSON object)
| Key                   | Type                     | Required | Meaning                                                            |
|-----------------------|--------------------------|----------|--------------------------------------------------------------------|
| `state_path`          | string (dotted)          | Yes      | Path to the listings array inside the state, e.g. `data.results.items`. |
| `fields`              | object (string→string)   | No       | Map of output field → source key. Keys are a subset of the six-field schema. |
| `detail_url_template` | string or null           | No       | A `str.format` template using `{value}`, e.g. `https://example.com/listing/{value}`. |
| `detail_url_field`    | string or null           | No       | Source key whose value fills `{value}`.                            |

A profile missing `state_path`, or that is not a JSON object, is invalid
(§6, exit 1).

### 2.4 Embedded-state format
The input HTML contains the substring `window.__INITIAL_STATE__ = ` followed by a
balanced `{…}` JSON-like object. The object may contain the bare JavaScript
literal `undefined` as a value (not valid JSON); it is treated as `null` (R3).

---

## 3. Outputs

`web-scraper-json` writes `listings.jsonl` and `listings.csv` into `--output-dir`
using the **identical format, field order, encoding, and quoting** defined in
[web-scraper.md §3](web-scraper.md): six columns `title, price, location, rooms,
area, detail_url`, UTF-8, JSONL one object per line (LF after every line, keys in
field order, nulls as JSON `null`), CSV with header and minimal quoting, empty
fields for nulls. Records are written in the order listings appear in the array.

`web-scraper-fetch` writes the decoded response body verbatim to `--output` as
UTF-8.

---

## 4. Business rules

- **R1 — Fetch is GET-to-file.** `web-scraper-fetch` performs a single HTTP(S)
  GET with the configured User-Agent and timeout and writes the decoded body to
  `--output`. It performs no other network I/O.
- **R2 — Scheme restriction.** Only `http://` and `https://` URLs are accepted;
  any other scheme (e.g. `file://`) is rejected before any request is made
  (§6, exit 2), preventing local-file or non-HTTP access.
- **R3 — Decoding.** The response body is decoded using the HTTP response
  charset when present, otherwise UTF-8, replacing undecodable bytes; the output
  file is written UTF-8.
- **R4 — State location.** `web-scraper-json` finds the first occurrence of
  `window.__INITIAL_STATE__ = ` and parses the balanced `{…}` object that
  follows. If the marker is absent, it is an extraction error (exit 1).
- **R5 — Balanced-object scan.** The object spans from its opening `{` to the
  matching `}` at depth zero, tracking string literals and escapes so braces
  inside strings do not affect nesting. An unterminated object is an error.
- **R6 — `undefined` handling.** A bare token `undefined` that appears **outside
  any string value** is rewritten to `null`; an occurrence inside a string value
  is left unchanged. The cleaned text is parsed as JSON.
- **R7 — Listings selection.** `state_path` is split on `.` and navigated through
  nested objects. A missing segment, or a terminal value that is not an array, is
  an error (exit 1).
- **R8 — Field mapping.** For each array entry that is an object, each output
  field in `fields` is set to the string form of the source key's value, or
  `null` when the key is absent or its value is `null`. Booleans map to the
  strings `"true"`/`"false"`. Non-object entries are skipped.
- **R9 — Detail URL.** When both `detail_url_template` and `detail_url_field` are
  present and the field's value is neither absent, `null`, nor empty string,
  `detail_url` = `template.format(value=<field value>)`; otherwise `detail_url`
  is `null`.
- **R10 — Record shape.** A record contains the keys named in `fields` plus
  `detail_url`. The output writers pad any of the six schema columns not present
  in a record with `null` (JSONL) / empty (CSV), per [web-scraper.md §3](web-scraper.md).
- **R11 — Atomic output.** `web-scraper-json` writes both output files to temp
  files in `--output-dir`, then `os.replace`s them into their final names only
  after both writes succeed. On any OS error it removes committed finals and temp
  files so no partial or looks-successful output remains (exit 1).
- **R12 — Idempotency.** Re-running either command with the same inputs produces
  the same output and overwrites prior output; neither appends.

---

## 5. Data quality rules

| Condition                                             | Classification | Action                        | Rule |
|-------------------------------------------------------|----------------|-------------------------------|------|
| Array entry is a JSON object                          | Valid          | Mapped to a record            | R8   |
| Array entry is not an object (string/number/null)     | Invalid        | Skipped                       | R8   |
| Source key absent or `null`                           | Valid          | Field set to `null`           | R8   |
| `detail_url_field` absent/`null`/empty                | Valid          | `detail_url` set to `null`    | R9   |
| `state_path` missing or not an array                  | Error          | Exit 1                        | R7   |
| Marker absent / object unbalanced / unparseable       | Error          | Exit 1                        | R4,R5 |

There is no quarantine output; invalid entries are silently skipped (they are not
counted separately in the MVP).

---

## 6. CLI contract

### 6.1 `web-scraper-fetch`
- Entry point: `web-scraper-fetch = "web_scraper.download:main"`.
- On success prints `saved <N> characters to <path>` and exits 0.
- Exit codes: 0 success; 1 fetch failure (URL/network error) or write failure;
  2 argument error (missing required arg, non-http(s) scheme).

### 6.2 `web-scraper-json`
- Entry point: `web-scraper-json = "web_scraper.jsoncli:main"`.
- On success prints `listings=<N> written=<N>` and exits 0 (`<N>` = records
  written; invalid/skipped entries are not included).
- Exit codes: 0 success; 1 unreadable input, invalid/unloadable profile,
  extraction/selection failure, or output write failure; 2 argument error
  (missing `--input`/`--output-dir`/`--profile`, or invalid/duplicate output names).

---

## 7. Error handling and edge cases

| Case                                       | Behavior                                             | Rule / Exit |
|--------------------------------------------|------------------------------------------------------|-------------|
| `--url` not http(s)                        | No request; exit 2.                                  | R2 / 6.1    |
| Network/URL error                          | No output; stderr message; exit 1.                   | 6.1         |
| Output file unwritable (fetch)             | Exit 1.                                              | 6.1         |
| `--profile` missing on command line        | Argparse usage error; exit 2.                        | 6.2         |
| Profile file unreadable / not JSON / no `state_path` | stderr message; exit 1.                     | R7 / 6.2    |
| `__INITIAL_STATE__` marker absent          | Extraction error; exit 1.                            | R4          |
| Unbalanced `{…}`                           | Error; exit 1.                                       | R5          |
| `undefined` inside a string value          | Preserved verbatim (not rewritten).                  | R6          |
| `state_path` segment missing / not array   | Error; exit 1.                                       | R7          |
| Empty listings array                        | 0 records; empty JSONL, header-only CSV; exit 0.    | R10, 6.2    |
| Non-object array entry                      | Skipped.                                             | R8          |
| Output write fails mid-way                  | No partial/looks-successful files; exit 1.           | R11         |

---

## 8. Acceptance criteria

### AC1 — Fetch rejects non-http scheme (R2)
- **Given** `--url file:///etc/passwd --output out.html`.
- **When** `web-scraper-fetch` runs.
- **Then** it exits 2, performs no request, and writes no file.

### AC2 — Fetch saves decoded body (R1, R3)
- **Given** a mocked response body `"<html>€</html>"` (UTF-8).
- **When** fetched to `out.html`.
- **Then** exit 0 and `out.html` contains exactly `<html>€</html>`.

### AC3 — Bare `undefined` becomes null; in-string preserved (R6)
- **Given** `window.__INITIAL_STATE__ = {"note": "value is undefined here", "x": undefined};`.
- **When** the state is extracted.
- **Then** the parsed object equals `{"note": "value is undefined here", "x": null}`.

### AC4 — Balanced scan ignores trailing script (R5)
- **Given** `window.__INITIAL_STATE__ = {"a": {"b": 2}};window.OTHER = {"not": "mine"};`.
- **When** extracted.
- **Then** the result equals `{"a": {"b": 2}}`.

### AC5 — Mapping and detail URL (R7, R8, R9)
- **Given** state `{"data": {"results": {"items": [{"ref": "a1", "street": "1 Example Street", "cost": 47120.47}]}}}`
  and profile `{"state_path": "data.results.items", "fields": {"title": "street", "price": "cost"},
  "detail_url_template": "https://example.com/listing/{value}", "detail_url_field": "ref"}`.
- **When** parsed.
- **Then** the single record is
  `{"title": "1 Example Street", "price": "47120.47", "detail_url": "https://example.com/listing/a1"}`.

### AC6 — Missing source key → null; missing url field → null detail_url (R8, R9)
- **Given** one item `{"street": "Only Street"}` with profile fields `{"title": "street", "price": "cost"}`,
  `detail_url_field` `"ref"`.
- **When** mapped.
- **Then** the record is `{"title": "Only Street", "price": null, "detail_url": null}`.

### AC7 — `--profile` is required (6.2)
- **Given** `--input page.html --output-dir out` with no `--profile`.
- **When** `web-scraper-json` runs.
- **Then** it exits 2 and writes no output.

### AC8 — Missing marker → exit 1 (R4)
- **Given** an input file containing `<html>no state</html>`.
- **When** `web-scraper-json` runs with a valid profile.
- **Then** it exits 1 and writes no output.

### AC9 — End-to-end JSONL + CSV (R10, R11)
- **Given** a saved page whose state yields two items under `data.results.items`.
- **When** `web-scraper-json` runs with a matching profile.
- **Then** exit 0, prints `listings=2 written=2`, `listings.jsonl` has two lines,
  and `listings.csv` begins with `title,price,location,rooms,area,detail_url\n`.

### AC10 — Atomic failure leaves no output (R11)
- **Given** a run where the CSV write raises an OS error after the JSONL temp is
  written.
- **When** `web-scraper-json` runs.
- **Then** it exits 1 and neither final output file nor any `*.tmp` file remains
  in `--output-dir`.

### AC11 — Invalid output name → exit 2 (6.2)
- **Given** `--jsonl-name a/b.jsonl`.
- **When** `web-scraper-json` runs with an otherwise valid invocation.
- **Then** it exits 2 and writes no output.

---

## 9. Non-functional requirements (measurable only)

- **NFR1 — No network in the JSON stage.** `web-scraper-json` opens zero network
  sockets (it reads a local file only).
- **NFR2 — Determinism.** Given identical input file, profile, and arguments,
  `web-scraper-json` produces byte-identical output across runs.
- **NFR3 — Encoding.** All output bytes are valid UTF-8 (no BOM).
- **NFR4 — No new runtime dependency.** Both commands use only the standard
  library and the already-present `beautifulsoup4` is not required by them.

---

## 10. Open questions and assumptions

### Assumptions
- **A1.** The embedded object is JSON apart from bare `undefined` values; other
  JS-only constructs (functions, comments, single quotes, trailing commas) are
  not expected and would cause an extraction error (exit 1). This is acceptable
  for the MVP.
- **A2.** Numeric and boolean source values are acceptable as raw stringified
  output; no locale/number formatting is applied.
- **A3.** Skipped non-object entries are not separately counted in the MVP
  summary (`listings=<N> written=<N>` reflects records written).

### Open questions
- **Q1.** Should the JSON stage follow multi-page state (pagination) in a future
  version, and if so how is the next page's URL/path discovered? (Out of scope now.)
- **Q2.** Should additional embedded-state markers (`__NEXT_DATA__`, `__NUXT__`,
  JSON-LD) be supported via a configurable marker in the profile? (Out of scope now.)

---

## 11. Revision log

### Round 1 — Initial draft
- Documents the already-implemented `web-scraper-fetch` and `web-scraper-json`
  commands. Self-consistency pass: exit codes (0/1/2), the six-field schema, and
  output format are aligned with `docs/specs/web-scraper.md`; the JSON stage
  reuses that spec's filename-validation rule and JSONL/CSV format. No real site
  names, domains, or site-specific JSON keys are used. No contradiction with the
  HTML-parser spec was found (the JSON stage is an alternative input path to the
  same output contract).
