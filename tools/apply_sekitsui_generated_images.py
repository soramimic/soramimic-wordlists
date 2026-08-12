#!/usr/bin/env python3
"""脊椎動物の分類SVGを、検品済みの科別生成イメージへ置き換える。

実写は常に保持する。現在の画像が class-image-v* の概念SVG、またはこの
スクリプトが以前割り当てた科別生成画像のときだけ、manifest と現在の family に
従って貼り直す。manifest にない科は従来の class SVG を維持する。

usage: python3 tools/apply_sekitsui_generated_images.py [--check]
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from apply_class_images import is_class_image, urls as class_image_urls
from wpnames import write_csv_no_trailing_newline

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "sekitsui.csv"
MANIFEST_PATH = Path(__file__).with_name("sekitsui_generated_images.json")
RAW_BASE = (
    "https://raw.githubusercontent.com/soramimic/soramimic-wordlists/"
    "main/images/sekitsui"
)
PAGE_BASE = (
    "https://github.com/soramimic/soramimic-wordlists/blob/"
    "main/images/sekitsui"
)
GENERATED_PREFIX = f"{RAW_BASE}/sekitsui_family_"


def is_generated_image(url: str) -> bool:
    return url.startswith(GENERATED_PREFIX) and url.endswith("_generated.webp")


def load_manifest(path: Path = MANIFEST_PATH) -> list[dict]:
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("sekitsui generated image manifest must be a list")
    keys = [(record.get("scope"), record.get("name")) for record in records]
    filenames = [record.get("filename") for record in records]
    if any(scope != "family" or not name for scope, name in keys):
        raise ValueError("sekitsui generated image manifest has invalid family scope")
    if len(keys) != len(set(keys)) or len(filenames) != len(set(filenames)):
        raise ValueError("sekitsui generated image manifest has duplicate entries")
    return records


def render(rows: list[dict[str, str]], records: list[dict]) -> tuple[list[dict[str, str]], int]:
    by_family = {record["name"]: record["filename"] for record in records}
    by_class = class_image_urls("sekitsui", "class-image-v1")
    changed = 0
    for row in rows:
        current = row.get("image", "")
        if current and not is_class_image(current) and not is_generated_image(current):
            continue
        filename = by_family.get((row.get("family") or "").strip())
        if not filename:
            if is_generated_image(current):
                fallback = by_class.get((row.get("class") or "").strip(), by_class["NA"])
                row["image"], row["image_page"] = fallback
                changed += 1
            continue
        image = f"{RAW_BASE}/{filename}"
        image_page = f"{PAGE_BASE}/{filename}"
        if current != image or row.get("image_page", "") != image_page:
            row["image"] = image
            row["image_page"] = image_page
            changed += 1
    return rows, changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    with CSV_PATH.open(encoding="utf-8") as source:
        reader = csv.DictReader(source)
        rows = [dict(row) for row in reader]
        columns = list(reader.fieldnames or [])
    rendered, changed = render(rows, load_manifest())
    if args.check:
        if changed:
            print(f"error: sekitsui generated images are stale ({changed} rows)")
            return 1
        print("sekitsui generated images: up to date")
        return 0
    write_csv_no_trailing_newline(CSV_PATH, columns, rendered)
    print(f"sekitsui.csv: 科別生成イメージを更新 {changed}行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
