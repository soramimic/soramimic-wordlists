#!/usr/bin/env python3
"""Preserve reviewed names, readings and metadata of list entries."""

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
SOURCES = Path(__file__).with_suffix(".jsonl")
COMMON_FIELDS = {"original", "team", "position", "prefecture", "parent",
                 "status", "wikidata", "municipality_type"}
FORM_FIELDS = {"surface", "pronunciation"}


def load_records(path: Path = SOURCES) -> list[dict]:
    records, seen, source_keys = [], set(), set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        key = (record["list"], record["id"])
        if key in seen:
            raise ValueError(f"Duplicate entry correction: {key}")
        if record["list"] not in {"baseball", "municipality"} \
                or not isinstance(record["id"], str) or not record["id"] \
                or not isinstance(record["original"], str) or not record["original"]:
            raise ValueError(f"Invalid entry identity: {key}")
        fields = record.get("fields", {})
        forms = record.get("forms", {})
        if not isinstance(fields, dict) or not set(fields) <= COMMON_FIELDS \
                or not isinstance(forms, dict) or any(
                    not isinstance(values, dict) or not set(values) <= FORM_FIELDS
                    for values in forms.values()
                ) or not (fields or forms):
            raise ValueError(f"Invalid entry fields: {key}")
        texts = [record["id"], record["original"], record.get("previous_original", "")]
        texts += list(fields.values())
        texts += [value for values in forms.values() for value in values.values()]
        if any(not isinstance(value, str) or any(c in value for c in '\r\n\t,"')
               for value in texts):
            raise ValueError(f"Invalid entry text: {key}")
        if fields.get("original", record["original"]) != record["original"]:
            raise ValueError(f"Corrected name does not match identity: {key}")
        source_qid = record.get("source_qid", "")
        if source_qid:
            source_key = (record["list"], source_qid)
            if not re.fullmatch(r"Q\d+", source_qid) or source_key in source_keys:
                raise ValueError(f"Invalid or duplicate source identity: {source_key}")
            source_keys.add(source_key)
        urls = record["source_urls"]
        if not isinstance(urls, list) or not urls or any(
            not isinstance(url, str) or urlsplit(url).scheme not in {"https", "http"}
            or not urlsplit(url).netloc for url in urls
        ):
            raise ValueError(f"Missing or invalid entry sources: {key}")
        date.fromisoformat(record["reviewed_on"])
        seen.add(key)
        records.append(record)
    return records


@lru_cache(maxsize=1)
def records_by_list() -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for record in load_records():
        result.setdefault(record["list"], []).append(record)
    return result


def source_aliases(list_name: str) -> dict[str, str]:
    return {record["source_qid"]: record["id"]
            for record in records_by_list().get(list_name, []) if record.get("source_qid")}


def apply_corrections(list_name: str, rows: list[dict], records: list[dict] | None = None,
                      *, strict: bool = False) -> int:
    records = records_by_list().get(list_name, []) if records is None else [
        record for record in records if record["list"] == list_name
    ]
    by_id: dict[str, list[dict]] = {}
    for row in rows:
        by_id.setdefault(row.get("id"), []).append(row)
    updates = []
    for record in records:
        group = by_id.get(record["id"], [])
        names = {record["original"], record.get("previous_original", record["original"])}
        if not any(row.get("original") in names for row in group):
            if strict:
                raise ValueError(f"Entry identity missing: {list_name}:{record['id']}")
            continue
        for row in group:
            fields = {**record.get("fields", {}),
                      **record.get("forms", {}).get(row.get("type"), {})}
            if not set(fields) <= set(row):
                raise ValueError(f"Entry column missing: {list_name}:{record['id']}")
            updates.append((row, fields))
    changed = 0
    for row, fields in updates:
        for column, value in fields.items():
            if row[column] != value:
                row[column] = value
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
        changed = apply_corrections(list_name, rows, records, strict=True)
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
        print(f"{path.name}: {changed} entry field changes")
    return int(args.check and bool(changes))


if __name__ == "__main__":
    raise SystemExit(main())
