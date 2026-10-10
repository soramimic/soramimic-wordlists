"""Read the separate creator lists together while preserving shared person IDs."""

import csv
from pathlib import Path

from wpnames import write_csv_no_trailing_newline

ROOT = Path(__file__).resolve().parent.parent
CSV_PATHS = (ROOT / "youtuber.csv", ROOT / "vtuber.csv")
CARD_IMAGE_PREFIX = (
    "https://raw.githubusercontent.com/soramimic/soramimic-wordlists/"
    "main/images/youtuber/"
)


def image_availability(image):
    """Whether an assigned image depicts the creator rather than a name card."""
    return ("no" if not image or image == "NA" or image.startswith(CARD_IMAGE_PREFIX)
            else "yes")


def write_creator_csv(path, columns, rows, writer=write_csv_no_trailing_newline):
    """Preserve usage notices and update image availability when writing creators."""
    columns = list(columns)
    if "has_image" not in columns:
        columns.append("has_image")
    updated = []
    for row in rows:
        row = {**row, "has_image": image_availability(row.get("image"))}
        # Missing metadata on new VTubers gets the default notice; explicit edits survive.
        if "usage_notice" in columns and row.get("usage_notice") in (None, "NA"):
            row["usage_notice"] = "guidelines" if row.get("category") == "vtuber" else ""
        if "usage_terms_page" in columns and row.get("usage_terms_page") in (None, "NA"):
            row["usage_terms_page"] = ""
        updated.append(row)
    writer(path, columns, updated)


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
        write_creator_csv(path, columns,
                          [row for row in rows if row["category"] == category], writer)
