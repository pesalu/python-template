import os


def read_page(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError):
        return None


def resolve_next_path(current_page_path: str, href: str) -> str | None:
    stripped = href
    for separator in ("#", "?"):
        index = stripped.find(separator)
        if index != -1:
            stripped = stripped[:index]
    if "://" in stripped:
        return None
    if not stripped:
        return None
    if os.path.isabs(stripped):
        return None
    return os.path.normpath(os.path.join(os.path.dirname(current_page_path), stripped))
