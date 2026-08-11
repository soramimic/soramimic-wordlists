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
import json
import os
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path(__file__).with_name("marine_life_source.csv")
IMAGE_SOURCES = Path(__file__).with_name("marine_life_image_sources.jsonl")
OUTPUT = ROOT / "marine_life.csv"

CLASSES = ("哺乳類", "爬虫類", "魚類", "無脊椎動物")
MIN_CLASS_COUNTS = {
    "哺乳類": 30,
    "爬虫類": 12,
    "魚類": 650,
    "無脊椎動物": 250,
}
MIN_TOTAL_COUNT = 1000
MIN_QID_COUNT = 700
MIN_APHIA_COUNT = 800
MIN_PHOTO_COUNT = 500
VERTEBRATE_BY_CLASS = {
    "哺乳類": "脊椎動物",
    "爬虫類": "脊椎動物",
    "魚類": "脊椎動物",
    "無脊椎動物": "無脊椎動物",
}
IMAGE_FILE_BY_GROUP = {
    "哺乳類": "marine_mammal.svg",
    "爬虫類": "marine_reptile.svg",
    "魚類": "marine_fish.svg",
    "無脊椎動物": "marine_invertebrate.svg",
    "刺胞動物": "marine_cnidarian.svg",
    "甲殻類": "marine_crustacean.svg",
    "軟体動物": "marine_mollusk.svg",
    "棘皮動物": "marine_echinoderm.svg",
    "蠕虫型": "marine_worm.svg",
    "その他無脊椎": "marine_other_invertebrate.svg",
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
APHIA_ID = re.compile(r"^[1-9][0-9]*$")
JODC_CODE = re.compile(r"^[0-9]{14}$")
SHA1 = re.compile(r"^[0-9a-f]{40}$")
SCIENTIFIC_NAME = re.compile(r"^[A-Z][A-Za-z().-]+(?: [A-Za-z().-]+)+$")
SOURCE_COLUMNS = (
    "id", "name", "class", "vertebrate", "order", "family", "description",
    "wikidata", "scientific_name", "aphia_id", "jodc_code", "image", "image_page",
    "image_group",
)
OUTPUT_COLUMNS = (
    "id", "original", "surface", "pronunciation", "class", "vertebrate",
    "order", "family", "description", "image", "image_page", "wikidata",
    "scientific_name", "aphia_id",
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
        if row["scientific_name"] and not SCIENTIFIC_NAME.fullmatch(row["scientific_name"]):
            raise ValueError(f"line {lineno}: invalid scientific name: {name}")
        if row["aphia_id"] and not APHIA_ID.fullmatch(row["aphia_id"]):
            raise ValueError(f"line {lineno}: invalid AphiaID: {name}")
        if row["jodc_code"] and not JODC_CODE.fullmatch(row["jodc_code"]):
            raise ValueError(f"line {lineno}: invalid JODC code: {name}")
        if bool(row["image"]) != bool(row["image_page"]):
            raise ValueError(f"line {lineno}: image/image_page mismatch: {name}")
        if row["image"] and not row["image"].startswith(
                "https://upload.wikimedia.org/wikipedia/commons/"):
            raise ValueError(f"line {lineno}: non-Commons photo: {name}")
        if row["image_page"] and "commons.wikimedia.org/wiki/File:" not in row["image_page"]:
            raise ValueError(f"line {lineno}: invalid Commons source page: {name}")
        if row["image_group"] not in IMAGE_FILE_BY_GROUP:
            raise ValueError(f"line {lineno}: invalid image group: {name}")
    counts = Counter(row["class"] for row in rows)
    for cls, minimum in MIN_CLASS_COUNTS.items():
        if counts[cls] < minimum:
            raise ValueError(f"too few {cls} rows: {counts[cls]} (minimum {minimum})")
    qid_count = sum(bool(row["wikidata"]) for row in rows)
    if qid_count < MIN_QID_COUNT:
        raise ValueError(f"too few Wikidata QIDs: {qid_count} (minimum {MIN_QID_COUNT})")
    aphia_count = sum(bool(row["aphia_id"]) for row in rows)
    if aphia_count < MIN_APHIA_COUNT:
        raise ValueError(f"too few AphiaIDs: {aphia_count} (minimum {MIN_APHIA_COUNT})")
    if len(rows) < MIN_TOTAL_COUNT:
        raise ValueError(f"too few rows: {len(rows)} (minimum {MIN_TOTAL_COUNT})")
    return rows


def validate_images() -> None:
    image_dir = ROOT / "images" / "marine_life"
    for filename in set(IMAGE_FILE_BY_GROUP.values()):
        path = image_dir / filename
        if not path.is_file():
            raise ValueError(f"missing concept image: {path}")
        root = ET.parse(path).getroot()
        label = "".join(root.itertext())
        if root.attrib.get("width") != "320" or root.attrib.get("height") != "200" or "イメージ" not in label:
            raise ValueError(f"missing or unlabeled concept image: {path}")


def validate_image_sources(rows: list[dict[str, str]], path: Path = IMAGE_SOURCES) -> None:
    """実写のライセンス・同定根拠snapshotが台帳と一対一に対応するか検査する。"""
    raw = path.read_bytes()
    if b"\r" in raw or raw.endswith(b"\n"):
        raise ValueError("image source JSONL must use LF without a trailing newline")
    records = [json.loads(line) for line in raw.decode("utf-8").split("\n")]
    by_name: dict[str, dict] = {}
    for lineno, record in enumerate(records, 1):
        name = record.get("name", "")
        if not name or name in by_name:
            raise ValueError(f"image source line {lineno}: missing or duplicate name: {name}")
        license_name = record.get("license", "")
        if not re.match(r"^(CC BY(?:-SA)?(?: |$)|CC0$|Public domain$)",
                        license_name, re.IGNORECASE):
            raise ValueError(f"image source line {lineno}: unsupported license: {name}")
        if license_name.upper().startswith("CC BY"):
            if not record.get("artist"):
                raise ValueError(f"image source line {lineno}: missing artist: {name}")
            if "creativecommons.org/licenses/" not in record.get("license_url", ""):
                raise ValueError(f"image source line {lineno}: missing license URL: {name}")
        if license_name.upper() == "CC0" and \
                "creativecommons.org/publicdomain/zero/" not in record.get("license_url", ""):
            raise ValueError(f"image source line {lineno}: missing CC0 URL: {name}")
        if not SHA1.fullmatch(record.get("sha1", "")):
            raise ValueError(f"image source line {lineno}: invalid SHA1: {name}")
        if int(record.get("width", 0)) < 320 or int(record.get("height", 0)) < 200:
            raise ValueError(f"image source line {lineno}: image too small: {name}")
        if not record.get("identification_basis"):
            raise ValueError(f"image source line {lineno}: missing identification basis: {name}")
        by_name[name] = record
    expected = {row["name"]: row for row in rows if row["image"]}
    if set(by_name) != set(expected):
        missing = sorted(set(expected) - set(by_name))[:10]
        extra = sorted(set(by_name) - set(expected))[:10]
        raise ValueError(f"image source names mismatch: missing={missing}, extra={extra}")
    for name, row in expected.items():
        record = by_name[name]
        for field in ("image", "image_page", "wikidata", "scientific_name", "aphia_id"):
            if record.get(field, "") != row[field]:
                raise ValueError(f"image source mismatch for {name}: {field}")
    if len(records) < MIN_PHOTO_COUNT:
        raise ValueError(f"too few reviewed photos: {len(records)} (minimum {MIN_PHOTO_COUNT})")


def generate(rows: list[dict[str, str]]) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        filename = IMAGE_FILE_BY_GROUP[row["image_group"]]
        image = row["image"] or f"{RAW_BASE}/{filename}"
        image_page = row["image_page"] or f"{PAGE_BASE}/{filename}"
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
            "image": image,
            "image_page": image_page,
            "wikidata": row["wikidata"],
            "scientific_name": row["scientific_name"],
            "aphia_id": row["aphia_id"],
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
    validate_image_sources(rows)
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
