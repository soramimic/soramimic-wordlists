#!/usr/bin/env python3
"""キュレーション台帳から marine_life.csv を再生成する。

海洋性は単一の分類群ではなく、Wikidata の分類木だけでは安全に判定できない。
そのため初版はレビュー済み台帳を正本とし、このスクリプトで利用用CSVを決定的に
生成する。ネットワークアクセスは行わない。

usage: python3 tools/update_marine_life.py [--check]
"""

import argparse
import csv
import io
import os
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path(__file__).with_name("marine_life_source.csv")
OUTPUT = ROOT / "marine_life.csv"

CLASSES = ("哺乳類", "爬虫類", "魚類", "無脊椎動物")
MIN_CLASS_COUNTS = {
    "哺乳類": 30,
    "爬虫類": 12,
    "魚類": 70,
    "無脊椎動物": 60,
}
MIN_QID_COUNT = 100
VERTEBRATE_BY_CLASS = {
    "哺乳類": "脊椎動物",
    "爬虫類": "脊椎動物",
    "魚類": "脊椎動物",
    "無脊椎動物": "無脊椎動物",
}
IMAGE_FILE_BY_CLASS = {
    "哺乳類": "marine_mammal.svg",
    "爬虫類": "marine_reptile.svg",
    "魚類": "marine_fish.svg",
    "無脊椎動物": "marine_invertebrate.svg",
}
RAW_BASE = (
    "https://raw.githubusercontent.com/soramimic/soramimic-wordlists/"
    "main/images/marine_life"
)
PAGE_BASE = (
    "https://github.com/soramimic/soramimic-wordlists/blob/"
    "main/images/marine_life"
)
KATAKANA = re.compile(r"^[ァ-ヶー・]+$")
QID = re.compile(r"^Q[1-9][0-9]*$")
SOURCE_COLUMNS = (
    "id", "name", "class", "vertebrate", "order", "family", "description",
    "wikidata",
)
OUTPUT_COLUMNS = (
    "id", "original", "surface", "pronunciation", "class", "vertebrate",
    "order", "family", "description", "image", "image_page", "wikidata",
)


def load_source(path: Path = SOURCE) -> list[dict[str, str]]:
    raw = path.read_bytes()
    if b"\r" in raw or raw.endswith(b"\n") or b'"' in raw:
        raise ValueError("source CSV must use LF without a trailing newline or quotes")
    lines = raw.decode("utf-8").split("\n")
    if tuple(lines[0].split(",")) != SOURCE_COLUMNS:
        raise ValueError(f"unexpected source columns: {lines[0].split(',')}")
    for lineno, line in enumerate(lines[1:], 2):
        if len(line.split(",")) != len(SOURCE_COLUMNS):
            raise ValueError(f"line {lineno}: unexpected number of columns")
    with io.StringIO(raw.decode("utf-8"), newline="") as f:
        rows = [dict(row) for row in csv.DictReader(f)]

    seen: set[str] = set()
    seen_descriptions: set[str] = set()
    for lineno, row in enumerate(rows, 2):
        if row["id"] != str(lineno - 2):
            raise ValueError(f"line {lineno}: id must be append-only sequence: {row['id']}")
        name = row["name"]
        if len(name) < 2 or not KATAKANA.fullmatch(name) or name[0] == "・" or name[-1] == "・":
            raise ValueError(f"line {lineno}: name is not katakana: {name}")
        if name in seen:
            raise ValueError(f"line {lineno}: duplicate name: {name}")
        seen.add(name)
        cls = row["class"]
        if cls not in CLASSES:
            raise ValueError(f"line {lineno}: invalid class: {cls}")
        if row["vertebrate"] != VERTEBRATE_BY_CLASS[cls]:
            raise ValueError(f"line {lineno}: class/vertebrate mismatch: {name}")
        if not row["order"].endswith("目") or not row["family"].endswith("科"):
            raise ValueError(f"line {lineno}: order/family must end in 目/科: {name}")
        if not (20 <= len(row["description"]) <= 60) or not row["description"].endswith("。"):
            raise ValueError(f"line {lineno}: invalid description: {name}")
        if row["description"] in seen_descriptions:
            raise ValueError(f"line {lineno}: duplicate description: {name}")
        seen_descriptions.add(row["description"])
        if any("," in row[col] for col in SOURCE_COLUMNS):
            raise ValueError(f"line {lineno}: comma is not supported: {name}")
        if row["wikidata"] and not QID.fullmatch(row["wikidata"]):
            raise ValueError(f"line {lineno}: invalid Wikidata QID: {name}")
    counts = Counter(row["class"] for row in rows)
    for cls, minimum in MIN_CLASS_COUNTS.items():
        if counts[cls] < minimum:
            raise ValueError(f"too few {cls} rows: {counts[cls]} (minimum {minimum})")
    qid_count = sum(bool(row["wikidata"]) for row in rows)
    if qid_count < MIN_QID_COUNT:
        raise ValueError(f"too few Wikidata QIDs: {qid_count} (minimum {MIN_QID_COUNT})")
    return rows


def validate_images() -> None:
    image_dir = ROOT / "images" / "marine_life"
    for filename in IMAGE_FILE_BY_CLASS.values():
        path = image_dir / filename
        if not path.is_file():
            raise ValueError(f"missing concept image: {path}")
        root = ET.parse(path).getroot()
        label = "".join(root.itertext())
        if root.attrib.get("width") != "320" or root.attrib.get("height") != "200" or "イメージ" not in label:
            raise ValueError(f"missing or unlabeled concept image: {path}")


def generate(rows: list[dict[str, str]]) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        filename = IMAGE_FILE_BY_CLASS[row["class"]]
        writer.writerow({
            "id": row["id"],
            "original": row["name"],
            "surface": row["name"],
            "pronunciation": row["name"],
            "class": row["class"],
            "vertebrate": row["vertebrate"],
            "order": row["order"],
            "family": row["family"],
            "description": row["description"],
            "image": f"{RAW_BASE}/{filename}",
            "image_page": f"{PAGE_BASE}/{filename}",
            "wikidata": row["wikidata"],
        })
    return out.getvalue().rstrip("\n").encode("utf-8")


def removed_names(generated: bytes, output: Path = OUTPUT) -> set[str]:
    if not output.exists():
        return set()
    old = {row["original"] for row in csv.DictReader(io.StringIO(output.read_text(encoding="utf-8")))}
    new = {row["original"] for row in csv.DictReader(io.StringIO(generated.decode("utf-8")))}
    return old - new


def write_atomic(path: Path, data: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_bytes(data)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="再生成結果と既存CSVが一致するかだけ確認する")
    parser.add_argument("--allow-removals", action="store_true",
                        help="既存CSVからの項目削除を明示的に許可する")
    args = parser.parse_args(argv)
    rows = load_source()
    validate_images()
    generated = generate(rows)
    counts = Counter(row["class"] for row in rows)
    summary = ", ".join(f"{key} {counts[key]}" for key in CLASSES)
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_bytes() != generated:
            print("marine_life.csv は台帳からの再生成結果と一致しません")
            return 1
        print(f"marine_life.csv: 再生成差分なし ({len(rows)}行; {summary})")
        return 0
    removed = removed_names(generated, OUTPUT)
    if removed and not args.allow_removals:
        print(f"既存CSVから{len(removed)}件が消えるため中断しました: "
              + ", ".join(sorted(removed)[:10]))
        print("意図した削除なら --allow-removals を付けて再実行してください")
        return 1
    write_atomic(OUTPUT, generated)
    print(f"marine_life.csv: {len(rows)}行を再生成 ({summary})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
