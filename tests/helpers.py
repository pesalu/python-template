"""Deterministic HTML/fixture builders shared across the scraper tests."""

import os

# Sentinel meaning "omit this element entirely from the card".
OMIT = object()


def make_card(
    title=OMIT,
    price=OMIT,
    location=OMIT,
    rooms=OMIT,
    area=OMIT,
    href=OMIT,
):
    """Build a single ``listing-card`` article.

    A field is included only when its argument is not ``OMIT``. ``href`` controls
    the ``a.listing-link`` element: when ``OMIT`` no link element is emitted at
    all (so ``detail_url`` is absent); otherwise a link with that raw ``href``
    value is emitted.
    """
    parts = ['<article class="listing-card">']
    if title is not OMIT:
        parts.append(f'<h2 class="listing-title">{title}</h2>')
    if price is not OMIT:
        parts.append(f'<span class="listing-price">{price}</span>')
    if location is not OMIT:
        parts.append(f'<span class="listing-location">{location}</span>')
    if rooms is not OMIT:
        parts.append(f'<span class="listing-rooms">{rooms}</span>')
    if area is not OMIT:
        parts.append(f'<span class="listing-area">{area}</span>')
    if href is not OMIT:
        parts.append(f'<a class="listing-link" href="{href}">View</a>')
    parts.append("</article>")
    return "\n".join(parts)


def make_page(cards, next_href=None):
    """Wrap a list of card HTML snippets into a full listing page document."""
    body = "\n".join(cards)
    nxt = ""
    if next_href is not None:
        nxt = f'<a class="pagination-next" href="{next_href}">Next</a>'
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><body>\n'
        f'<main class="listings">\n{body}\n</main>\n'
        f"{nxt}\n"
        "</body></html>\n"
    )


def write_pages(directory, pages):
    """Write ``pages`` as ``page1.html`` .. ``pageN.html`` linked in sequence.

    ``pages`` is a list where each element is a list of card HTML snippets for
    that page. Page ``i`` links to ``page{i+1}.html`` via ``pagination-next``;
    the last page has no next link. Returns the list of written file paths.
    """
    directory = str(directory)
    os.makedirs(directory, exist_ok=True)
    paths = []
    total = len(pages)
    for i, cards in enumerate(pages, start=1):
        next_href = f"page{i + 1}.html" if i < total else None
        html = make_page(cards, next_href)
        path = os.path.join(directory, f"page{i}.html")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(html)
        paths.append(path)
    return paths


# The two canonical records of spec section 2.3 (used by AC2/AC3/AC18).
CANONICAL_RECORDS = [
    {
        "title": "Cozy Downtown Apartment",
        "price": "€250,000",
        "location": "Helsinki, Kallio",
        "rooms": "3 rooms",
        "area": "72 m²",
        "detail_url": "/detail/123",
    },
    {
        "title": "Seaside Studio",
        "price": "€180,000",
        "location": "Espoo",
        "rooms": "1 room",
        "area": "28 m²",
        "detail_url": "/detail/124",
    },
]


def canonical_cards():
    """Return the two canonical cards of section 2.3 as HTML snippets."""
    return [
        make_card(
            title="Cozy Downtown Apartment",
            price="€250,000",
            location="Helsinki, Kallio",
            rooms="3 rooms",
            area="72 m²",
            href="/detail/123",
        ),
        make_card(
            title="Seaside Studio",
            price="€180,000",
            location="Espoo",
            rooms="1 room",
            area="28 m²",
            href="/detail/124",
        ),
    ]


# Expected serialized bytes for the two canonical records (AC2 / AC3).
JSONL_LINE_1 = (
    '{"title": "Cozy Downtown Apartment", "price": "€250,000", '
    '"location": "Helsinki, Kallio", "rooms": "3 rooms", '
    '"area": "72 m²", "detail_url": "/detail/123"}'
)
JSONL_LINE_2 = (
    '{"title": "Seaside Studio", "price": "€180,000", '
    '"location": "Espoo", "rooms": "1 room", '
    '"area": "28 m²", "detail_url": "/detail/124"}'
)
EXPECTED_JSONL = (JSONL_LINE_1 + "\n" + JSONL_LINE_2 + "\n").encode("utf-8")

CSV_HEADER = "title,price,location,rooms,area,detail_url"
CSV_ROW_1 = 'Cozy Downtown Apartment,"€250,000","Helsinki, Kallio",3 rooms,72 m²,/detail/123'
CSV_ROW_2 = 'Seaside Studio,"€180,000",Espoo,1 room,28 m²,/detail/124'
EXPECTED_CSV = (CSV_HEADER + "\n" + CSV_ROW_1 + "\n" + CSV_ROW_2 + "\n").encode("utf-8")

# Header-only CSV for zero records (AC12): 43 bytes.
EXPECTED_CSV_HEADER_ONLY = (CSV_HEADER + "\n").encode("utf-8")
