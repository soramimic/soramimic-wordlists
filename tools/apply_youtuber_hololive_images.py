#!/usr/bin/env python3
"""Apply reviewed Hololive profile images and roster rows to youtuber.csv."""

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
CSV_PATH = ROOT / "youtuber.csv"
MANIFEST_PATH = Path(__file__).resolve().parent / "youtuber_hololive_images.json"
IMAGE_PREFIX = "https://hololive.hololivepro.com/wp-content/uploads/"
TERMS_PAGE = "https://hololivepro.com/terms/"
IMAGE_USAGE = "noncommercial_fanwork"
EXPECTED_STATUS_COUNTS = Counter({"current": 63, "graduated": 9, "activity_ended": 2})
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
FALLBACK_COLUMNS = {
    "id", "original", "surface", "pronunciation", "type", "category",
    "org", "debut_year", "status", "wikidata", "channel", "description",
    "subscribers", "subscribers_as_of",
}


def _official_url(value: str, *, uploads: bool) -> bool:
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port
        or parsed.hostname != "hololive.hololivepro.com"
    ):
        return False
    if uploads:
        return value.startswith(IMAGE_PREFIX)
    return parsed.path.startswith("/talents/") and parsed.path.endswith("/")


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.get("images", [])
    required = {
        "original", "talent_status", "image_url", "source_page", "credit",
        "terms_page", "reviewed", "source_sha256", "fallback_rows",
    }
    result: dict[str, dict] = {}
    status_counts: Counter[str] = Counter()
    fallback_ids: set[str] = set()
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
        if not _official_url(record["image_url"], uploads=True):
            raise SystemExit(f"error: {context} のimage_urlが公式配信元でない")
        if not _official_url(record["source_page"], uploads=False):
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
        fallback_rows = record["fallback_rows"]
        if not isinstance(fallback_rows, list):
            raise SystemExit(f"error: {context} のfallback_rowsが配列でない")
        for row_index, row in enumerate(fallback_rows, 1):
            row_context = f"{context} fallback_rows[{row_index}]"
            if set(row) != FALLBACK_COLUMNS:
                raise SystemExit(f"error: {row_context} の列が不正")
            if row["original"] != original or row["category"] != "vtuber":
                raise SystemExit(f"error: {row_context} の人物またはcategoryが不正")
            if row["id"] in fallback_ids:
                raise SystemExit(f"error: fallback id が重複: {row['id']}")
            fallback_ids.add(row["id"])
            if any(any(char in value for char in ',"\r\n') for value in row.values()):
                raise SystemExit(f"error: {row_context} にCSV禁止文字がある")
        result[original] = record
        status_counts[status] += 1
    if path.resolve() == MANIFEST_PATH.resolve() and status_counts != EXPECTED_STATUS_COUNTS:
        raise SystemExit(
            "error: ホロライブ名簿件数が不正: "
            f"{dict(status_counts)} (期待 {dict(EXPECTED_STATUS_COUNTS)})"
        )
    return result


def apply(
    csv_path: Path = CSV_PATH,
    manifest_path: Path = MANIFEST_PATH,
) -> tuple[int, int, int]:
    manifest = load_manifest(manifest_path)
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    required_columns = FALLBACK_COLUMNS | {
        "image", "image_page", "image_credit", "image_usage", "image_terms_page",
    }
    missing_columns = sorted(required_columns - set(fieldnames))
    if missing_columns:
        raise SystemExit(f"error: youtuber.csv に {missing_columns[0]} がない")

    by_original: dict[str, list[dict[str, str]]] = {}
    used_ids = {row["id"] for row in rows}
    for row in rows:
        by_original.setdefault(row["original"], []).append(row)

    added_rows = 0
    for original, record in manifest.items():
        targets = by_original.get(original, [])
        if not targets:
            if not record["fallback_rows"]:
                raise SystemExit(f"error: youtuber.csv に対象がいない: {original}")
            targets = []
            for fallback in record["fallback_rows"]:
                if fallback["id"] in used_ids:
                    raise SystemExit(f"error: fallback id が既存行と重複: {fallback['id']}")
                row = {column: "" for column in fieldnames}
                row.update(fallback)
                rows.append(row)
                targets.append(row)
                used_ids.add(row["id"])
                added_rows += 1
            by_original[original] = targets

    changed_people: set[str] = set()
    changed_rows = 0
    # A removed approval restores the symbolic card on the next scheduled update.
    for row in rows:
        if row.get("image", "").startswith(IMAGE_PREFIX) and row["original"] not in manifest:
            row["image"] = card_image_url(row["original"])
            row["image_page"] = card_page_url(row["original"])
            row["image_credit"] = ""
            row["image_usage"] = ""
            row["image_terms_page"] = ""
            changed_people.add(row["original"])
            changed_rows += 1

    for original, record in manifest.items():
        desired_status = "current" if record["talent_status"] == "current" else "former"
        for row in by_original[original]:
            if row["category"] != "vtuber":
                raise SystemExit(f"error: {original} がVTuber行でない")
            desired = (
                record["image_url"], record["source_page"], record["credit"],
                IMAGE_USAGE, record["terms_page"], desired_status,
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
    return len(changed_people), changed_rows, added_rows


def main() -> None:
    people, rows, added = apply()
    print(f"youtuber.csv: ホロライブ公式画像 {people}人 / {rows}行を更新 ({added}行追加)")


if __name__ == "__main__":
    main()
