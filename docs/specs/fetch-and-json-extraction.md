# Functional specification: Fetch stage and raw embedded-JSON capture

Status: Draft (round 2)
Feature file: `docs/specs/fetch-and-json-extraction.md`
Applies to package: `src/web_scraper/`

> Companion to [docs/specs/web-scraper.md](web-scraper.md) (the HTML-card
> parser). This plain Python package (hatchling + uv, Python `>=3.12`) is not a
> Databricks bundle. These two commands extend the project with a network
> download stage and a **raw capture** stage for single-page-app sites whose
> listings are embedded as JSON. All examples use generic placeholders
> (`https://example.com`, generic JSON keys); no real site is assumed.

---

## 1. Purpose and scope

### Purpose
Provide two companion command-line tools that **capture raw data as-is** —
mapping to any particular model is intentionally left to a downstream consumer:
1. `web-scraper-fetch` — download a single web page over HTTP(S) and save its raw
   body to a local file.
2. `web-scraper-extract` — read a saved HTML file whose data is embedded as a
   JavaScript `window.__INITIAL_STATE__` object, and write the **original JSON**
   (the whole state, or a sub-node) to a file unchanged.

### Non-goals (explicit)
- **No mapping / normalization to a fixed model.** Both commands emit the raw
  bytes/JSON; shaping the data into a schema is a downstream concern.
- No retries, rate limiting, caching, or `robots.txt` enforcement. **The operator
  is responsible for honoring each target site's `robots.txt` AND terms of
  service.** `robots.txt` permission is not terms-of-service permission.
- No JavaScript execution / headless rendering.
- No crawling or pagination: one URL per `web-scraper-fetch` run; one saved file
  per `web-scraper-extract` run.
- Only the `window.__INITIAL_STATE__` marker is supported; other markers
  (`__NEXT_DATA__`, `__NUXT__`, JSON-LD) are out of scope.

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

### 2.2 `web-scraper-extract`
- `--input` (path, required): a saved HTML file containing a
  `window.__INITIAL_STATE__ = {…}` assignment, UTF-8.
- `--output` (path, required): file to write the raw JSON to.
- `--state-path` (string, optional): dotted path to a sub-node (e.g. a listings
  array); omit to write the whole state object.
- `--jsonl` (flag, optional): when the selected node is an array, write one JSON
  object per line instead of a single pretty-printed document.

### 2.3 Embedded-state format
The input HTML contains the substring `window.__INITIAL_STATE__ = ` followed by a
balanced `{…}` JSON-like object. The object may contain the bare JavaScript
literal `undefined` as a value (not valid JSON); it is treated as `null` (R4).

---

## 3. Outputs

- `web-scraper-fetch` writes the decoded response body verbatim to `--output`
  as UTF-8.
- `web-scraper-extract` writes, to `--output` (UTF-8, non-ASCII preserved):
  - the whole `__INITIAL_STATE__` object as pretty-printed JSON when no
    `--state-path` is given;
  - the node at `--state-path` otherwise;
  - with `--jsonl` and an array node, one compact JSON object per line.

  The output is the **original data**, not reshaped into any schema.

---

## 4. Business rules

- **R1 — Fetch is GET-to-file.** `web-scraper-fetch` performs a single HTTP(S)
  GET with the configured User-Agent and timeout and writes the decoded body to
  `--output`. It performs no other network I/O.
- **R2 — Scheme restriction.** Only `http://` and `https://` URLs are accepted;
  any other scheme (e.g. `file://`) is rejected before any request is made
  (§6, exit 2), preventing local-file or non-HTTP access.
- **R3 — Decoding.** The response body is decoded using the HTTP response charset
  when present, otherwise UTF-8, replacing undecodable bytes; the output file is
  written UTF-8.
- **R4 — `undefined` handling.** During extraction, a bare token `undefined` that
  appears **outside any string value** is rewritten to `null`; an occurrence
  inside a string value is left unchanged. The cleaned text is parsed as JSON.
- **R5 — State location + balanced scan.** `web-scraper-extract` finds the first
  occurrence of `window.__INITIAL_STATE__ = ` and parses the balanced `{…}`
  object that follows, tracking string literals and escapes so braces inside
  strings do not affect nesting. A missing marker or unterminated object is an
  error (exit 1).
- **R6 — Node selection.** `--state-path` is split on `.` and navigated through
  nested objects. A missing segment is an error (exit 1). With no `--state-path`,
  the whole state object is used.
- **R7 — Raw, unmapped output.** The extracted node is serialized without
  modification of keys or values (numbers, booleans, nested objects, and arrays
  are preserved). With `--jsonl`, an array is written one element per line;
  otherwise a single pretty-printed JSON document (2-space indent) is written.
- **R8 — Atomic output.** `web-scraper-extract` writes to a temp file then
  `os.replace`s it into the final name; on any OS error the temp file is removed
  and no partial output remains (exit 1).
- **R9 — Idempotency.** Re-running either command with the same inputs produces
  the same output and overwrites prior output; neither appends.

---

## 5. Data quality rules

| Condition                                       | Action                                | Rule |
|-------------------------------------------------|---------------------------------------|------|
| Bare `undefined` outside a string               | Rewritten to `null`                   | R4   |
| `undefined` inside a string value               | Preserved verbatim                    | R4   |
| Marker absent / object unbalanced / unparseable | Error, exit 1                         | R5   |
| `--state-path` segment missing                  | Error, exit 1                         | R6   |
| Selected node is not an array, with `--jsonl`   | Written as a single pretty document   | R7   |

No listing is dropped, renamed, or reshaped; the output mirrors the source.

---

## 6. CLI contract

### 6.1 `web-scraper-fetch`
- Entry point: `web-scraper-fetch = "web_scraper.download:main"`.
- On success prints `saved <N> characters to <path>` and exits 0.
- Exit codes: 0 success; 1 fetch failure (URL/network error) or write failure;
  2 argument error (missing required arg, non-http(s) scheme).

### 6.2 `web-scraper-extract`
- Entry point: `web-scraper-extract = "web_scraper.extractcli:main"`.
- Args: `--input` (required), `--output` (required), `--state-path` (optional),
  `--jsonl` (optional flag).
- On success prints `extracted <N> to <path>` (`<N>` = array length when the
  selected node is a list, else 1) and exits 0.
- Exit codes: 0 success; 1 unreadable input, extraction/selection failure, or
  output write failure; 2 argument error (missing `--input`/`--output`).

---

## 7. Error handling and edge cases

| Case                                       | Behavior                                 | Rule / Exit |
|--------------------------------------------|------------------------------------------|-------------|
| `--url` not http(s)                        | No request; exit 2.                      | R2 / 6.1    |
| Network/URL error                          | No output; stderr message; exit 1.       | 6.1         |
| Output file unwritable                     | Exit 1 (temp removed for extract).       | R8 / 6      |
| `__INITIAL_STATE__` marker absent          | Error; exit 1.                           | R5          |
| Unbalanced `{…}`                           | Error; exit 1.                           | R5          |
| `undefined` inside a string value          | Preserved verbatim.                      | R4          |
| `--state-path` segment missing             | Error; exit 1.                           | R6          |
| Empty array node                            | Written (empty JSONL or `[]`); exit 0.  | R7          |

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

### AC3 — Bare `undefined` becomes null; in-string preserved (R4)
- **Given** `window.__INITIAL_STATE__ = {"note": "value is undefined here", "x": undefined};`.
- **When** the state is extracted.
- **Then** the parsed object equals `{"note": "value is undefined here", "x": null}`.

### AC4 — Balanced scan ignores trailing script (R5)
- **Given** `window.__INITIAL_STATE__ = {"a": {"b": 2}};window.OTHER = {"not": "mine"};`.
- **When** extracted.
- **Then** the result equals `{"a": {"b": 2}}`.

### AC5 — Whole-state capture preserves data (R7)
- **Given** a page whose state is `{"data": {"results": {"items": [{"ref": "a1", "cost": 100}]}}}`.
- **When** `web-scraper-extract` runs with no `--state-path`.
- **Then** the output parses back to the identical state object.

### AC6 — Node selection + JSONL (R6, R7)
- **Given** the same state and `--state-path data.results.items --jsonl`.
- **When** `web-scraper-extract` runs.
- **Then** exit 0, and the single output line parses to
  `{"ref": "a1", "cost": 100}` (original keys, unmapped).

### AC7 — Missing marker → exit 1 (R5)
- **Given** an input file containing `<html>no state</html>`.
- **When** `web-scraper-extract` runs.
- **Then** it exits 1 and writes no output.

### AC8 — Missing `--state-path` segment → exit 1 (R6)
- **Given** a valid state but `--state-path data.missing`.
- **When** `web-scraper-extract` runs.
- **Then** it exits 1.

### AC9 — Atomic write failure leaves no temp (R8)
- **Given** a run where `os.replace` raises after the temp file is written.
- **When** `web-scraper-extract` runs.
- **Then** it exits 1 and no `*.tmp` or final output file remains.

---

## 9. Non-functional requirements (measurable only)

- **NFR1 — No network in the extract stage.** `web-scraper-extract` opens zero
  network sockets (it reads a local file only).
- **NFR2 — Determinism.** Given identical input and arguments, both commands
  produce byte-identical output across runs.
- **NFR3 — Encoding.** All output bytes are valid UTF-8 (no BOM).
- **NFR4 — No new runtime dependency.** Both commands use only the standard
  library.

---

## 10. Open questions and assumptions

### Assumptions
- **A1.** The embedded object is JSON apart from bare `undefined` values; other
  JS-only constructs (functions, comments, single quotes, trailing commas) are
  not expected and would cause an extraction error (exit 1).

### Open questions
- **Q1.** Should additional embedded-state markers (`__NEXT_DATA__`, `__NUXT__`,
  JSON-LD) be supported via a configurable marker? (Out of scope now.)

---

## 11. Revision log

### Round 2 — Mapping removed
- Removed the `web-scraper-json` command and all field-mapping / profile content.
  The tool now captures raw data only (`web-scraper-fetch` + `web-scraper-extract`);
  mapping to a model is a downstream concern. Self-consistency pass: exit codes
  (0/1/2) and the raw-output contract are internally consistent; no real site
  names or site-specific keys are used; no contradiction with
  `docs/specs/web-scraper.md` (that spec governs the separate HTML-card parser).

### Round 1 — Initial draft
- Documented `web-scraper-fetch`, `web-scraper-extract`, and the (now removed)
  `web-scraper-json` mapping command.
