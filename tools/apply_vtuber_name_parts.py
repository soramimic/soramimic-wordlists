#!/usr/bin/env python3
"""Add reviewed activity-name parts without changing existing creator rows."""

import argparse
import csv
import datetime
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

from wpnames import write_csv_no_trailing_newline

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "vtuber.csv"
SOURCES_PATH = ROOT / "tools/vtuber_name_parts.jsonl"
PART_FIELDS = {"surface", "pronunciation", "type"}


def compact(value):
    return re.sub(r"[\s・･=＝]", "", unicodedata.normalize("NFKC", value))


def load_reviewed(path=SOURCES_PATH):
    records, seen = [], set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        for key in ("person_id", "original", "pronunciation", "family",
                    "family_pronunciation", "given", "given_pronunciation"):
            value = record.get(key)
            if not isinstance(value, str) or not value.strip() or value == "NA":
                raise ValueError(f"Missing name-part field: {key}")
        pid = record["person_id"]
        if not pid.isdecimal() or pid in seen:
            raise ValueError(f"Invalid or duplicate person ID: {pid}")
        seen.add(pid)
        order = record.get("order")
        if order not in {"family_given", "given_family"}:
            raise ValueError(f"Missing name order: {pid}")
        first, second = order.split("_")
        if compact(record[first] + record[second]) != compact(record["original"]):
            raise ValueError(f"Name parts do not reproduce activity name: {pid}")
        if (record[first + "_pronunciation"] + record[second + "_pronunciation"]
                != compact(record["pronunciation"])):
            raise ValueError(f"Name parts do not reproduce reading: {pid}")
        for key in ("family_pronunciation", "given_pronunciation"):
            if not re.fullmatch(r"[ァ-ヶー]+", record[key]):
                raise ValueError(f"Invalid name-part reading: {pid}")
        urls = record.get("source_urls")
        if not isinstance(urls, list) or not urls:
            raise ValueError(f"Missing name-part source: {pid}")
        for url in urls:
            if not isinstance(url, str):
                raise ValueError(f"Invalid name-part source: {pid}")
            parsed = urlparse(url)
            if parsed.scheme not in {"https", "http"} or not parsed.netloc:
                raise ValueError(f"Invalid name-part source: {pid}")
        datetime.date.fromisoformat(record["reviewed_on"])
        records.append(record)
    return records


def add_reviewed_parts(rows, records):
    """Return new rows; reject stale identities or conflicting existing parts."""
    groups = defaultdict(list)
    for row in rows:
        groups[row["id"]].append(row)
    additions = {}
    for record in records:
        pid = record["person_id"]
        if pid in additions:
            raise ValueError(f"Duplicate person ID: {pid}")
        group = groups[pid]
        full = [row for row in group if row["type"] == "full"]
        if (len(full) != 1 or any(row["original"] != record["original"]
                                 or row["category"] != "vtuber" for row in group)
                or full[0]["pronunciation"] != record["pronunciation"]):
            raise ValueError(f"Name-part identity or full reading changed: {pid}")
        additions[pid] = []
        for part in ("family", "given"):
            expected = {**full[0], "type": part, "surface": record[part],
                        "pronunciation": record[part + "_pronunciation"]}
            existing = [row for row in group if row["type"] == part]
            if existing and existing != [expected]:
                raise ValueError(f"Conflicting {part} row: {pid}")
            if not existing:
                additions[pid].append(expected)
    result = []
    for row in rows:
        result.append(dict(row))
        if row["type"] == "full":
            result.extend(additions.get(row["id"], []))
    return result, sum(map(len, additions.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns, rows = reader.fieldnames, list(reader)
    records = load_reviewed()
    result, added = add_reviewed_parts(rows, records)
    if not args.check and added:
        write_csv_no_trailing_newline(CSV_PATH, columns, result)
    print(f"Reviewed name parts: {len(records)} people; {added} "
          + ("missing rows" if args.check else "rows added"))
    return int(args.check and added > 0)


if __name__ == "__main__":
    raise SystemExit(main())
