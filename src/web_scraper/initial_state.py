"""Extract the raw ``window.__INITIAL_STATE__`` JSON embedded in a page.

Some listing sites render as single-page apps whose data is embedded in the page
as a JavaScript state object rather than as HTML cards. This module locates that
object and parses it (tolerating the JS literal ``undefined``) so the original
JSON can be captured as-is; mapping to any downstream model is out of scope.
"""

import json
from typing import Any

_MARKER = "window.__INITIAL_STATE__ = "
_UNDEFINED = "undefined"


class InitialStateError(Exception):
    """Raised when the embedded state cannot be located, parsed, or navigated."""


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


def select_node(state: dict[str, Any], dotted_path: str) -> Any:
    """Navigate ``dotted_path`` in ``state`` and return the node found there."""
    node: Any = state
    for part in dotted_path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise InitialStateError(f"path not found: {dotted_path!r} (at {part!r})")
        node = node[part]
    return node


def extract_raw(html: str, state_path: str | None = None) -> Any:
    """Return the raw (unmapped) embedded state, or the node at ``state_path``."""
    state = extract_initial_state(html)
    if state_path:
        return select_node(state, state_path)
    return state
