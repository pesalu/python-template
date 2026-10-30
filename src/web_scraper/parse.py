from bs4 import BeautifulSoup
from bs4.element import Tag

_OPTIONAL_FIELDS = {
    "price": "listing-price",
    "location": "listing-location",
    "rooms": "listing-rooms",
    "area": "listing-area",
}


def normalize_text(text: str) -> str:
    return " ".join(text.split())


def _has_class(tag: Tag, name: str) -> bool:
    classes = tag.get("class")
    return isinstance(classes, list) and name in classes


def _is_top_level_card(tag: Tag) -> bool:
    parent = tag.parent
    while isinstance(parent, Tag):
        if _has_class(parent, "listing-card"):
            return False
        parent = parent.parent
    return True


def _field_text(card: Tag, class_name: str) -> str | None:
    element = card.find(class_=class_name)
    if not isinstance(element, Tag):
        return None
    value = normalize_text(element.get_text(separator=""))
    return value or None


def parse_listings(html: str) -> list[dict[str, str | None]]:
    soup = BeautifulSoup(html, "html.parser")
    records: list[dict[str, str | None]] = []
    for card in soup.select(".listing-card"):
        if not _is_top_level_card(card):
            continue
        title_element = card.find(class_="listing-title")
        title = (
            normalize_text(title_element.get_text(separator=""))
            if isinstance(title_element, Tag)
            else ""
        )
        link = card.find("a", class_="listing-link")
        detail_url: str | None = None
        if isinstance(link, Tag):
            href = link.get("href")
            if isinstance(href, str) and href.strip():
                detail_url = href
        record: dict[str, str | None] = {
            "title": title,
            "price": _field_text(card, _OPTIONAL_FIELDS["price"]),
            "location": _field_text(card, _OPTIONAL_FIELDS["location"]),
            "rooms": _field_text(card, _OPTIONAL_FIELDS["rooms"]),
            "area": _field_text(card, _OPTIONAL_FIELDS["area"]),
            "detail_url": detail_url,
        }
        records.append(record)
    return records


def find_next_page(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    link = soup.find("a", class_="pagination-next")
    if not isinstance(link, Tag):
        return None
    href = link.get("href")
    if isinstance(href, str):
        return href
    return None
