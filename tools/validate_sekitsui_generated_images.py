#!/usr/bin/env python3
"""脊椎動物の科別生成画像・manifest・CSV割当を検証する。"""

from __future__ import annotations

import csv
import hashlib
from collections import Counter
from pathlib import Path

from apply_sekitsui_generated_images import CSV_PATH, RAW_BASE, load_manifest
from plan_sekitsui_generated_images import (
    MIN_FAMILY_ROWS, build_plan, load_rows, stable_filename, validate_plan,
)

ROOT = Path(__file__).resolve().parent.parent
IMAGE_DIR = ROOT / "images" / "sekitsui"
MIN_ASSETS = 90
MIN_COVERED_ROWS = 1600


def validate() -> None:
    missing_photo_rows = load_rows()
    plan, assignment = build_plan(missing_photo_rows)
    validate_plan(plan, assignment, missing_photo_rows)
    records = load_manifest()
    by_family = {record["name"]: record for record in records}
    expected_families = {record["name"] for record in plan}
    unexpected = set(by_family) - expected_families
    if unexpected:
        raise ValueError(f"manifest contains ineligible families: {sorted(unexpected)}")
    if len(records) < MIN_ASSETS:
        raise ValueError(f"too few sekitsui family images: {len(records)}")

    covered = Counter(assignment.values())
    covered_rows = sum(covered[f"family:{name}"] for name in by_family)
    if covered_rows < MIN_COVERED_ROWS:
        raise ValueError(f"too few rows covered by family images: {covered_rows}")

    for name, record in by_family.items():
        filename = record["filename"]
        if filename != stable_filename(name):
            raise ValueError(f"unstable filename for {name}: {filename}")
        path = IMAGE_DIR / filename
        if not path.is_file():
            raise ValueError(f"missing generated image: {path}")
        raw = path.read_bytes()
        marker = raw.find(b"\x9d\x01\x2a")
        if raw[:4] != b"RIFF" or raw[8:12] != b"WEBP" or marker < 0:
            raise ValueError(f"invalid generated WebP: {path}")
        width = int.from_bytes(raw[marker + 3:marker + 5], "little") & 0x3FFF
        height = int.from_bytes(raw[marker + 5:marker + 7], "little") & 0x3FFF
        if (width, height) != (960, 600):
            raise ValueError(f"unexpected generated image size: {path}")
        if record.get("label") != "生成イメージ" or record.get("scope") != "family":
            raise ValueError(f"missing disclosure metadata: {name}")
        if record.get("qc", {}).get("status") != "accepted":
            raise ValueError(f"image is not accepted: {name}")
        if record.get("member_count") != covered[f"family:{name}"]:
            raise ValueError(f"member count mismatch: {name}")
        if hashlib.sha256(raw).hexdigest() != record.get("sha256"):
            raise ValueError(f"generated image hash mismatch: {name}")

    with CSV_PATH.open(encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    actual_covered = 0
    for row in rows:
        target = assignment.get(row["original"])
        if not target or not target.startswith("family:"):
            continue
        family = target.split(":", 1)[1]
        filename = by_family[family]["filename"]
        if row["image"] != f"{RAW_BASE}/{filename}":
            raise ValueError(f"CSV family image mismatch: {row['original']}")
        actual_covered += 1
    if actual_covered != covered_rows:
        raise ValueError("CSV family image coverage mismatch")
    if MIN_FAMILY_ROWS != 5:
        raise ValueError("unexpected family threshold")
    print(
        f"sekitsui family generated images: assets={len(records)} "
        f"covered={covered_rows} class_fallback={len(missing_photo_rows) - covered_rows}"
    )


if __name__ == "__main__":
    validate()
