#!/usr/bin/env python3
"""植物の分類SVGを検品済みの科別生成イメージへ置き換える。"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from apply_class_images import is_class_image, urls as class_image_urls
from plan_plant_generated_images import valid_qid
from wpnames import write_csv_no_trailing_newline

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "plant.csv"
MANIFEST_PATH = Path(__file__).with_name("plant_generated_images.json")
RAW_BASE = "https://raw.githubusercontent.com/soramimic/soramimic-wordlists/main/images/plant"
PAGE_BASE = "https://github.com/soramimic/soramimic-wordlists/blob/main/images/plant"
GENERATED_PREFIX = f"{RAW_BASE}/plant_family_"


def is_generated_image(url: str) -> bool:
    return url.startswith(GENERATED_PREFIX) and url.endswith("_generated.webp")


def load_manifest(path: Path = MANIFEST_PATH) -> list[dict]:
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("plant generated image manifest must be a list")
    identities = []
    filenames = []
    name_qids: dict[str, set[str]] = {}
    for record in records:
        name = (record.get("name") or "").strip()
        qid = (record.get("family_qid") or "").strip()
        if record.get("scope") != "family" or not name or (qid and not valid_qid(qid)):
            raise ValueError("plant generated image manifest has invalid family scope")
        identities.append((qid, name))
        filenames.append(record.get("filename"))
        if qid:
            name_qids.setdefault(name, set()).add(qid)
    if any(len(qids) > 1 for qids in name_qids.values()):
        raise ValueError("plant generated image manifest has conflicting family QIDs")
    if len(identities) != len(set(identities)) or len(filenames) != len(set(filenames)):
        raise ValueError("plant generated image manifest has duplicate entries")
    return records


def render(rows: list[dict[str, str]], records: list[dict]) -> tuple[list[dict[str, str]], int]:
    accepted = [record for record in records
                if record.get("accepted") is True
                and record.get("qc", {}).get("status") == "accepted"]
    by_qid = {record["family_qid"]: record for record in accepted
              if record.get("family_qid")}
    by_name_fallback = {record["name"]: record for record in accepted
                        if not record.get("family_qid")}
    by_class = class_image_urls("plant", "class-image-v1")
    changed = 0
    for row in rows:
        current = row.get("image", "")
        if current and not is_class_image(current) and not is_generated_image(current):
            continue
        family = (row.get("family") or "").strip()
        qid = (row.get("family_wikidata") or "").strip()
        record = by_qid.get(qid) if qid else by_name_fallback.get(family)
        if record and record["name"] != family:
            record = None
        if not record:
            if is_generated_image(current):
                fallback = by_class.get((row.get("class") or "").strip(), by_class["NA"])
                row["image"], row["image_page"] = fallback
                changed += 1
            continue
        image = f"{RAW_BASE}/{record['filename']}"
        page = f"{PAGE_BASE}/{record['filename']}"
        if current != image or row.get("image_page", "") != page:
            row["image"], row["image_page"] = image, page
            changed += 1
    return rows, changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    with CSV_PATH.open(encoding="utf-8") as source:
        reader = csv.DictReader(source)
        rows, columns = [dict(row) for row in reader], list(reader.fieldnames or [])
    rendered, changed = render(rows, load_manifest())
    if args.check:
        if changed:
            print(f"error: plant generated images are stale ({changed} rows)")
            return 1
        print("plant generated images: up to date")
        return 0
    write_csv_no_trailing_newline(CSV_PATH, columns, rendered)
    print(f"plant.csv: 科別生成イメージを更新 {changed}行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
