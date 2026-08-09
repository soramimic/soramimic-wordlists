#!/usr/bin/env python3
"""school.csv の実写が無い学校に校種別の概念イメージを割り当てる。

概念イメージは実写が後から見つかったときに置き換えてよいフォールバック。
同じ id の全表層には同じ画像を設定する。

usage: python3 tools/apply_school_type_images.py
"""

import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_school_type_images import SCHOOL_TYPES
from wpnames import write_csv_no_trailing_newline

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "school.csv"
RAW_PREFIX = "https://raw.githubusercontent.com/soramimic/soramimic-wordlists/main/images/school_type/"
BLOB_PREFIX = "https://github.com/soramimic/soramimic-wordlists/blob/main/images/school_type/"


def is_school_type_image(url: str) -> bool:
    return (url or "").startswith(RAW_PREFIX)


def media_for(label: str) -> tuple[str, str] | None:
    spec = SCHOOL_TYPES.get(label)
    if not spec:
        return None
    filename = spec[0]
    return RAW_PREFIX + filename, BLOB_PREFIX + filename


def main() -> int:
    with CSV_PATH.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        cols = list(reader.fieldnames or [])
    for col in ("image", "image_page"):
        if col not in cols:
            pos = cols.index("wikidata") if "wikidata" in cols else len(cols)
            cols.insert(pos, col)

    filled = Counter()
    kept_photos = 0
    for row in rows:
        row.setdefault("image", "")
        row.setdefault("image_page", "")
        if row["image"] and not is_school_type_image(row["image"]):
            kept_photos += 1
            continue
        media = media_for(row.get("school_type", ""))
        if not media or row["image"] == media[0]:
            continue
        row["image"], row["image_page"] = media
        filled[row.get("school_type", "") or "NA"] += 1

    write_csv_no_trailing_newline(CSV_PATH, cols, rows)
    total = sum(is_school_type_image(row.get("image", "")) for row in rows)
    print(f"school.csv: 校種イメージを付与 +{sum(filled.values())}行 "
          f"({', '.join(f'{k} {v}' for k, v in sorted(filled.items()))}), "
          f"実写行 {kept_photos}, 校種イメージ計 {total}行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
