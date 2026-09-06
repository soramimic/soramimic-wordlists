#!/usr/bin/env python3
"""Apply reviewed NIJISANJI profile images to vtuber.csv."""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_youtuber_cards import (  # noqa: E402
    URL_PREFIX as CARD_PREFIX,
    image_page_url as card_page_url,
    image_url as card_image_url,
)
from wpnames import write_csv_no_trailing_newline  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "vtuber.csv"
MANIFEST_PATH = Path(__file__).resolve().parent / "youtuber_nijisanji_images.json"
IMAGE_HOST = "images.microcms-assets.io"
IMAGE_PATH_PREFIX = "/assets/5694fd90407444338a64d654e407cc0e/"
PROFILE_PREFIX = "https://www.nijisanji.jp/talents/l/"
TERMS_PAGE = "https://www.anycolor.co.jp/guidelines/"
IMAGE_USAGE = "noncommercial_fanwork"
EXPECTED_STATUS_COUNTS = Counter({"current": 198})
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _official_image_url(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and not parsed.username
        and not parsed.password
        and parsed.port is None
        and parsed.hostname == IMAGE_HOST
        and parsed.path.startswith(IMAGE_PATH_PREFIX)
        and not parsed.query
        and not parsed.fragment
    )


def _official_profile_url(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and not parsed.username
        and not parsed.password
        and parsed.port is None
        and parsed.hostname == "www.nijisanji.jp"
        and value.startswith(PROFILE_PREFIX)
        and len(parsed.path) > len("/talents/l/")
        and not parsed.query
        and not parsed.fragment
    )


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.get("images", [])
    required = {
        "original", "talent_status", "image_url", "source_page", "credit",
        "terms_page", "reviewed", "source_sha256",
    }
    result: dict[str, dict] = {}
    status_counts: Counter[str] = Counter()
    for index, record in enumerate(records, 1):
        context = f"{path.name} images[{index}]"
        missing = sorted(required - set(record))
        if missing:
            raise SystemExit(f"error: {context} に {missing[0]} がない")
        original = record["original"]
        if not original or original in result:
            raise SystemExit(f"error: {context} のoriginalが空または重複")
        status = record["talent_status"]
        if status not in EXPECTED_STATUS_COUNTS:
            raise SystemExit(f"error: {context} のtalent_statusが不正")
        if not _official_image_url(record["image_url"]):
            raise SystemExit(f"error: {context} のimage_urlが公式配信元でない")
        if not _official_profile_url(record["source_page"]):
            raise SystemExit(f"error: {context} のsource_pageが公式プロフィールでない")
        if record["terms_page"] != TERMS_PAGE:
            raise SystemExit(f"error: {context} のterms_pageが不正")
        if not record["credit"].strip():
            raise SystemExit(f"error: {context} のcreditが空")
        for field in ("original", "credit", "source_page"):
            if any(char in record[field] for char in ',"\r\n'):
                raise SystemExit(f"error: {context} の{field}にCSV禁止文字がある")
        if not ISO_DATE.fullmatch(record["reviewed"]):
            raise SystemExit(f"error: {context} のreviewedが不正")
        if not SHA256.fullmatch(record["source_sha256"]):
            raise SystemExit(f"error: {context} のsource_sha256が不正")
        result[original] = record
        status_counts[status] += 1
    if path.resolve() == MANIFEST_PATH.resolve() and status_counts != EXPECTED_STATUS_COUNTS:
        raise SystemExit(
            "error: にじさんじ名簿件数が不正: "
            f"{dict(status_counts)} (期待 {dict(EXPECTED_STATUS_COUNTS)})"
        )
    return result


def apply(csv_path: Path = CSV_PATH, manifest_path: Path = MANIFEST_PATH) -> tuple[int, int]:
    manifest = load_manifest(manifest_path)
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    required_columns = {
        "original", "category", "status", "image", "image_page",
        "image_credit", "image_usage", "image_terms_page",
    }
    missing_columns = sorted(required_columns - set(fieldnames))
    if missing_columns:
        raise SystemExit(f"error: vtuber.csv に {missing_columns[0]} がない")

    by_original: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_original.setdefault(row["original"], []).append(row)
    missing_people = sorted(set(manifest) - set(by_original))
    if missing_people:
        raise SystemExit(f"error: vtuber.csv に対象がいない: {missing_people[0]}")

    changed_people: set[str] = set()
    changed_rows = 0
    for row in rows:
        if _official_image_url(row.get("image", "")) and row["original"] not in manifest:
            row["image"] = card_image_url(row["original"])
            row["image_page"] = card_page_url(row["original"])
            row["image_credit"] = ""
            row["image_usage"] = ""
            row["image_terms_page"] = ""
            changed_people.add(row["original"])
            changed_rows += 1

    for original, record in manifest.items():
        for row in by_original[original]:
            if row["category"] != "vtuber":
                raise SystemExit(f"error: {original} がVTuber行でない")
            desired = (
                record["image_url"], record["source_page"], record["credit"],
                IMAGE_USAGE, record["terms_page"], "current",
            )
            current = (
                row["image"], row["image_page"], row["image_credit"],
                row["image_usage"], row["image_terms_page"], row["status"],
            )
            if current != desired:
                (
                    row["image"], row["image_page"], row["image_credit"],
                    row["image_usage"], row["image_terms_page"], row["status"],
                ) = desired
                changed_people.add(original)
                changed_rows += 1

    write_csv_no_trailing_newline(csv_path, fieldnames, rows)
    return len(changed_people), changed_rows


def main() -> None:
    people, rows = apply()
    print(f"vtuber.csv: にじさんじ公式画像 {people}人 / {rows}行を更新")


if __name__ == "__main__":
    main()
