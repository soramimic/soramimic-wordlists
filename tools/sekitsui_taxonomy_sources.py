"""Apply reviewed vertebrate taxonomy facts without replacing existing values."""

from __future__ import annotations

import argparse
import csv
import json
from functools import lru_cache
from pathlib import Path

from wpnames import write_csv_no_trailing_newline

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = Path(__file__).with_suffix(".jsonl")
FIELDS = ("class", "order", "family")
CLASSES = {"哺乳類", "鳥類", "爬虫類", "両生類", "魚類"}


def is_missing(value: str | None) -> bool:
    return (value or "").strip() in ("", "NA")


@lru_cache(maxsize=None)
def load_sources(path: Path = SOURCE_PATH) -> dict[str, dict]:
    records = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        name = record["original"]
        values = record["values"]
        if not name or name in records or not record.get("id"):
            raise ValueError(f"invalid or duplicate taxonomy identity: {name}")
        if not values or set(values) - set(FIELDS):
            raise ValueError(f"invalid taxonomy fields: {name}")
        if "class" in values and values["class"] not in CLASSES:
            raise ValueError(f"invalid vertebrate class: {name}")
        if "order" in values and (
            not values["order"].endswith("目")
            or values["order"].endswith(("亜目", "下目", "小目", "上目"))
        ):
            raise ValueError(f"invalid vertebrate order: {name}")
        if "family" in values and (
            not values["family"].endswith("科")
            or values["family"].endswith(("亜科", "上科"))
        ):
            raise ValueError(f"invalid vertebrate family: {name}")
        supported = set()
        for source in record["sources"]:
            if not source.get("url", "").startswith("https://"):
                raise ValueError(f"missing taxonomy source URL: {name}")
            if not source.get("matched_name"):
                raise ValueError(f"missing source identity: {name}")
            for field, value in source["values"].items():
                if field in values and values[field] == value and not is_missing(value):
                    supported.add(field)
        if supported != set(values):
            raise ValueError(f"unsupported taxonomy fields: {name}")
        records[name] = record
    return records


def apply_sources(rows: list[dict[str, str]], sources: dict[str, dict] | None = None) -> int:
    sources = load_sources() if sources is None else sources
    changed = 0
    for row in rows:
        source = sources.get(row["original"])
        if not source or row["id"] != source["id"]:
            continue
        for field, value in source["values"].items():
            if is_missing(row.get(field)):
                row[field] = value
                changed += 1
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=ROOT / "sekitsui.csv")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    with args.csv.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        columns = list(reader.fieldnames or [])
    changed = apply_sources(rows)
    if args.check:
        print(f"sekitsui reviewed taxonomy: {changed} missing cells")
        return int(bool(changed))
    write_csv_no_trailing_newline(args.csv, columns, rows)
    print(f"sekitsui reviewed taxonomy: filled {changed} cells")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
