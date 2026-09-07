#!/usr/bin/env python3
"""Apply Realize Production profile images and credits to vtuber.csv."""

from __future__ import annotations

import csv
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from gen_youtuber_cards import image_page_url as card_page_url
from gen_youtuber_cards import image_url as card_image_url
from wpnames import write_csv_no_trailing_newline

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "vtuber.csv"
MANIFEST_PATH = ROOT / "tools" / "vtuber_realize_images.json"
ORG = "りあぷろ"
TERMS_PAGE = "https://realize-pro.com/guideline/"
IMAGE_USAGE = "noncommercial_fanwork"
INDIVIDUAL_TERMS = {
    "佐透 直": "https://sugu310.fanbox.cc/posts/2568555",
    "狼桜ぽんさや": "https://lit.link/ponsaya",
    "憂羽うゆ": "https://lit.link/uyunyqn",
    "橙崎ちなつ": "https://lit.link/chinatsuvtuber",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _official_image_url(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and parsed.netloc == "realize-pro.com"
        and parsed.path.startswith("/wp-content/uploads/")
        and parsed.path.lower().endswith((".png", ".webp", ".jpg", ".jpeg"))
        and not parsed.query
        and not parsed.fragment
    )


def load_manifest(
    path: Path = MANIFEST_PATH, *, include_inactive: bool = False,
) -> dict[str, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("images"), list):
        raise ValueError(f"{path}: unsupported image manifest")
    required = {
        "original", "profile_id", "enabled", "image_url", "source_page",
        "credit", "terms_page", "reviewed", "source_sha256",
    }
    records: dict[str, dict] = {}
    image_urls: set[str] = set()
    profile_ids: set[int] = set()
    for record in data["images"]:
        if required - record.keys():
            raise ValueError(f"{path}: incomplete image record")
        name = record["original"]
        profile_id = record["profile_id"]
        if not name or name != name.strip() or name in records:
            raise ValueError(f"{path}: empty or duplicate name: {name!r}")
        if type(profile_id) is not int or profile_id <= 0 or profile_id in profile_ids:
            raise ValueError(f"{name}: invalid or duplicate profile_id")
        if type(record["enabled"]) is not bool:
            raise ValueError(f"{name}: enabled must be boolean")
        if not _official_image_url(record["image_url"]):
            raise ValueError(f"{name}: image_url is not an official image")
        if record["image_url"] in image_urls:
            raise ValueError(f"{name}: duplicate image_url")
        expected_page = f"https://realize-pro.com/talents/?open={profile_id}"
        if record["source_page"] != expected_page:
            raise ValueError(f"{name}: source_page does not match profile_id")
        if record["terms_page"] != INDIVIDUAL_TERMS.get(name, TERMS_PAGE):
            raise ValueError(f"{name}: incorrect terms_page")
        if not record["credit"].strip():
            raise ValueError(f"{name}: missing credit")
        for field in ("original", "credit", "image_url", "source_page", "terms_page"):
            if any(char in record[field] for char in ',"\r\n'):
                raise ValueError(f"{name}: invalid CSV characters in {field}")
        reviewed = date.fromisoformat(record["reviewed"])
        if reviewed.isoformat() != record["reviewed"]:
            raise ValueError(f"{name}: invalid reviewed date")
        if not SHA256.fullmatch(record["source_sha256"]):
            raise ValueError(f"{name}: invalid source_sha256")
        records[name] = record
        image_urls.add(record["image_url"])
        profile_ids.add(profile_id)
    return {
        name: record for name, record in records.items()
        if include_inactive or record["enabled"]
    }


def apply(csv_path: Path = CSV_PATH, manifest_path: Path = MANIFEST_PATH) -> tuple[int, int]:
    manifest = load_manifest(manifest_path, include_inactive=True)
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    image_fields = ("image", "image_page", "image_credit", "image_usage", "image_terms_page")
    required = {"original", "category", "org", *image_fields}
    if required - set(fieldnames):
        raise ValueError(f"{csv_path}: missing required columns")
    missing = set(manifest) - {row["original"] for row in rows}
    if missing:
        raise ValueError(f"{csv_path}: missing people: {sorted(missing)}")
    changed_people: set[str] = set()
    changed_rows = 0
    for row in rows:
        name = row["original"]
        record = manifest.get(name)
        if record is None:
            if _official_image_url(row["image"]):
                raise ValueError(f"{name}: official image absent from manifest")
            continue
        if row["category"] != "vtuber" or row["org"] != ORG:
            raise ValueError(f"{name}: category or org does not match manifest")
        if record["enabled"]:
            desired = (
                record["image_url"], record["source_page"], record["credit"],
                IMAGE_USAGE, record["terms_page"],
            )
        elif _official_image_url(row["image"]) or not row["image"]:
            desired = (card_image_url(name), card_page_url(name), "", "", "")
        else:
            continue
        if tuple(row[field] for field in image_fields) != desired:
            row.update(zip(image_fields, desired))
            changed_people.add(name)
            changed_rows += 1
    if changed_rows:
        write_csv_no_trailing_newline(csv_path, fieldnames, rows)
    return len(changed_people), changed_rows


if __name__ == "__main__":
    people, rows = apply()
    print(f"vtuber.csv: Realize Production images updated for {people} people / {rows} rows")
