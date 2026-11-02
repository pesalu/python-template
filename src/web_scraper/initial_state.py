"""Extract listing records from a React ``window.__INITIAL_STATE__`` JSON blob.

Some listing sites render as single-page apps whose data is embedded in the page
as a JavaScript state object rather than as HTML cards. This module locates that
object, parses it (tolerating the JS literal ``undefined``), navigates to the
listings array, and maps each entry onto the same six-field record shape used by
the HTML parser.

Field mapping is driven by a caller-supplied profile (see ``Profile``) so any
site can be handled without code changes; no site-specific profile is built in.
"""

import json
from dataclasses import dataclass, field
from typing import Any

_MARKER = "window.__INITIAL_STATE__ = "
_UNDEFINED = "undefined"


class InitialStateError(Exception):
    """Raised when the embedded state cannot be located, parsed, or navigated."""


@dataclass(frozen=True)
class Profile:
    """Declarative mapping from a site's JSON state to output records.

    ``state_path`` is a dotted path to the listings array. ``fields`` maps each
    output field to a source key in a listing object. ``detail_url_template`` is
    an optional ``str.format`` template filled from ``detail_url_field``.
    """

    state_path: str
    fields: dict[str, str] = field(default_factory=dict)
    detail_url_template: str | None = None
    detail_url_field: str | None = None


def _extract_object(text: str, start: int) -> str:
    """Return the balanced ``{...}`` at ``text[start:]`` as a JSON string.

    Bare ``undefined`` tokens that appear outside of strings are rewritten to
    ``null`` so the result is valid JSON; occurrences inside string values are
    left untouched.
    """
    out: list[str] = []
    depth = 0
    in_str = False
    esc = False
    started = False
    i = start
    n = len(text)
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue
        if ch == "{":
            depth += 1
            started = True
            out.append(ch)
            i += 1
            continue
        if ch == "}":
            depth -= 1
            out.append(ch)
            i += 1
            if started and depth == 0:
                return "".join(out)
            continue
        if ch == "u" and text.startswith(_UNDEFINED, i):
            prev = text[i - 1] if i > 0 else ""
            after = text[i + len(_UNDEFINED)] if i + len(_UNDEFINED) < n else ""
            if not _is_word(prev) and not _is_word(after):
                out.append("null")
                i += len(_UNDEFINED)
                continue
        out.append(ch)
        i += 1
    raise InitialStateError("unterminated __INITIAL_STATE__ object")


def _is_word(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def extract_initial_state(html: str) -> dict[str, Any]:
    """Parse the ``window.__INITIAL_STATE__`` object embedded in ``html``."""
    idx = html.find(_MARKER)
    if idx == -1:
        raise InitialStateError("window.__INITIAL_STATE__ not found in page")
    blob = _extract_object(html, idx + len(_MARKER))
    try:
        data = json.loads(blob)
    except json.JSONDecodeError as exc:
        raise InitialStateError(f"could not parse embedded state: {exc}") from exc
    if not isinstance(data, dict):
        raise InitialStateError("embedded state is not a JSON object")
    return data


def select_listings(state: dict[str, Any], dotted_path: str) -> list[Any]:
    """Navigate ``dotted_path`` in ``state`` and return the listings array."""
    node: Any = state
    for part in dotted_path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise InitialStateError(f"listings path not found: {dotted_path!r} (at {part!r})")
        node = node[part]
    if not isinstance(node, list):
        raise InitialStateError(f"listings path {dotted_path!r} is not an array")
    return node


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def map_listings(items: list[Any], profile: Profile) -> list[dict[str, str | None]]:
    """Map raw listing objects onto six-field records using ``profile``."""
    records: list[dict[str, str | None]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        record: dict[str, str | None] = {
            out_field: _to_str(item.get(src_key)) for out_field, src_key in profile.fields.items()
        }
        record["detail_url"] = _detail_url(item, profile)
        records.append(record)
    return records


def _detail_url(item: dict[str, Any], profile: Profile) -> str | None:
    if not profile.detail_url_template or not profile.detail_url_field:
        return None
    value = item.get(profile.detail_url_field)
    if value is None or value == "":
        return None
    return profile.detail_url_template.format(value=value)


def parse_initial_state(html: str, profile: Profile) -> list[dict[str, str | None]]:
    """Full pipeline: extract state, select listings, and map them to records."""
    state = extract_initial_state(html)
    items = select_listings(state, profile.state_path)
    return map_listings(items, profile)
