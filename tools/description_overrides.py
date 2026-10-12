#!/usr/bin/env python3
"""Apply reviewed description corrections without changing vocabulary or source data."""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
SOURCES = Path(__file__).with_name("description_overrides.jsonl")


def load_records(path: Path = SOURCES) -> list[dict]:
    records, seen = [], set()
    descriptions_by_id = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        key = (record["list"], record["id"], record["original"], record["column"])
        if key in seen:
            raise ValueError(f"Duplicate description override: {key}")
        if not re.fullmatch(r"[a-z][a-z_]*", record["list"]) \
                or not isinstance(record["id"], str) or not record["id"] \
                or any(c in record["id"] for c in '\r\n\t,"') \
                or not isinstance(record["original"], str) or not record["original"] \
                or record["column"] not in {"description", "achievement"}:
            raise ValueError(f"Invalid description identity: {key}")
        description = record["description"]
        if not isinstance(description, str) or any(c in description for c in '\r\n\t,"'):
            raise ValueError(f"Invalid description: {key}")
        identity_column = (record["list"], record["id"], record["column"])
        if identity_column in descriptions_by_id and descriptions_by_id[identity_column] != description:
            raise ValueError(f"Conflicting descriptions for aliases: {identity_column}")
        descriptions_by_id[identity_column] = description
        for left, right in (("（", "）"), ("「", "」"), ("『", "』"), ("(", ")")):
            if description.count(left) != description.count(right):
                raise ValueError(f"Unbalanced description: {key}")
        urls = record["source_urls"]
        if not isinstance(urls, list) or any(
            not isinstance(url, str) or urlsplit(url).scheme not in {"https", "http"}
            or not urlsplit(url).netloc for url in urls
        ):
            raise ValueError(f"Invalid description sources: {key}")
        date.fromisoformat(record["reviewed_on"])
        seen.add(key)
        records.append(record)
    return records


@lru_cache(maxsize=1)
def _records_by_list() -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for record in load_records():
        result.setdefault(record["list"], []).append(record)
    return result


def reviewed_identities(list_name: str) -> set[tuple[str, str]]:
    return {(record["id"], record["original"])
            for record in _records_by_list().get(list_name, [])}


def apply_overrides(
    list_name: str, rows: list[dict], records: list[dict] | None = None,
    *, strict: bool = False,
) -> int:
    """Match both stable ID and original name; update every surface of that identity.

    Updaters may work with a subset of a list. The standalone check requires every
    ledger identity to exist, so removed or renamed entries cannot go unnoticed.
    """
    records = _records_by_list().get(list_name, []) if records is None else [
        record for record in records if record["list"] == list_name
    ]
    by_id: dict[str, list[dict]] = {}
    for row in rows:
        by_id.setdefault(row.get("id"), []).append(row)

    def matching_rows(record: dict) -> list[dict]:
        group = by_id.get(record["id"], [])
        return group if any(row.get("original") == record["original"] for row in group) else []
    for record in records:
        matches = matching_rows(record)
        if strict and not matches:
            raise ValueError(f"Description identity missing: {list_name}:{record['id']}:{record['original']}")
        if any(record["column"] not in row for row in matches):
            raise ValueError(f"Description column missing: {list_name}:{record['column']}")
    changed = 0
    for record in records:
        for row in matching_rows(record):
            column = record["column"]
            if row[column] != record["description"]:
                row[column] = record["description"]
                changed += 1
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    records = load_records()
    changes = 0
    for list_name in sorted({record["list"] for record in records}):
        path = ROOT / f"{list_name}.csv"
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            columns, rows = reader.fieldnames, list(reader)
        changed = apply_overrides(list_name, rows, records, strict=True)
        changes += changed
        if changed and not args.check:
            output = io.StringIO(newline="")
            writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            text = output.getvalue().rstrip("\n")
            if '"' in text:
                raise ValueError(f"Quoted fields are not supported: {path.name}")
            path.write_text(text, encoding="utf-8")
        print(f"{path.name}: {changed} description changes")
    return int(args.check and bool(changes))


if __name__ == "__main__":
    raise SystemExit(main())
