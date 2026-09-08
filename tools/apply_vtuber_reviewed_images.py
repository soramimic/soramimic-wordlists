#!/usr/bin/env python3
"""Apply the exact VTuber images, attribution, and terms in the reviewed manifest."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from gen_youtuber_cards import asset_name, build_card, image_page_url, image_url
from wpnames import write_csv_no_trailing_newline

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "vtuber.csv"
MANIFEST_PATH = ROOT / "tools/vtuber_reviewed_images.json"
IMAGE_USAGE = "noncommercial_fanwork"
IMAGE_FIELDS = ("image", "image_page", "image_credit", "image_usage", "image_terms_page")


def load_manifest(path: Path = MANIFEST_PATH, *, include_inactive: bool = False) -> dict[str, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("images"), list):
        raise ValueError(f"{path}: unsupported image manifest")
    required = {"person_id", "original", "org", "enabled", "image_url", "source_page",
                "credit", "terms_page", "reviewed"}
    records = {}
    ids = set()
    urls = set()
    for record in data["images"]:
        if not isinstance(record, dict) or required - record.keys():
            raise ValueError(f"{path}: incomplete image record")
        name = record["original"]
        for field in required - {"enabled"}:
            value = record[field]
            if not isinstance(value, str) or not value.strip() or value != value.strip():
                raise ValueError(f"{name}: invalid {field}")
            if any(c in value for c in ',"\r\n'):
                raise ValueError(f"{name}: invalid CSV characters in {field}")
        if name in records or record["person_id"] in ids or record["image_url"] in urls:
            raise ValueError(f"{name}: duplicate name, person ID, or image")
        if not re.fullmatch(r"[1-9][0-9]*", record["person_id"]):
            raise ValueError(f"{name}: invalid person ID")
        if type(record["enabled"]) is not bool:
            raise ValueError(f"{name}: enabled must be boolean")
        for field in ("image_url", "source_page", "terms_page"):
            parsed = urlsplit(record[field])
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError(f"{name}: invalid {field} URL")
        if date.fromisoformat(record["reviewed"]).isoformat() != record["reviewed"]:
            raise ValueError(f"{name}: invalid review date")
        if "sha256" in record and not re.fullmatch(r"[0-9a-f]{64}", record["sha256"]):
            raise ValueError(f"{name}: invalid sha256")
        local_prefix = "https://raw.githubusercontent.com/soramimic/soramimic-wordlists/main/images/vtuber/"
        if record["image_url"].startswith(local_prefix):
            filename = record["image_url"][len(local_prefix):]
            if not filename or Path(filename).name != filename or not filename.endswith(".png"):
                raise ValueError(f"{name}: invalid local image filename")
            asset = path.parent.parent / "images/vtuber" / filename
            if not asset.is_file() or hashlib.sha256(asset.read_bytes()).hexdigest() != record.get("sha256"):
                raise ValueError(f"{name}: local image missing or hash mismatch")
        records[name] = record
        ids.add(record["person_id"])
        urls.add(record["image_url"])
    return {name: r for name, r in records.items() if include_inactive or r["enabled"]}


def expected_image_fields(record: dict) -> tuple[str, ...]:
    if record["enabled"]:
        return (record["image_url"], record["source_page"], record["credit"],
                IMAGE_USAGE, record["terms_page"])
    return (image_url(record["original"]), image_page_url(record["original"]), "", "", "")


def validate_rows(rows: list[dict], manifest: dict[str, dict], *, require_applied: bool = True) -> None:
    seen = set()
    managed_urls = {r["image_url"] for r in manifest.values()}
    managed_ids = {r["person_id"] for r in manifest.values()}
    for row in rows:
        record = manifest.get(row["original"])
        if record is None:
            if row["image"] in managed_urls or row["id"] in managed_ids:
                raise ValueError(f"{row['original']}: image or ID belongs to another manifest person")
            continue
        if (row["id"], row["category"], row["org"]) != (record["person_id"], "vtuber", record["org"]):
            raise ValueError(f"{row['original']}: identity does not match image manifest")
        if require_applied and tuple(row[f] for f in IMAGE_FIELDS) != expected_image_fields(record):
            raise ValueError(f"{row['original']}: image fields do not match manifest")
        seen.add(row["original"])
    if seen != set(manifest):
        raise ValueError(f"missing manifest people: {sorted(set(manifest) - seen)}")


def apply(csv_path: Path = CSV_PATH, manifest_path: Path = MANIFEST_PATH) -> tuple[int, int]:
    manifest = load_manifest(manifest_path, include_inactive=True)
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    if {"id", "original", "category", "org", *IMAGE_FIELDS} - set(fields):
        raise ValueError(f"{csv_path}: missing required columns")
    validate_rows(rows, manifest, require_applied=False)
    changed = set()
    count = 0
    for row in rows:
        record = manifest.get(row["original"])
        if record is None:
            continue
        desired = expected_image_fields(record)
        if not record["enabled"]:
            card = csv_path.parent / "images/youtuber" / asset_name(record["original"])
            if not card.is_file():
                card.parent.mkdir(parents=True, exist_ok=True)
                card.write_text(build_card(record["original"], "vtuber", record["org"]), encoding="utf-8")
        if tuple(row[f] for f in IMAGE_FIELDS) != desired:
            row.update(zip(IMAGE_FIELDS, desired))
            changed.add(row["original"])
            count += 1
    if count:
        write_csv_no_trailing_newline(csv_path, fields, rows)
    return len(changed), count


if __name__ == "__main__":
    people, rows = apply()
    print(f"vtuber.csv: reviewed images updated for {people} people / {rows} rows")
