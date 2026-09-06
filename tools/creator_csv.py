"""Read the separate creator lists together while preserving shared person IDs."""

import csv
from pathlib import Path

from wpnames import write_csv_no_trailing_newline

ROOT = Path(__file__).resolve().parent.parent
CSV_PATHS = (ROOT / "youtuber.csv", ROOT / "vtuber.csv")


def validate_creator_rows(rows):
    identities = {}
    for row in rows:
        category = row.get("category")
        if category not in {"youtuber", "vtuber"}:
            raise ValueError(f"Invalid creator category: {category!r}")
        identity = (row["original"], category)
        previous = identities.setdefault(row["id"], identity)
        if previous != identity:
            raise ValueError(f"Creator ID collision: {row['id']}")


def read_creator_csvs(paths=CSV_PATHS):
    columns, rows = [], []
    for path in paths:
        with Path(path).open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if columns and columns != reader.fieldnames:
                raise ValueError(f"Creator CSV columns differ: {path}")
            columns = list(reader.fieldnames or [])
            incoming = list(reader)
        if any(row.get("category") != Path(path).stem for row in incoming):
            raise ValueError(f"Creator category does not match file: {path}")
        rows.extend(incoming)
    validate_creator_rows(rows)
    return columns, rows


def write_creator_csvs(columns, rows, paths=CSV_PATHS,
                       writer=write_csv_no_trailing_newline):
    validate_creator_rows(rows)
    destinations = {Path(path).stem: Path(path) for path in paths}
    if any(row["category"] not in destinations for row in rows):
        raise ValueError("Missing destination for creator category")
    for category, path in destinations.items():
        writer(path, columns, [row for row in rows if row["category"] == category])
