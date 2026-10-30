import csv
import json

FIELDS: list[str] = ["title", "price", "location", "rooms", "area", "detail_url"]


def write_jsonl(records: list[dict[str, str | None]], path: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        for record in records:
            ordered = {field: record.get(field) for field in FIELDS}
            handle.write(json.dumps(ordered, ensure_ascii=False))
            handle.write("\n")


def write_csv(records: list[dict[str, str | None]], path: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(FIELDS)
        for record in records:
            writer.writerow(
                ["" if record.get(field) is None else record.get(field) for field in FIELDS]
            )
