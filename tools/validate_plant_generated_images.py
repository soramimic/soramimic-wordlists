#!/usr/bin/env python3
"""植物の科別生成画像・manifest・CSV割当を検証する。"""

from __future__ import annotations

import csv
import hashlib
from collections import Counter
from pathlib import Path

from apply_plant_generated_images import CSV_PATH, RAW_BASE, load_manifest
from plan_plant_generated_images import (
    MIN_FAMILY_ROWS, build_plan, load_rows, stable_filename, validate_plan,
)

ROOT = Path(__file__).resolve().parent.parent
IMAGE_DIR = ROOT / "images" / "plant"
# 2026-08-16 の全数目視QCで採用した基準値。資産や割当の脱落を検知する。
MIN_ASSETS = 180
MIN_COVERED_ROWS = 699


def webp_size(raw: bytes) -> tuple[int, int]:
    marker = raw.find(b"\x9d\x01\x2a")
    if raw[:4] != b"RIFF" or raw[8:12] != b"WEBP" or marker < 0:
        raise ValueError("invalid WebP")
    width = int.from_bytes(raw[marker + 3:marker + 5], "little") & 0x3FFF
    height = int.from_bytes(raw[marker + 5:marker + 7], "little") & 0x3FFF
    return width, height


def validate() -> None:
    missing_photo_rows = load_rows()
    plan, assignment = build_plan(missing_photo_rows)
    validate_plan(plan, assignment, missing_photo_rows)
    records = load_manifest()
    accepted = [record for record in records
                if record.get("accepted") is True
                and record.get("qc", {}).get("status") == "accepted"]
    planned = {(record.get("family_qid") or "", record["name"]): record
               for record in plan}
    actual = {(record.get("family_qid") or "", record["name"]): record
              for record in accepted}
    unexpected = set(actual) - set(planned)
    if unexpected:
        raise ValueError(f"manifest contains ineligible families: {sorted(unexpected)}")
    if len(accepted) < MIN_ASSETS:
        raise ValueError(f"too few plant family images: {len(accepted)}")
    covered = Counter(assignment.values())
    covered_rows = sum(covered[record["word"]] for key, record in planned.items()
                       if key in actual)
    if covered_rows < MIN_COVERED_ROWS:
        raise ValueError(f"too few rows covered by family images: {covered_rows}")
    for identity, record in actual.items():
        item = planned[identity]
        name, qid = record["name"], record.get("family_qid", "")
        if record["filename"] != stable_filename(name, qid):
            raise ValueError(f"unstable filename for {name}: {record['filename']}")
        path = IMAGE_DIR / record["filename"]
        if not path.is_file():
            raise ValueError(f"missing generated image: {path}")
        raw = path.read_bytes()
        try:
            size = webp_size(raw)
        except ValueError as error:
            raise ValueError(f"invalid generated WebP: {path}") from error
        if size != (960, 600):
            raise ValueError(f"unexpected generated image size: {path}")
        if record.get("label") != "生成イメージ" or record.get("scope") != "family":
            raise ValueError(f"missing disclosure metadata: {name}")
        if record.get("accepted") is not True or record.get("qc", {}).get("status") != "accepted":
            raise ValueError(f"image is not accepted: {name}")
        if record.get("member_count") != covered[item["word"]]:
            raise ValueError(f"member count mismatch: {name}")
        if hashlib.sha256(raw).hexdigest() != record.get("sha256"):
            raise ValueError(f"generated image hash mismatch: {name}")

    with CSV_PATH.open(encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    by_word = {item["word"]: actual[(item.get("family_qid") or "", item["name"])]
               for item in plan if (item.get("family_qid") or "", item["name"]) in actual}
    actual_covered = 0
    for row in rows:
        target = assignment.get(row["original"])
        if target not in by_word:
            continue
        record = by_word[target]
        if row["image"] != f"{RAW_BASE}/{record['filename']}":
            raise ValueError(f"CSV family image mismatch: {row['original']}")
        actual_covered += 1
    if actual_covered != covered_rows:
        raise ValueError("CSV family image coverage mismatch")
    if MIN_FAMILY_ROWS != 1:
        raise ValueError("unexpected family threshold")
    print(f"plant family generated images: assets={len(accepted)} covered={covered_rows} "
          f"class_fallback={len(missing_photo_rows) - covered_rows}")


if __name__ == "__main__":
    validate()
